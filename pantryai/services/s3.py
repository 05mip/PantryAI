import boto3
from config import S3_BUCKETS, AWS_REGION

s3_client = boto3.client("s3", region_name=AWS_REGION)


def upload_recipe_image(recipe_id, image_bytes, content_type="image/jpeg"):
    key = f"recipes/{recipe_id}.jpg"
    s3_client.put_object(
        Bucket=S3_BUCKETS["recipe_images"],
        Key=key,
        Body=image_bytes,
        ContentType=content_type,
    )
    return key


def get_recipe_image_url(recipe_id):
    key = f"recipes/{recipe_id}.jpg"
    try:
        s3_client.head_object(Bucket=S3_BUCKETS["recipe_images"], Key=key)
        return f"https://{S3_BUCKETS['recipe_images']}.s3.{AWS_REGION}.amazonaws.com/{key}"
    except Exception:
        return None


def upload_static_asset(key, body, content_type):
    s3_client.put_object(
        Bucket=S3_BUCKETS["static"],
        Key=key,
        Body=body,
        ContentType=content_type,
        CacheControl="public, max-age=31536000",
    )
    return f"https://{S3_BUCKETS['static']}.s3.{AWS_REGION}.amazonaws.com/{key}"


def download_image(url):
    """Download image from URL and return bytes."""
    import requests
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.content
    except Exception:
        return None
