import json
import logging

from flask import Blueprint, request, jsonify, g

from services.dynamo import (
    list_recipes, get_recipe, list_all_recipes_cached, create_recipe,
    list_pantry, toggle_favorite, list_favorites, get_user_favorite_ids,
)
from services.matching import score_recipe
from services.opensearch import search_recipes as os_search
from services.bedrock import get_smart_grocery_suggestions, call_bedrock

logger = logging.getLogger("pantryai")
recipes_bp = Blueprint("recipes", __name__, url_prefix="/api/recipes")


@recipes_bp.route("", methods=["GET"])
def get_recipes():
    limit = request.args.get("limit", 20, type=int)
    offset = request.args.get("offset", 0, type=int)
    items, total = list_recipes(limit=limit, offset=offset)
    return jsonify({"success": True, "data": items, "total": total})


@recipes_bp.route("", methods=["POST"])
def add_recipe():
    data = request.get_json()
    if not data or not data.get("title"):
        return jsonify({"success": False, "error": "Title is required"}), 400
    if not data.get("ingredients") or not isinstance(data["ingredients"], list):
        return jsonify({"success": False, "error": "At least one ingredient is required"}), 400

    recipe = create_recipe(
        title=data["title"],
        ingredients=data["ingredients"],
        instructions=data.get("instructions", ""),
        cuisine=data.get("cuisine", ""),
        tags=data.get("tags", []),
        prep_time_mins=data.get("prep_time_mins", 0),
        servings=data.get("servings", 4),
        image_url=data.get("image_url", ""),
    )
    return jsonify({"success": True, "data": recipe}), 201


@recipes_bp.route("/generate", methods=["POST"])
def generate_recipes():
    data = request.get_json()
    titles = data.get("titles", []) if data else []
    if not titles or not isinstance(titles, list):
        return jsonify({"success": False, "error": "titles array is required"}), 400
    titles = [t.strip() for t in titles if t.strip()][:10]
    if not titles:
        return jsonify({"success": False, "error": "No valid titles provided"}), 400

    logger.info(f"Generating {len(titles)} recipes: {titles}")

    prompt = f"""Generate complete recipes for these dishes. For each recipe provide:
- title (use the exact title given)
- cuisine (best guess)
- prep_time_mins (realistic estimate)
- servings (default 4)
- ingredients: array of objects with name, quantity (number), unit
- instructions: step-by-step as a single string with "Step 1: ... Step 2: ..." format

Dishes:
{json.dumps(titles)}

Return ONLY a JSON object with a "recipes" array. No markdown, no explanation.
Example format:
{{"recipes": [{{"title": "...", "cuisine": "...", "prep_time_mins": 30, "servings": 4, "ingredients": [{{"name": "chicken breast", "quantity": 2, "unit": "lb"}}], "instructions": "Step 1: ..."}}]}}"""

    try:
        raw = call_bedrock(prompt, max_tokens=8192)
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        parsed = json.loads(text)
        recipe_defs = parsed.get("recipes", [])
        logger.info(f"Bedrock returned {len(recipe_defs)} recipe definitions")
    except Exception as e:
        logger.error(f"Recipe generation Bedrock error: {e}")
        return jsonify({"success": False, "error": "Failed to generate recipes"}), 500

    created = []
    for rd in recipe_defs:
        ings = rd.get("ingredients", [])
        if not ings:
            logger.warning(f"Skipping recipe '{rd.get('title')}' — no ingredients")
            continue
        try:
            recipe = create_recipe(
                title=rd.get("title", "Untitled"),
                ingredients=ings,
                instructions=rd.get("instructions", ""),
                cuisine=rd.get("cuisine", ""),
                prep_time_mins=rd.get("prep_time_mins", 0),
                servings=rd.get("servings", 4),
            )
            created.append(recipe)
            logger.info(f"Created recipe: {recipe.get('title')} ({recipe.get('recipe_id')})")
        except Exception as e:
            logger.error(f"Failed to save generated recipe '{rd.get('title')}': {e}")

    logger.info(f"Generate endpoint done: {len(created)} created out of {len(titles)} requested")
    return jsonify({"success": True, "data": created}), 201


