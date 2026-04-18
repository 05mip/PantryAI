"""
Seed script (by category, parallelized): fetches recipes from TheMealDB API,
writes to DynamoDB + OpenSearch.

Run: python seed_recipes1_parallel.py
"""

from dotenv import load_dotenv
load_dotenv()

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from services.dynamo import put_recipe
from services.opensearch import bulk_index_recipes

from seed_recipes import parse_meal

BASE_URL = "https://www.themealdb.com/api/json/v1/1"
MAX_WORKERS = 12  # tune this (8–20 is usually safe)


def log(msg):
    print(msg, flush=True)


def get_categories():
    resp = requests.get(f"{BASE_URL}/categories.php", timeout=15)
    resp.raise_for_status()
    return [c["strCategory"] for c in resp.json().get("categories", [])]


def get_meals_by_category(category):
    resp = requests.get(f"{BASE_URL}/filter.php?c={category}", timeout=15)
    resp.raise_for_status()
    return resp.json().get("meals") or []


def get_meal_details(meal_id):
    resp = requests.get(f"{BASE_URL}/lookup.php?i={meal_id}", timeout=15)
    resp.raise_for_status()
    meals = resp.json().get("meals") or []
    return meals[0] if meals else None


def process_meal(meal_id):
    """
    Worker function for threads.
    Returns (recipe, title, error)
    """
    try:
        meal = get_meal_details(meal_id)
        if not meal:
            return None, None, f"no details for {meal_id}"

        recipe, _ = parse_meal(meal)
        title = recipe["title"]

        if not recipe["ingredients"]:
            return None, title, "no ingredients"

        return recipe, title, None

    except Exception as e:
        return None, None, str(e)


def main():
    all_recipes = []
    seen_titles = set()
    seen_ids = set()
    failed = 0

    # thread-safe lock for shared sets
    lock = Lock()

    log("Starting recipe seed (parallel, by category)...")
    log("")

    try:
        categories = get_categories()
    except Exception as e:
        log(f"Failed to fetch categories: {e}")
        return

    log(f"Found {len(categories)} categories")
    log("")

    # collect ALL meal IDs first (dedupe early)
    all_meal_ids = set()

    for category in categories:
        log(f"[{category}] Fetching...")
        try:
            meals = get_meals_by_category(category)
            ids = [m["idMeal"] for m in meals if m.get("idMeal")]
            all_meal_ids.update(ids)
            log(f"[{category}] +{len(ids)} meals")
        except Exception as e:
            log(f"[{category}] ERROR: {e}")

    log("")
    log(f"Total unique meal IDs: {len(all_meal_ids)}")
    log("Starting parallel fetch...")
    log("")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_meal, meal_id): meal_id
            for meal_id in all_meal_ids
        }

        for future in as_completed(futures):
            meal_id = futures[future]

            try:
                recipe, title, error = future.result()
            except Exception as e:
                log(f"FAIL (future crash): {meal_id} — {e}")
                failed += 1
                continue

            if error:
                log(f"SKIP: {meal_id} — {error}")
                continue

            # dedupe safely
            with lock:
                if meal_id in seen_ids:
                    continue
                if title in seen_titles:
                    continue
                seen_ids.add(meal_id)
                seen_titles.add(title)

            try:
                put_recipe(recipe)
                all_recipes.append(recipe)

                log(
                    f"OK: {title} "
                    f"({len(recipe['ingredients'])} ingredients, "
                    f"cuisine={recipe.get('cuisine', '?')})"
                )

            except Exception as e:
                failed += 1
                log(f"FAIL (db): {title} — {e}")

    log("")
    log("=" * 60)
    log(f"Seeding complete: {len(all_recipes)} recipes written, {failed} failed")
    log(f"Unique titles: {len(seen_titles)}, unique IDs: {len(seen_ids)}")

    if all_recipes:
        log("Indexing to OpenSearch...")
        try:
            for r in all_recipes:
                if isinstance(r.get("tags"), set):
                    r["tags"] = list(r["tags"])
            bulk_index_recipes(all_recipes)
            log("OpenSearch indexing complete.")
        except Exception as e:
            log(f"OpenSearch indexing failed: {e}")

    log("Done.")


if __name__ == "__main__":
    main()