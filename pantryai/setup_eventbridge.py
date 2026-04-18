"""
Setup EventBridge Scheduler rule for periodic recipe scraping.
Run: python setup_eventbridge.py
"""
import json

import boto3
from config import AWS_REGION

events = boto3.client("events", region_name=AWS_REGION)
lambda_client = boto3.client("lambda", region_name=AWS_REGION)


def setup_scraper_schedule(lambda_arn, role_arn):
    """
    Create an EventBridge rule that triggers the scraper Lambda weekly.
    lambda_arn: ARN of the lambda_scraper function
    role_arn: ARN of an IAM role EventBridge can assume
    """
    rule_name = "pai-weekly-scrape"

    events.put_rule(
        Name=rule_name,
        ScheduleExpression="rate(7 days)",
        State="ENABLED",
        Description="Trigger PantryAI recipe scraper weekly",
    )
    print(f"Created EventBridge rule: {rule_name}")

    events.put_targets(
        Rule=rule_name,
        Targets=[
            {
                "Id": "scraper-lambda",
                "Arn": lambda_arn,
                "Input": json.dumps({
                    "source": "eventbridge",
                    "action": "scrape_new_recipes",
                }),
            }
        ],
    )
    print(f"Added Lambda target to rule: {rule_name}")

    try:
        lambda_client.add_permission(
            FunctionName=lambda_arn,
            StatementId="AllowEventBridgeInvoke",
            Action="lambda:InvokeFunction",
            Principal="events.amazonaws.com",
            SourceArn=f"arn:aws:events:{AWS_REGION}:*:rule/{rule_name}",
        )
        print("Added Lambda invoke permission for EventBridge")
    except lambda_client.exceptions.ResourceConflictException:
        print("Lambda permission already exists")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python setup_eventbridge.py <lambda_arn> <role_arn>")
        sys.exit(1)
    setup_scraper_schedule(sys.argv[1], sys.argv[2])
