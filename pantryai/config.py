import os

DYNAMO_TABLES = {
    "pantry": "pai-pantry",
    "recipes": "pai-recipes",
    "favorites": "pai-favorites",
    "grocery": "pai-grocery-lists",
    "meal_plans": "pai-meal-plans",
}

S3_BUCKETS = {
    "recipe_images": "pai-recipe-images",
    "static": "pai-static-assets",
}

BEDROCK = {
    "model_id": "anthropic.claude-sonnet-4-5",
    "region": os.environ.get("AWS_REGION", "us-west-2"),
}

OPENSEARCH = {
    "endpoint": os.environ.get("OPENSEARCH_ENDPOINT", ""),
    "index": "recipes",
}

SQS = {
    "scrape_queue_url": os.environ.get("SQS_SCRAPE_QUEUE_URL", ""),
}

FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-in-prod")
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")

DEFAULT_USER_ID = "default-user"

CLOUDWATCH = {
    "flask_log_group": "/pantryai/flask",
    "lambda_log_group": "/pantryai/lambda",
}
