import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from config import DYNAMO_TABLES, AWS_REGION

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)


def _table(name):
    return dynamodb.Table(DYNAMO_TABLES[name])


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _new_id():
    return str(uuid.uuid4())


def _to_decimal(val):
    """DynamoDB requires Decimal for numbers."""
    if isinstance(val, float):
        return Decimal(str(val))
    if isinstance(val, int):
        return Decimal(val)
    return val


def _from_decimal(obj):
    """Convert Decimal back to int/float for JSON serialization."""
    if isinstance(obj, list):
        return [_from_decimal(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _from_decimal(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    if isinstance(obj, set):
        return list(obj)
    return obj


# ---------------------------------------------------------------------------
# Pantry
# ---------------------------------------------------------------------------

def list_pantry(user_id):
    resp = _table("pantry").query(
        KeyConditionExpression=Key("user_id").eq(user_id)
    )
    items = _from_decimal(resp.get("Items", []))
    return sorted(items, key=lambda x: (x.get("category", ""), x.get("name", "")))


def get_pantry_item(user_id, item_id):
    resp = _table("pantry").get_item(Key={"user_id": user_id, "item_id": item_id})
    return _from_decimal(resp.get("Item"))


def find_pantry_item_by_name(user_id, name):
    """Find pantry item by normalized name using the GSI."""
    resp = _table("pantry").query(
        IndexName="name-index",
        KeyConditionExpression=Key("user_id").eq(user_id) & Key("name").eq(name.lower().strip())
    )
    items = resp.get("Items", [])
    return _from_decimal(items[0]) if items else None


def add_pantry_item(user_id, name, quantity, unit, category, expiry_date=None):
    normalized_name = name.lower().strip()
    existing = find_pantry_item_by_name(user_id, normalized_name)

    if existing:
        new_qty = Decimal(str(existing["quantity"])) + Decimal(str(quantity))
        _table("pantry").update_item(
            Key={"user_id": user_id, "item_id": existing["item_id"]},
            UpdateExpression="SET quantity = :q",
            ExpressionAttributeValues={":q": new_qty},
        )
        existing["quantity"] = _from_decimal(new_qty)
        return _from_decimal(existing)

    item_id = _new_id()
    item = {
        "user_id": user_id,
        "item_id": item_id,
        "name": normalized_name,
        "quantity": _to_decimal(quantity),
        "unit": unit,
        "category": category.lower().strip() if category else "other",
        "added_at": _now_iso(),
    }
    if expiry_date:
        item["expiry_date"] = expiry_date

    _table("pantry").put_item(Item=item)
    return _from_decimal(item)


def update_pantry_item(user_id, item_id, updates):
    expr_parts = []
    expr_values = {}
    expr_names = {}

    for field in ["quantity", "unit", "expiry_date", "category", "name"]:
        if field in updates and updates[field] is not None:
            safe = f"#{field}"
            expr_names[safe] = field
            expr_parts.append(f"{safe} = :{field}")
            expr_values[f":{field}"] = _to_decimal(updates[field])

    if not expr_parts:
        return get_pantry_item(user_id, item_id)

    _table("pantry").update_item(
        Key={"user_id": user_id, "item_id": item_id},
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
    )
    return get_pantry_item(user_id, item_id)


def delete_pantry_item(user_id, item_id):
    _table("pantry").delete_item(Key={"user_id": user_id, "item_id": item_id})


def bulk_add_pantry(user_id, items):
    results = []
    for item in items:
        result = add_pantry_item(
            user_id,
            item["name"],
            item.get("quantity", 1),
            item.get("unit", "count"),
            item.get("category", "other"),
            item.get("expiry_date"),
        )
        results.append(result)
    return results


def get_pantry_categories(user_id):
    items = list_pantry(user_id)
    return sorted(set(item.get("category", "other") for item in items))


# ---------------------------------------------------------------------------
# Recipes
# ---------------------------------------------------------------------------

def get_recipe(recipe_id):
    resp = _table("recipes").get_item(Key={"recipe_id": recipe_id})
    return _from_decimal(resp.get("Item"))


def list_recipes(limit=20, offset=0):
    resp = _table("recipes").scan()
    items = resp.get("Items", [])
    while resp.get("LastEvaluatedKey"):
        resp = _table("recipes").scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))
    items = _from_decimal(items)
    items.sort(key=lambda x: x.get("title", ""))
    return items[offset:offset + limit], len(items)


_recipe_cache = {"data": None, "expires": 0}


def list_all_recipes_cached():
    """Return all recipes, cached in memory for 5 minutes."""
    import time
    now = time.time()
    if _recipe_cache["data"] is not None and now < _recipe_cache["expires"]:
        return _recipe_cache["data"]

    resp = _table("recipes").scan()
    items = resp.get("Items", [])
    while resp.get("LastEvaluatedKey"):
        resp = _table("recipes").scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))

    items = _from_decimal(items)
    _recipe_cache["data"] = items
    _recipe_cache["expires"] = now + 300
    return items


def create_recipe(title, ingredients, instructions="", cuisine="", tags=None, prep_time_mins=0, servings=4):
    """Create a new recipe from user input."""
    recipe_id = _new_id()
    recipe = {
        "recipe_id": recipe_id,
        "title": title.strip(),
        "ingredients": [
            {
                "name": ing.get("name", "").lower().strip(),
                "quantity": _to_decimal(ing.get("quantity", 1)),
                "unit": ing.get("unit", "count"),
            }
            for ing in ingredients if ing.get("name")
        ],
        "instructions": instructions.strip(),
        "cuisine": cuisine.strip(),
        "prep_time_mins": _to_decimal(prep_time_mins),
        "servings": _to_decimal(servings),
        "created_at": _now_iso(),
    }
    if tags:
        recipe["tags"] = set(tags)
    _table("recipes").put_item(Item=recipe)
    _recipe_cache["data"] = None
    return _from_decimal(recipe)


