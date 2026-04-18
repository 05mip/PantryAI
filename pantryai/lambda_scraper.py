"""
AWS Lambda function: SQS-triggered recipe scraper.
Receives URLs from pai-scrape-queue, fetches recipe data, writes to DynamoDB + OpenSearch.

Deploy as a Lambda with:
  - Runtime: Python 3.11
  - Trigger: SQS queue (pai-scrape-queue)
  - Env vars: same as Flask app (AWS_REGION, OPENSEARCH_ENDPOINT, etc.)
  - Layer: include boto3, requests, opensearch-py
"""
import json
import logging
import re
import uuid
from datetime import datetime, timezone

import boto3
import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DYNAMO_TABLE = "pai-recipes"
S3_BUCKET = "pai-recipe-images"
AWS_REGION = "us-west-2"

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
s3 = boto3.client("s3", region_name=AWS_REGION)
table = dynamodb.Table(DYNAMO_TABLE)


def handler(event, context):
    records = event.get("Records", [])
    logger.info(f"Processing {len(records)} SQS messages")

    for record in records:
        try:
            body = json.loads(record["body"])
            url = body.get("url", "")
            if not url:
                logger.warning("Empty URL in message, skipping")
                continue

            logger.info(f"Scraping recipe from: {url}")
            recipe = scrape_recipe(url)
            if recipe:
                write_recipe(recipe)
                logger.info(f"Successfully scraped: {recipe.get('title', 'Unknown')}")
            else:
                logger.warning(f"Failed to extract recipe from: {url}")

        except Exception as e:
            logger.error(f"Error processing message: {e}")

    return {"statusCode": 200, "body": f"Processed {len(records)} messages"}


def scrape_recipe(url):
    """
    Attempt to scrape recipe data from a URL.
    Looks for JSON-LD schema.org Recipe markup first, then falls back to basic extraction.
    """
    try:
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "PantryAI Recipe Scraper/1.0"
        })
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        logger.error(f"HTTP request failed for {url}: {e}")
        return None

    json_ld = extract_json_ld_recipe(html)
    if json_ld:
        return normalize_json_ld(json_ld, url)

    return None


def extract_json_ld_recipe(html):
    pattern = re.compile(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        try:
            data = json.loads(match.group(1))
            if isinstance(data, list):
                for item in data:
                    if item.get("@type") == "Recipe":
                        return item
            elif isinstance(data, dict):
                if data.get("@type") == "Recipe":
                    return data
                graph = data.get("@graph", [])
                for item in graph:
                    if isinstance(item, dict) and item.get("@type") == "Recipe":
                        return item
        except json.JSONDecodeError:
            continue
    return None


def normalize_json_ld(data, source_url):
    recipe_id = str(uuid.uuid4())
    title = data.get("name", "").strip()
    if not title:
        return None

    raw_ingredients = data.get("recipeIngredient", [])
    ingredients = []
    for ing in raw_ingredients:
        if isinstance(ing, str):
            ingredients.append({"name": ing.lower().strip(), "quantity": 1, "unit": "count"})

    instructions_raw = data.get("recipeInstructions", [])
    instructions = ""
    if isinstance(instructions_raw, str):
        instructions = instructions_raw
    elif isinstance(instructions_raw, list):
        steps = []
        for step in instructions_raw:
            if isinstance(step, str):
                steps.append(step)
            elif isinstance(step, dict):
                steps.append(step.get("text", ""))
        instructions = "\n".join(s for s in steps if s)

    cuisine = ""
    rc = data.get("recipeCuisine", "")
    if isinstance(rc, list):
        cuisine = rc[0] if rc else ""
    elif isinstance(rc, str):
        cuisine = rc

    image = data.get("image", "")
    if isinstance(image, list):
        image = image[0] if image else ""
    elif isinstance(image, dict):
        image = image.get("url", "")

    return {
        "recipe_id": recipe_id,
        "title": title,
        "ingredients": ingredients,
        "instructions": instructions,
        "cuisine": cuisine,
        "tags": set(),
        "prep_time_mins": 0,
        "servings": 4,
        "source_url": source_url,
        "image_url": image,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def write_recipe(recipe):
    from decimal import Decimal

    item = {
        "recipe_id": recipe["recipe_id"],
        "title": recipe["title"],
        "instructions": recipe.get("instructions", ""),
        "cuisine": recipe.get("cuisine", ""),
        "source_url": recipe.get("source_url", ""),
        "created_at": recipe.get("created_at", ""),
        "servings": Decimal(str(recipe.get("servings", 4))),
        "prep_time_mins": Decimal(str(recipe.get("prep_time_mins", 0))),
    }

    if recipe.get("ingredients"):
        item["ingredients"] = [
            {
                "name": ing["name"],
                "quantity": Decimal(str(ing.get("quantity", 1))),
                "unit": ing.get("unit", "count"),
            }
            for ing in recipe["ingredients"]
        ]

    if recipe.get("tags"):
        item["tags"] = set(recipe["tags"]) if recipe["tags"] else None
        if not item["tags"]:
            del item["tags"]

    image_url = recipe.get("image_url", "")
    if image_url:
        try:
            img_resp = requests.get(image_url, timeout=10)
            if img_resp.ok:
                key = f"recipes/{recipe['recipe_id']}.jpg"
                s3.put_object(
                    Bucket=S3_BUCKET, Key=key,
                    Body=img_resp.content, ContentType="image/jpeg",
                )
                item["image_s3_key"] = key
        except Exception as e:
            logger.warning(f"Image download failed: {e}")

    table.put_item(Item=item)
