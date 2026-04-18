"""
Setup CloudWatch log groups and metric alarms for PantryAI.
Run: python setup_cloudwatch.py
"""
import boto3
from config import AWS_REGION, CLOUDWATCH, DYNAMO_TABLES

logs = boto3.client("logs", region_name=AWS_REGION)
cloudwatch = boto3.client("cloudwatch", region_name=AWS_REGION)


def create_log_groups():
    for name, group in CLOUDWATCH.items():
        try:
            logs.create_log_group(logGroupName=group)
            logs.put_retention_policy(logGroupName=group, retentionInDays=30)
            print(f"Created log group: {group}")
        except logs.exceptions.ResourceAlreadyExistsException:
            print(f"Log group {group} already exists")


def create_alarms():
    for table_key, table_name in DYNAMO_TABLES.items():
        cloudwatch.put_metric_alarm(
            AlarmName=f"pai-{table_key}-read-throttle",
            Namespace="AWS/DynamoDB",
            MetricName="ReadThrottleEvents",
            Dimensions=[{"Name": "TableName", "Value": table_name}],
            Statistic="Sum",
            Period=300,
            EvaluationPeriods=1,
            Threshold=5,
            ComparisonOperator="GreaterThanOrEqualToThreshold",
            ActionsEnabled=False,
            AlarmDescription=f"DynamoDB read throttle on {table_name}",
        )
        cloudwatch.put_metric_alarm(
            AlarmName=f"pai-{table_key}-write-throttle",
            Namespace="AWS/DynamoDB",
            MetricName="WriteThrottleEvents",
            Dimensions=[{"Name": "TableName", "Value": table_name}],
            Statistic="Sum",
            Period=300,
            EvaluationPeriods=1,
            Threshold=5,
            ComparisonOperator="GreaterThanOrEqualToThreshold",
            ActionsEnabled=False,
            AlarmDescription=f"DynamoDB write throttle on {table_name}",
        )
        print(f"Created read/write throttle alarms for {table_name}")

    cloudwatch.put_metric_alarm(
        AlarmName="pai-bedrock-throttle",
        Namespace="AWS/Bedrock",
        MetricName="ThrottledCount",
        Statistic="Sum",
        Period=300,
        EvaluationPeriods=1,
        Threshold=3,
        ComparisonOperator="GreaterThanOrEqualToThreshold",
        ActionsEnabled=False,
        AlarmDescription="Bedrock API throttle events",
    )
    print("Created Bedrock throttle alarm")


def main():
    print("Setting up CloudWatch resources...")
    create_log_groups()
    create_alarms()
    print("Done.")


if __name__ == "__main__":
    main()
