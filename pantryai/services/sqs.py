import json
import logging

import boto3

from config import SQS, AWS_REGION

logger = logging.getLogger("pantryai")

sqs_client = boto3.client("sqs", region_name=AWS_REGION)


def send_scrape_message(url, metadata=None):
    """Send a recipe URL to the scrape queue for async processing by Lambda."""
    queue_url = SQS.get("scrape_queue_url")
    if not queue_url:
        logger.warning("SQS scrape queue URL not configured; message not sent.")
        return None

    body = {"url": url}
    if metadata:
        body["metadata"] = metadata

    try:
        response = sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(body),
        )
        message_id = response.get("MessageId")
        logger.info(f"Sent scrape message {message_id} for URL: {url}")
        return message_id
    except Exception as e:
        logger.error(f"Failed to send SQS message: {e}")
        raise


def send_batch_scrape_messages(urls):
    """Send multiple scrape URLs in a single batch (up to 10 per batch)."""
    queue_url = SQS.get("scrape_queue_url")
    if not queue_url:
        logger.warning("SQS scrape queue URL not configured; batch not sent.")
        return []

    results = []
    for i in range(0, len(urls), 10):
        batch = urls[i:i + 10]
        entries = [
            {
                "Id": str(idx),
                "MessageBody": json.dumps({"url": url}),
            }
            for idx, url in enumerate(batch)
        ]
        try:
            response = sqs_client.send_message_batch(
                QueueUrl=queue_url,
                Entries=entries,
            )
            successful = response.get("Successful", [])
            failed = response.get("Failed", [])
            results.extend(successful)
            if failed:
                logger.error(f"Failed to send {len(failed)} messages in batch")
        except Exception as e:
            logger.error(f"Batch send failed: {e}")

    logger.info(f"Batch sent {len(results)} scrape messages")
    return results
