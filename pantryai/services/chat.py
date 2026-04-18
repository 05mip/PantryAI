import json
import logging
import traceback
import uuid
from datetime import datetime, timezone

from services.bedrock import call_bedrock_conversation
from services.dynamo import (
    list_pantry, list_grocery, list_meal_plan,
    get_user_favorite_ids, list_all_recipes_cached,
)
from services.matching import score_recipe

logger = logging.getLogger("pantryai")

_conversations = {}
MAX_HISTORY = 10

SYSTEM_PROMPT_TEMPLATE = """You are Chef Charlie, a friendly and knowledgeable kitchen assistant inside the PantryAI app. You help users plan meals, manage their pantry, build grocery lists, and discover recipes.

You have access to the user's current app data, provided below as context. Use this data to give personalized, actionable advice.

CURRENT PANTRY:
{pantry_json}

CURRENT GROCERY LIST:
{grocery_json}

THIS WEEK'S MEAL PLAN:
{meal_plan_json}

RECIPE DATABASE (top matches for user's pantry):
{recipes_json}

FAVORITED RECIPE IDs:
{favorites_json}

RULES:
1. Always consider what the user already has in their pantry before suggesting purchases.
2. When proposing a meal plan, return it as a structured block (see format below).
3. When proposing grocery items, return them as a structured block.
4. When creating a new recipe, return it as a structured recipe block with full ingredients (name, quantity, unit) and step-by-step instructions.
5. For substitution questions, explain the substitute, the ratio, and any flavor/texture differences.
6. Be concise but warm. Use a casual, encouraging tone. You're a friendly chef, not a textbook.
7. If the user asks you to do something (add to grocery list, fill meal plan, save a recipe), propose it first and let them confirm — never say you did it directly.
8. When suggesting a meal plan, try to minimize grocery purchases by reusing pantry ingredients across meals.
9. For bulking/cutting/dietary goals, adjust macros accordingly and mention approximate protein/calories when relevant.
10. You can mix text blocks with action blocks in a single response.

RESPONSE FORMAT:
You must return a JSON object with a "blocks" array. Each block is one of:
- {{"type": "text", "content": "Your message here"}}
- {{"type": "meal_plan_proposal", "data": {{"Mon": {{"breakfast": {{"title": "...", "recipe_id": null, "servings": 1}}, "lunch": {{...}}, "dinner": {{...}}}}, "Tue": {{...}}, "Wed": {{...}}, "Thu": {{...}}, "Fri": {{...}}, "Sat": {{...}}, "Sun": {{...}}}}}}
- {{"type": "grocery_proposal", "data": {{"items": [{{"name": "...", "quantity": 1, "unit": "count"}}]}}}}
- {{"type": "recipe_proposal", "data": {{"title": "...", "cuisine": "...", "prep_time_mins": 30, "servings": 4, "ingredients": [{{"name": "...", "quantity": 1, "unit": "count"}}], "instructions": "Step 1: ...\\nStep 2: ..."}}}}
- {{"type": "substitution", "data": {{"original": "...", "substitute": "...", "ratio": "1:1", "notes": "..."}}}}

Return ONLY the JSON object. No markdown fences, no explanation outside the blocks."""


def _get_current_week():
    now = datetime.now(timezone.utc)
    iso = now.isocalendar()
    return f"{iso[0]}-{iso[1]:02d}"


def _build_system_prompt(user_id):
    pantry = list_pantry(user_id)
    pantry_summary = [
        {"name": i.get("name", ""), "qty": i.get("quantity", 0), "unit": i.get("unit", ""), "category": i.get("category", "")}
        for i in pantry
    ]

    grocery = list_grocery(user_id)
    grocery_summary = [
        {"name": i.get("name", ""), "qty": i.get("quantity", 0), "unit": i.get("unit", ""), "checked": i.get("checked", False)}
        for i in grocery
    ]

    week = _get_current_week()
    meal_slots = list_meal_plan(user_id, week)
    meal_summary = [
        {"slot": s.get("slot_id", ""), "recipe": s.get("recipe_title", ""), "servings": s.get("servings", 1)}
        for s in meal_slots
    ]

    fav_ids = list(get_user_favorite_ids(user_id))

    all_recipes = list_all_recipes_cached()
    scored = []
    for r in all_recipes:
        ings = r.get("ingredients", [])
        if not ings:
            continue
        result = score_recipe(pantry, ings)
        scored.append({
            "recipe_id": r.get("recipe_id"),
            "title": r.get("title", ""),
            "cuisine": r.get("cuisine", ""),
            "score": result["score"],
            "missing_count": len(result["missing"]),
            "ingredients": [ing.get("name", "") for ing in ings],
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    top_recipes = scored[:50]

    return SYSTEM_PROMPT_TEMPLATE.format(
        pantry_json=json.dumps(pantry_summary, indent=1),
        grocery_json=json.dumps(grocery_summary, indent=1),
        meal_plan_json=json.dumps(meal_summary, indent=1),
        recipes_json=json.dumps(top_recipes, indent=1),
        favorites_json=json.dumps(fav_ids),
    )


def _parse_response(raw_text):
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "blocks" in parsed:
            return parsed["blocks"]
        if isinstance(parsed, list):
            return parsed
        return [{"type": "text", "content": text}]
    except json.JSONDecodeError:
        return [{"type": "text", "content": text}]


def chat(user_id, message, conversation_id=None):
    if not conversation_id:
        conversation_id = str(uuid.uuid4())

    if conversation_id not in _conversations:
        _conversations[conversation_id] = []

    history = _conversations[conversation_id]
    history.append({"role": "user", "content": message})

    if len(history) > MAX_HISTORY * 2:
        history[:] = history[-(MAX_HISTORY * 2):]

    try:
        system_prompt = _build_system_prompt(user_id)
        logger.info("Chef Charlie: context gathered, calling Bedrock...")
    except Exception as e:
        logger.error(f"Chef Charlie context-gathering error: {e}\n{traceback.format_exc()}")
        history.pop()
        return {
            "conversation_id": conversation_id,
            "blocks": [{"type": "text", "content": "Sorry, I'm having trouble thinking right now. Try again in a moment!"}],
        }

    try:
        raw = call_bedrock_conversation(system_prompt, history)
        logger.info(f"Chef Charlie: Bedrock responded ({len(raw)} chars)")
        blocks = _parse_response(raw)
        history.append({"role": "assistant", "content": raw})
        return {"conversation_id": conversation_id, "blocks": blocks}
    except Exception as e:
        logger.error(f"Chef Charlie Bedrock error: {e}\n{traceback.format_exc()}")
        history.pop()
        return {
            "conversation_id": conversation_id,
            "blocks": [{"type": "text", "content": "Sorry, I'm having trouble thinking right now. Try again in a moment!"}],
        }