def put_recipe(recipe):
    """Write a recipe item (used by seeding script)."""
    clean = {}
    for k, v in recipe.items():
        if v is not None and v != "" and v != []:
            clean[k] = _to_decimal(v) if isinstance(v, (int, float)) else v
    if "ingredients" in clean:
        clean["ingredients"] = [
            {ik: _to_decimal(iv) if isinstance(iv, (int, float)) else iv for ik, iv in ing.items()}
            for ing in clean["ingredients"]
        ]
    _table("recipes").put_item(Item=clean)


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------

def is_favorite(user_id, recipe_id):
    resp = _table("favorites").get_item(Key={"user_id": user_id, "recipe_id": recipe_id})
    return resp.get("Item") is not None


def toggle_favorite(user_id, recipe_id):
    if is_favorite(user_id, recipe_id):
        _table("favorites").delete_item(Key={"user_id": user_id, "recipe_id": recipe_id})
        return False
    _table("favorites").put_item(Item={
        "user_id": user_id,
        "recipe_id": recipe_id,
        "favorited_at": _now_iso(),
    })
    return True


def list_favorites(user_id):
    resp = _table("favorites").query(
        KeyConditionExpression=Key("user_id").eq(user_id)
    )
    fav_items = _from_decimal(resp.get("Items", []))
    recipes = []
    for fav in fav_items:
        recipe = get_recipe(fav["recipe_id"])
        if recipe:
            recipe["is_favorite"] = True
            recipe["favorited_at"] = fav.get("favorited_at")
            recipes.append(recipe)
    return recipes


def get_user_favorite_ids(user_id):
    resp = _table("favorites").query(
        KeyConditionExpression=Key("user_id").eq(user_id),
        ProjectionExpression="recipe_id",
    )
    return {item["recipe_id"] for item in resp.get("Items", [])}


# ---------------------------------------------------------------------------
# Grocery Lists
# ---------------------------------------------------------------------------

def list_grocery(user_id):
    resp = _table("grocery").query(
        KeyConditionExpression=Key("user_id").eq(user_id)
    )
    items = _from_decimal(resp.get("Items", []))
    unchecked = sorted([i for i in items if not i.get("checked")], key=lambda x: x.get("name", ""))
    checked = sorted([i for i in items if i.get("checked")], key=lambda x: x.get("name", ""))
    return unchecked + checked


def add_grocery_item(user_id, name, quantity, unit, source="manual", recipe_id=None):
    normalized = name.lower().strip()
    existing = list_grocery(user_id)
    for item in existing:
        if item.get("name", "").lower().strip() == normalized:
            return _from_decimal(item)

    item_id = _new_id()
    item = {
        "user_id": user_id,
        "item_id": item_id,
        "name": normalized,
        "quantity": _to_decimal(quantity),
        "unit": unit,
        "checked": False,
        "source": source,
        "added_at": _now_iso(),
    }
    if recipe_id:
        item["recipe_id"] = recipe_id
    _table("grocery").put_item(Item=item)
    return _from_decimal(item)


def update_grocery_item(user_id, item_id, updates):
    expr_parts = []
    expr_values = {}
    expr_names = {}

    for field in ["checked", "quantity", "unit", "name"]:
        if field in updates:
            safe = f"#{field}"
            expr_names[safe] = field
            expr_parts.append(f"{safe} = :{field}")
            val = updates[field]
            expr_values[f":{field}"] = _to_decimal(val) if isinstance(val, (int, float)) else val

    if not expr_parts:
        return None

    _table("grocery").update_item(
        Key={"user_id": user_id, "item_id": item_id},
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
    )
    resp = _table("grocery").get_item(Key={"user_id": user_id, "item_id": item_id})
    return _from_decimal(resp.get("Item"))


def delete_grocery_item(user_id, item_id):
    _table("grocery").delete_item(Key={"user_id": user_id, "item_id": item_id})


def delete_checked_grocery(user_id):
    items = list_grocery(user_id)
    count = 0
    for item in items:
        if item.get("checked"):
            delete_grocery_item(user_id, item["item_id"])
            count += 1
    return count


def get_checked_grocery(user_id):
    items = list_grocery(user_id)
    return [i for i in items if i.get("checked")]


# ---------------------------------------------------------------------------
# Meal Plans
# ---------------------------------------------------------------------------

def list_meal_plan(user_id, week):
    """List all meal plan slots for a given week (YYYY-WW format)."""
    resp = _table("meal_plans").query(
        KeyConditionExpression=Key("user_id").eq(user_id) & Key("slot_id").begins_with(week)
    )
    return _from_decimal(resp.get("Items", []))


def set_meal_slot(user_id, slot_id, recipe_id, recipe_title, servings):
    item = {
        "user_id": user_id,
        "slot_id": slot_id,
        "recipe_id": recipe_id,
        "recipe_title": recipe_title,
        "servings": _to_decimal(servings),
    }
    _table("meal_plans").put_item(Item=item)
    return _from_decimal(item)


def clear_meal_slot(user_id, slot_id):
    _table("meal_plans").delete_item(Key={"user_id": user_id, "slot_id": slot_id})
