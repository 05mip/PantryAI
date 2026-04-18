"""
AWS Lambda function: DynamoDB Streams -> OpenSearch sync.
Triggered by DynamoDB Streams on pai-recipes table.

Deploy as Lambda with:
  - Runtime: Python 3.11
  - Trigger: DynamoDB Stream on pai-recipes (NEW_AND_OLD_IMAGES)
  - Env vars: OPENSEARCH_ENDPOINT, AWS_REGION
"""
import json
import logging
import os

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

logger = logging.getLogger()
logger.setLevel(logging.INFO)

OPENSEARCH_ENDPOINT = os.environ.get("OPENSEARCH_ENDPOINT", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")
INDEX_NAME = "recipes"


def get_os_client():
    credentials = boto3.Session().get_credentials()
    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        AWS_REGION,
        "aoss",
        session_token=credentials.token,
    )
    host = OPENSEARCH_ENDPOINT.replace("https://", "").replace("http://", "").rstrip("/")
    return OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=30,
    )


def handler(event, context):
    if not OPENSEARCH_ENDPOINT:
        logger.warning("OPENSEARCH_ENDPOINT not set, skipping sync")
        return

    client = get_os_client()
    records = event.get("Records", [])
    logger.info(f"Processing {len(records)} DynamoDB stream records")

    for record in records:
        event_name = record.get("eventName", "")
        try:
            if event_name in ("INSERT", "MODIFY"):
                new_image = record.get("dynamodb", {}).get("NewImage", {})
                recipe_id = _unwrap(new_image.get("recipe_id", {}))
                if not recipe_id:
                    continue

                title = _unwrap(new_image.get("title", {}))
                cuisine = _unwrap(new_image.get("cuisine", {}))
                tags = _unwrap(new_image.get("tags", {}))

                ingredients = _unwrap(new_image.get("ingredients", {}))
                ingredients_text = ""
                if isinstance(ingredients, list):
                    ingredients_text = " ".join(
                        _unwrap(ing.get("name", {})) if isinstance(ing, dict) else str(ing)
                        for ing in ingredients
                    )

                doc = {
                    "title": title or "",
                    "ingredients_text": ingredients_text,
                    "cuisine": cuisine or "",
                    "tags": list(tags) if isinstance(tags, (list, set)) else [],
                }
                client.index(index=INDEX_NAME, id=recipe_id, body=doc)
                logger.info(f"Indexed recipe: {recipe_id}")

            elif event_name == "REMOVE":
                old_image = record.get("dynamodb", {}).get("OldImage", {})
                recipe_id = _unwrap(old_image.get("recipe_id", {}))
                if recipe_id:
                    client.delete(index=INDEX_NAME, id=recipe_id, ignore=[404])
                    logger.info(f"Deleted recipe from index: {recipe_id}")

        except Exception as e:
            logger.error(f"Error processing stream record: {e}")

    return {"statusCode": 200, "body": f"Processed {len(records)} records"}


def _unwrap(dynamo_val):
    """Unwrap a DynamoDB stream attribute value."""
    if not isinstance(dynamo_val, dict):
        return dynamo_val
    if "S" in dynamo_val:
        return dynamo_val["S"]
    if "N" in dynamo_val:
        return float(dynamo_val["N"])
    if "BOOL" in dynamo_val:
        return dynamo_val["BOOL"]
    if "SS" in dynamo_val:
        return dynamo_val["SS"]
    if "L" in dynamo_val:
        return [_unwrap(v) for v in dynamo_val["L"]]
    if "M" in dynamo_val:
        return {k: _unwrap(v) for k, v in dynamo_val["M"].items()}
    if "NULL" in dynamo_val:
        return None
    return dynamo_val
