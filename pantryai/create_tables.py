"""
One-time script to create all DynamoDB tables for PantryAI.
Run: python create_tables.py
"""
from dotenv import load_dotenv
load_dotenv()

import boto3
from config import DYNAMO_TABLES, AWS_REGION

dynamodb = boto3.client("dynamodb", region_name=AWS_REGION)


def create_table(table_name, key_schema, attribute_definitions, gsi=None):
    params = {
        "TableName": table_name,
        "KeySchema": key_schema,
        "AttributeDefinitions": attribute_definitions,
        "BillingMode": "PAY_PER_REQUEST",
    }
    if gsi:
        params["GlobalSecondaryIndexes"] = gsi

    try:
        dynamodb.create_table(**params)
        print(f"Created table: {table_name}")
        waiter = dynamodb.get_waiter("table_exists")
        waiter.wait(TableName=table_name)
        print(f"  Table {table_name} is active.")
    except dynamodb.exceptions.ResourceInUseException:
        print(f"  Table {table_name} already exists, skipping.")


def main():
    # pai-pantry
    create_table(
        DYNAMO_TABLES["pantry"],
        key_schema=[
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "item_id", "KeyType": "RANGE"},
        ],
        attribute_definitions=[
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "item_id", "AttributeType": "S"},
            {"AttributeName": "name", "AttributeType": "S"},
        ],
        gsi=[
            {
                "IndexName": "name-index",
                "KeySchema": [
                    {"AttributeName": "user_id", "KeyType": "HASH"},
                    {"AttributeName": "name", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    )

    # pai-recipes
    create_table(
        DYNAMO_TABLES["recipes"],
        key_schema=[{"AttributeName": "recipe_id", "KeyType": "HASH"}],
        attribute_definitions=[
            {"AttributeName": "recipe_id", "AttributeType": "S"},
            {"AttributeName": "cuisine", "AttributeType": "S"},
        ],
        gsi=[
            {
                "IndexName": "cuisine-index",
                "KeySchema": [
                    {"AttributeName": "cuisine", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    )

    # pai-favorites
    create_table(
        DYNAMO_TABLES["favorites"],
        key_schema=[
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "recipe_id", "KeyType": "RANGE"},
        ],
        attribute_definitions=[
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "recipe_id", "AttributeType": "S"},
        ],
    )

    # pai-grocery-lists
    create_table(
        DYNAMO_TABLES["grocery"],
        key_schema=[
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "item_id", "KeyType": "RANGE"},
        ],
        attribute_definitions=[
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "item_id", "AttributeType": "S"},
        ],
    )

    # pai-meal-plans
    create_table(
        DYNAMO_TABLES["meal_plans"],
        key_schema=[
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "slot_id", "KeyType": "RANGE"},
        ],
        attribute_definitions=[
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "slot_id", "AttributeType": "S"},
        ],
    )

    # Enable DynamoDB Streams on pai-recipes for OpenSearch sync
    try:
        dynamodb.update_table(
            TableName=DYNAMO_TABLES["recipes"],
            StreamSpecification={
                "StreamEnabled": True,
                "StreamViewType": "NEW_AND_OLD_IMAGES",
            },
        )
        print(f"Enabled streams on {DYNAMO_TABLES['recipes']}")
    except Exception as e:
        print(f"  Streams may already be enabled: {e}")

    print("\nAll tables created successfully.")


if __name__ == "__main__":
    main()
