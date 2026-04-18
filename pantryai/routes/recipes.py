import logging

from flask import Blueprint, request, jsonify, g

from services.dynamo import (
    list_recipes, get_recipe, list_all_recipes_cached,
    list_pantry, toggle_favorite, list_favorites, get_user_favorite_ids,
)
from services.matching import score_recipe
from services.opensearch import search_recipes as os_search
from services.bedrock import get_smart_grocery_suggestions

logger = logging.getLogger("pantryai")
recipes_bp = Blueprint("recipes", __name__, url_prefix="/api/recipes")


@recipes_bp.route("", methods=["GET"])
def get_recipes():
    limit = request.args.get("limit", 20, type=int)
    offset = request.args.get("offset", 0, type=int)
    items, total = list_recipes(limit=limit, offset=offset)
    return jsonify({"success": True, "data": items, "total": total})


@recipes_bp.route("/search", methods=["GET"])
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"success": True, "data": []})

    limit = request.args.get("limit", 20, type=int)
    results = os_search(q, limit=limit)

    if not results:
        all_recipes, _ = list_recipes(limit=500, offset=0)
        q_lower = q.lower()
        results = [
            r for r in all_recipes
            if q_lower in r.get("title", "").lower()
            or any(q_lower in ing.get("name", "").lower() for ing in r.get("ingredients", []))
        ][:limit]

    return jsonify({"success": True, "data": results})


@recipes_bp.route("/matches", methods=["GET"])
def matches():
    pantry_items = list_pantry(g.user_id)
    all_recipes = list_all_recipes_cached()
    fav_ids = get_user_favorite_ids(g.user_id)

    scored = []
    for recipe in all_recipes:
        ingredients = recipe.get("ingredients", [])
        if not ingredients:
            continue
        result = score_recipe(pantry_items, ingredients)
        scored.append({
            **recipe,
            "match_score": result["score"],
            "matched_ingredients": result["matched"],
            "missing_ingredients": result["missing"],
            "is_favorite": recipe.get("recipe_id") in fav_ids,
        })

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return jsonify({"success": True, "data": scored[:50]})


@recipes_bp.route("/near-matches", methods=["GET"])
def near_matches():
    max_missing = request.args.get("max_missing", 4, type=int)
    max_missing = min(max(1, max_missing), 10)

    pantry_items = list_pantry(g.user_id)
    all_recipes = list_all_recipes_cached()
    fav_ids = get_user_favorite_ids(g.user_id)

    results = []
    for recipe in all_recipes:
        ingredients = recipe.get("ingredients", [])
        if not ingredients:
            continue
        result = score_recipe(pantry_items, ingredients)
        n_missing = len(result["missing"])
        if 1 <= n_missing <= max_missing:
            results.append({
                **recipe,
                "match_score": result["score"],
                "matched_ingredients": result["matched"],
                "missing_ingredients": result["missing"],
                "missing_count": n_missing,
                "is_favorite": recipe.get("recipe_id") in fav_ids,
            })

    results.sort(key=lambda x: (x["missing_count"], -x["match_score"]))
    return jsonify({"success": True, "data": results[:50]})


@recipes_bp.route("/smart-suggestions", methods=["GET"])
def smart_suggestions():
    pantry_items = list_pantry(g.user_id)
    all_recipes = list_all_recipes_cached()

    missing_by_recipe = {}
    for recipe in all_recipes:
        ingredients = recipe.get("ingredients", [])
        if not ingredients:
            continue
        result = score_recipe(pantry_items, ingredients)
        if 1 <= len(result["missing"]) <= 4:
            missing_by_recipe[recipe.get("title", "Unknown")] = [
                ing.get("name", "") for ing in result["missing"]
            ]

    if not missing_by_recipe:
        return jsonify({"success": True, "data": []})

    suggestions = get_smart_grocery_suggestions(missing_by_recipe)
    return jsonify({"success": True, "data": suggestions})


@recipes_bp.route("/<recipe_id>", methods=["GET"])
def get_recipe_detail(recipe_id):
    recipe = get_recipe(recipe_id)
    if not recipe:
        return jsonify({"success": False, "error": "Recipe not found"}), 404
    recipe["is_favorite"] = recipe_id in get_user_favorite_ids(g.user_id)
    return jsonify({"success": True, "data": recipe})


@recipes_bp.route("/<recipe_id>/favorite", methods=["POST"])
def favorite(recipe_id):
    recipe = get_recipe(recipe_id)
    if not recipe:
        return jsonify({"success": False, "error": "Recipe not found"}), 404
    is_fav = toggle_favorite(g.user_id, recipe_id)
    return jsonify({"success": True, "data": {"is_favorite": is_fav}})


@recipes_bp.route("/favorites", methods=["GET"])
def get_favorites():
    recipes = list_favorites(g.user_id)
    return jsonify({"success": True, "data": recipes})