def _score_search_results(results, user_id):
    """Add pantry match scores to a list of search results."""
    pantry_items = list_pantry(user_id)
    fav_ids = get_user_favorite_ids(user_id)
    scored = []
    for r in results:
        ingredients = r.get("ingredients", [])
        if ingredients:
            result = score_recipe(pantry_items, ingredients)
            r["match_score"] = result["score"]
            r["matched_ingredients"] = result["matched"]
            r["missing_ingredients"] = result["missing"]
        else:
            r["match_score"] = 0
            r["matched_ingredients"] = []
            r["missing_ingredients"] = []
        r["is_favorite"] = r.get("recipe_id", "") in fav_ids
        scored.append(r)
    return scored


@recipes_bp.route("/search", methods=["GET"])
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"success": True, "data": []})

    limit = request.args.get("limit", 20, type=int)
    results = os_search(q, limit=limit)

    if results:
        full_results = []
        for hit in results:
            recipe = get_recipe(hit["recipe_id"])
            if recipe:
                full_results.append(recipe)
        results = full_results
    else:
        all_recipes, _ = list_recipes(limit=500, offset=0)
        q_lower = q.lower()
        results = [
            r for r in all_recipes
            if q_lower in r.get("title", "").lower()
            or any(q_lower in ing.get("name", "").lower() for ing in r.get("ingredients", []))
        ][:limit]

    results = _score_search_results(results[:limit], g.user_id)
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


@recipes_bp.route("/import-url", methods=["POST"])
def import_from_url():
    """Fetch a URL, extract recipe data via Bedrock, return structured recipe for the form."""
    import requests as http_requests
    data = request.get_json()
    url = (data.get("url") or "").strip() if data else ""
    if not url:
        return jsonify({"success": False, "error": "URL is required"}), 400

    logger.info(f"Importing recipe from URL: {url}")
    try:
        resp = http_requests.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        page_text = resp.text
        if len(page_text) < 500:
            raise ValueError(f"Page too short ({len(page_text)} chars), likely blocked")
        page_text = page_text[:30000]
    except Exception as e:
        logger.error(f"Failed to fetch URL: {e}")
        return jsonify({"success": False, "error": "Could not fetch that URL"}), 400

    prompt = f"""Extract the recipe from this webpage HTML. Return ONLY a JSON object with these fields:
- title (string)
- cuisine (string, best guess)
- prep_time_mins (number)
- servings (number)
- ingredients: array of objects with name (string), quantity (number), unit (string)
- instructions (string, step-by-step with "Step 1: ... Step 2: ..." format)
- image_url (string, the main recipe image URL from the page, or null if not found)

If this page does not contain a recipe, return {{"error": "No recipe found on this page"}}.
Return ONLY valid JSON, no markdown, no explanation.

WEBPAGE CONTENT:
{page_text}"""

    try:
        raw = call_bedrock(prompt, max_tokens=4096)
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        parsed = json.loads(text)
        if "error" in parsed:
            return jsonify({"success": False, "error": parsed["error"]}), 400
        logger.info(f"Imported recipe: {parsed.get('title')}")
        return jsonify({"success": True, "data": parsed})
    except Exception as e:
        logger.error(f"Recipe import Bedrock error: {e}")
        return jsonify({"success": False, "error": "Failed to parse recipe from page"}), 500


@recipes_bp.route("/<recipe_id>/image", methods=["GET"])
def recipe_image(recipe_id):
    """Return the image URL stored on the recipe record."""
    recipe = get_recipe(recipe_id)
    if not recipe:
        return jsonify({"success": True, "data": {"image_url": None}})

    image_url = recipe.get("image_url") or recipe.get("thumb") or None
    return jsonify({"success": True, "data": {"image_url": image_url}})


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
