import json
import logging
import os

from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

from config import OPENSEARCH, AWS_REGION

logger = logging.getLogger("pantryai")

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client

    endpoint = OPENSEARCH["endpoint"]
    if not endpoint:
        logger.warning("OpenSearch endpoint not configured; search will be unavailable.")
        return None

    access_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    session_token = os.environ.get("AWS_SESSION_TOKEN", "")

    if not access_key or not secret_key:
        logger.warning("AWS credentials not found in env vars for OpenSearch.")
        return None

    auth_kwargs = {
        "region": AWS_REGION,
        "service": "aoss",
    }
    if session_token:
        awsauth = AWS4Auth(access_key, secret_key, AWS_REGION, "aoss", session_token=session_token)
    else:
        awsauth = AWS4Auth(access_key, secret_key, AWS_REGION, "aoss")

    host = endpoint.replace("https://", "").replace("http://", "").rstrip("/")
    _client = OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=30,
    )
    return _client


def ensure_index():
    client = _get_client()
    if not client:
        return
    index = OPENSEARCH["index"]
    try:
        exists = client.indices.exists(index)
    except Exception as e:
        logger.error(f"Failed to check index existence: {e}")
        exists = False

    if not exists:
        try:
            client.indices.create(index, body={
                "mappings": {
                    "properties": {
                        "title": {"type": "text", "analyzer": "standard"},
                        "ingredients_text": {"type": "text", "analyzer": "standard"},
                        "cuisine": {"type": "keyword"},
                        "tags": {"type": "keyword"},
                    }
                }
            })
            logger.info(f"Created OpenSearch index: {index}")
        except Exception as e:
            logger.error(f"Failed to create index: {e}")


def index_recipe(recipe):
    client = _get_client()
    if not client:
        return

    ingredients_text = " ".join(
        ing.get("name", "") for ing in recipe.get("ingredients", [])
    )
    doc = {
        "title": recipe.get("title", ""),
        "ingredients_text": ingredients_text,
        "cuisine": recipe.get("cuisine", ""),
        "tags": list(recipe.get("tags", [])),
    }
    client.index(
        index=OPENSEARCH["index"],
        id=recipe["recipe_id"],
        body=doc,
    )


def bulk_index_recipes(recipes):
    client = _get_client()
    if not client:
        return

    ensure_index()
    actions = []
    for recipe in recipes:
        ingredients_text = " ".join(
            ing.get("name", "") for ing in recipe.get("ingredients", [])
        )
        actions.append({"index": {"_index": OPENSEARCH["index"], "_id": recipe["recipe_id"]}})
        actions.append({
            "title": recipe.get("title", ""),
            "ingredients_text": ingredients_text,
            "cuisine": recipe.get("cuisine", ""),
            "tags": list(recipe.get("tags", [])),
        })

    if actions:
        body = "\n".join([json.dumps(a) for a in actions]) + "\n"
        resp = client.bulk(body=body)
        errors = resp.get("errors", False)
        if errors:
            for item in resp.get("items", []):
                err = item.get("index", {}).get("error")
                if err:
                    logger.error(f"Bulk index error: {err}")
        logger.info(f"Bulk indexed {len(recipes)} recipes to OpenSearch (errors={errors})")


def search_recipes(query, limit=20):
    client = _get_client()
    if not client:
        return []

    body = {
        "size": limit,
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["title^3", "ingredients_text^2", "cuisine"],
                "fuzziness": "AUTO",
            }
        }
    }
    try:
        resp = client.search(index=OPENSEARCH["index"], body=body)
        hits = resp.get("hits", {}).get("hits", [])
        return [{"recipe_id": h["_id"], "score": h["_score"], **h["_source"]} for h in hits]
    except Exception as e:
        logger.error(f"OpenSearch search error: {e}")
        return []
