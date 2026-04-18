import logging

from flask import Blueprint, request, jsonify, g

from services.dynamo import (
    list_grocery, add_grocery_item, update_grocery_item,
    delete_grocery_item, delete_checked_grocery, get_checked_grocery,
    bulk_add_pantry, get_recipe, list_pantry, list_meal_plan,
)
from services.matching import score_recipe, normalize_ingredient

logger = logging.getLogger("pantryai")
grocery_bp = Blueprint("grocery", __name__, url_prefix="/api/grocery")


@grocery_bp.route("", methods=["GET"])
def get_grocery():
    items = list_grocery(g.user_id)
    return jsonify({"success": True, "data": items})


@grocery_bp.route("", methods=["POST"])
def create_item():
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"success": False, "error": "Name is required"}), 400

    item = add_grocery_item(
        user_id=g.user_id,
        name=data["name"],
        quantity=data.get("quantity", 1),
        unit=data.get("unit", "count"),
        source=data.get("source", "manual"),
        recipe_id=data.get("recipe_id"),
    )
    return jsonify({"success": True, "data": item}), 201


@grocery_bp.route("/<item_id>", methods=["PUT"])
def update_item(item_id):
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No update data provided"}), 400
    item = update_grocery_item(g.user_id, item_id, data)
    if not item:
        return jsonify({"success": False, "error": "Item not found"}), 404
    return jsonify({"success": True, "data": item})


@grocery_bp.route("/<item_id>", methods=["DELETE"])
def remove_item(item_id):
    delete_grocery_item(g.user_id, item_id)
    return jsonify({"success": True, "data": {"deleted": item_id}})


@grocery_bp.route("/checked", methods=["DELETE"])
def clear_checked():
    count = delete_checked_grocery(g.user_id)
    return jsonify({"success": True, "data": {"cleared": count}})


@grocery_bp.route("/all", methods=["DELETE"])
def clear_all():
    items = list_grocery(g.user_id)
    for item in items:
        delete_grocery_item(g.user_id, item["item_id"])
    return jsonify({"success": True, "data": {"cleared": len(items)}})


@grocery_bp.route("/from-recipe/<recipe_id>", methods=["POST"])
def from_recipe(recipe_id):
    recipe = get_recipe(recipe_id)
    if not recipe:
        return jsonify({"success": False, "error": "Recipe not found"}), 404

    pantry_items = list_pantry(g.user_id)
    result = score_recipe(pantry_items, recipe.get("ingredients", []))
    added = []

    for ing in result["missing"]:
        item = add_grocery_item(
            user_id=g.user_id,
            name=ing.get("name", ""),
            quantity=ing.get("quantity", 1),
            unit=ing.get("unit", "count"),
            source="recipe",
            recipe_id=recipe_id,
        )
        added.append(item)

    return jsonify({"success": True, "data": {"added": len(added), "items": added}})


@grocery_bp.route("/from-meal-plan", methods=["POST"])
def from_meal_plan():
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    week = f"{now.isocalendar()[0]}-{now.isocalendar()[1]:02d}"
    data = request.get_json() or {}
    week = data.get("week", week)

    slots = list_meal_plan(g.user_id, week)
    if not slots:
        return jsonify({"success": True, "data": {"added": 0, "already_in_stock": 0, "already_on_list": 0}})

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
                aggregated[name]["quantity"] += qty
            else:
                aggregated[name] = {"name": name, "quantity": qty, "unit": unit}

    pantry_items = list_pantry(g.user_id)
    pantry_lookup = {}
    for pi in pantry_items:
        pantry_lookup[pi.get("name", "").lower().strip()] = pi

    existing_grocery = list_grocery(g.user_id)
    existing_names = {item.get("name", "").lower().strip() for item in existing_grocery}

    added = 0
    already_in_stock = 0
    already_on_list = 0

    for name, info in aggregated.items():
        if name in pantry_lookup:
            p = pantry_lookup[name]
            if p.get("quantity", 0) >= info["quantity"]:
                already_in_stock += 1
                continue

        if name in existing_names:
            already_on_list += 1
            continue

        add_grocery_item(
            user_id=g.user_id,
            name=info["name"],
            quantity=round(info["quantity"], 2),
            unit=info["unit"],
            source="meal_plan",
        )
        added += 1

    return jsonify({
        "success": True,
        "data": {
            "added": added,
            "already_in_stock": already_in_stock,
            "already_on_list": already_on_list,
        }
    })


@grocery_bp.route("/to-pantry", methods=["POST"])
def to_pantry():
    checked_items = get_checked_grocery(g.user_id)
    if not checked_items:
        return jsonify({"success": True, "data": {"moved": 0}})

    pantry_items = [
        {
            "name": item.get("name", ""),
            "quantity": item.get("quantity", 1),
            "unit": item.get("unit", "count"),
            "category": "other",
        }
        for item in checked_items
    ]
    bulk_add_pantry(g.user_id, pantry_items)

    for item in checked_items:
        delete_grocery_item(g.user_id, item["item_id"])

    return jsonify({"success": True, "data": {"moved": len(checked_items)}})
