import logging
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
import boto3

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

    credentials = boto3.Session().get_credentials()
    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        AWS_REGION,
        "aoss",
        session_token=credentials.token,
    )

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
    if not client.indices.exists(index):
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
        body = "\n".join([__import__("json").dumps(a) for a in actions]) + "\n"
        client.bulk(body=body)
        logger.info(f"Bulk indexed {len(recipes)} recipes to OpenSearch")


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
