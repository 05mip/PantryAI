import logging
from datetime import datetime, timezone, timedelta

from flask import Blueprint, request, jsonify, g

from services.dynamo import (
    list_meal_plan, set_meal_slot, clear_meal_slot,
    get_recipe, list_pantry,
)
from services.matching import normalize_ingredient

logger = logging.getLogger("pantryai")
meals_bp = Blueprint("meals", __name__, url_prefix="/api/meals")


def _current_week():
    now = datetime.now(timezone.utc)
    iso = now.isocalendar()
    return f"{iso[0]}-{iso[1]:02d}"


def _week_dates(week_str):
    """Return (start_date, end_date) for a YYYY-WW week string."""
    parts = week_str.split("-")
    year = int(parts[0])
    week = int(parts[1])
    jan4 = datetime(year, 1, 4, tzinfo=timezone.utc)
    start = jan4 - timedelta(days=jan4.weekday())
    start += timedelta(weeks=week - 1)
    end = start + timedelta(days=6)
    return start, end


@meals_bp.route("", methods=["GET"])
def get_meals():
    week = request.args.get("week", _current_week())
    slots = list_meal_plan(g.user_id, week)

    start, end = _week_dates(week)
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    meals = ["breakfast", "lunch", "dinner"]

    grid = {}
    for day_idx, day in enumerate(days):
        date = start + timedelta(days=day_idx)
        grid[day] = {
            "date": date.strftime("%Y-%m-%d"),
            "display_date": date.strftime("%b %d"),
            "meals": {m: None for m in meals},
        }

    for slot in slots:
        sid = slot.get("slot_id", "")
        parts = sid.split("-")
        if len(parts) >= 4:
            day = parts[2]
            meal = parts[3]
            if day in grid and meal in grid[day]["meals"]:
                grid[day]["meals"][meal] = {
                    "slot_id": sid,
                    "recipe_id": slot.get("recipe_id"),
                    "recipe_title": slot.get("recipe_title"),
                    "servings": slot.get("servings", 1),
                }

    return jsonify({
        "success": True,
        "data": {
            "week": week,
            "start_date": start.strftime("%b %d"),
            "end_date": end.strftime("%b %d"),
            "grid": grid,
        }
    })


@meals_bp.route("/<slot_id>", methods=["PUT"])
def set_slot(slot_id):
    data = request.get_json()
    if not data or not data.get("recipe_id"):
        return jsonify({"success": False, "error": "recipe_id is required"}), 400

    recipe = get_recipe(data["recipe_id"])
    if not recipe:
        return jsonify({"success": False, "error": "Recipe not found"}), 404

    servings = data.get("servings", recipe.get("servings", 1))
    result = set_meal_slot(
        g.user_id, slot_id, recipe["recipe_id"],
        recipe.get("title", ""), servings,
    )
    return jsonify({"success": True, "data": result})


@meals_bp.route("/<slot_id>", methods=["DELETE"])
def remove_slot(slot_id):
    clear_meal_slot(g.user_id, slot_id)
    return jsonify({"success": True, "data": {"cleared": slot_id}})


@meals_bp.route("/grocery-preview", methods=["GET"])
def grocery_preview():
    week = request.args.get("week", _current_week())
    slots = list_meal_plan(g.user_id, week)

    if not slots:
        return jsonify({"success": True, "data": {"have_none": [], "have_partial": [], "have_enough": []}})

    aggregated = {}
    for slot in slots:
        recipe = get_recipe(slot.get("recipe_id", ""))
        if not recipe:
            continue
        servings_mult = (slot.get("servings", 1) or 1) / max(recipe.get("servings", 1) or 1, 1)
        for ing in recipe.get("ingredients", []):
            name = normalize_ingredient(ing.get("name", ""))
            if not name:
                continue
            qty = (ing.get("quantity", 1) or 1) * servings_mult
            unit = ing.get("unit", "count")
            if name in aggregated:
                aggregated[name]["needed"] += qty
            else:
                aggregated[name] = {"name": name, "needed": qty, "unit": unit}

    pantry_items = list_pantry(g.user_id)
    pantry_lookup = {}
    for pi in pantry_items:
        n = pi.get("name", "").lower().strip()
        pantry_lookup[n] = pi.get("quantity", 0)

    have_none = []
    have_partial = []
    have_enough = []

    for name, info in sorted(aggregated.items()):
        on_hand = pantry_lookup.get(name, 0)
        entry = {
            "name": info["name"],
            "needed": round(info["needed"], 2),
            "unit": info["unit"],
            "on_hand": on_hand,
        }
        if on_hand <= 0:
            entry["status"] = "need"
            have_none.append(entry)
        elif on_hand < info["needed"]:
            entry["status"] = "partial"
            entry["short"] = round(info["needed"] - on_hand, 2)
            have_partial.append(entry)
        else:
            entry["status"] = "enough"
            have_enough.append(entry)

    return jsonify({
        "success": True,
        "data": {
            "have_none": have_none,
            "have_partial": have_partial,
            "have_enough": have_enough,
        }
    })
