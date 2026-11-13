"""
Package handler.py and deploy it to LocalStack Lambda, triggered by an SQS queue.

Steps:
  1. Zip handler.py in memory.
  2. Create the IAM role lambda-exec if it is missing.
  3. Create or update the function sandbox-order-processor.
  4. Create the queue order-queue-lambda and map it to the function.
  5. With --test, send three sample orders to that queue.

The Lambda uses its own queue so it does not compete with the Kubernetes
consumer, which reads order-queue.

Usage (from the repo root):
    python services/serverless-lambda/deploy_lambda.py
    python services/serverless-lambda/deploy_lambda.py --test
"""
import argparse
import io
import json
import os
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ENDPOINT = os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
# Lambda containers reach LocalStack through this hostname, not localhost
LAMBDA_VISIBLE_ENDPOINT = "http://localhost.localstack.cloud:4566"
FUNCTION_NAME = "sandbox-order-processor"
ROLE_NAME = "lambda-exec"
QUEUE_NAME = "order-queue-lambda"
ORDERS_TABLE = "sandbox-orders"
HANDLER_FILE = Path(__file__).with_name("handler.py")

TRUST_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }
    ],
}


def client(service):
    return boto3.client(service, endpoint_url=ENDPOINT, region_name=REGION)


def package_handler():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(HANDLER_FILE, arcname="handler.py")
    return buffer.getvalue()


def ensure_role(iam):
    try:
        iam.create_role(RoleName=ROLE_NAME, AssumeRolePolicyDocument=json.dumps(TRUST_POLICY))
        print(f"Created role {ROLE_NAME}")
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "EntityAlreadyExists":
            raise
    return iam.get_role(RoleName=ROLE_NAME)["Role"]["Arn"]


def wait_until_ready(lam, timeout_seconds=30):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        config = lam.get_function_configuration(FunctionName=FUNCTION_NAME)
        if config.get("LastUpdateStatus", "Successful") != "InProgress":
            return
        time.sleep(1)
    raise TimeoutError("Lambda update did not finish in time")


def deploy_function(lam, role_arn, code):
    environment = {
        "Variables": {
            "ORDERS_TABLE": ORDERS_TABLE,
            "AWS_ENDPOINT_URL": LAMBDA_VISIBLE_ENDPOINT,
        }
    }

    try:
        lam.get_function(FunctionName=FUNCTION_NAME)
    except lam.exceptions.ResourceNotFoundException:
        lam.create_function(
            FunctionName=FUNCTION_NAME,
            Runtime="python3.11",
            Role=role_arn,
            Handler="handler.lambda_handler",
            Code={"ZipFile": code},
            Timeout=30,
            MemorySize=128,
            Environment=environment,
        )
        wait_until_ready(lam)
        print(f"Created function {FUNCTION_NAME}")
        return

    lam.update_function_code(FunctionName=FUNCTION_NAME, ZipFile=code)
    wait_until_ready(lam)
    lam.update_function_configuration(
        FunctionName=FUNCTION_NAME,
        Environment=environment,
        Timeout=30,
    )
    wait_until_ready(lam)
    print(f"Updated function {FUNCTION_NAME}")


def ensure_queue(sqs):
    queue_url = sqs.create_queue(QueueName=QUEUE_NAME)["QueueUrl"]
    queue_arn = sqs.get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=["QueueArn"],
    )["Attributes"]["QueueArn"]
    return queue_url, queue_arn


def ensure_event_mapping(lam, queue_arn):
    existing = lam.list_event_source_mappings(
        FunctionName=FUNCTION_NAME,
        EventSourceArn=queue_arn,
    )["EventSourceMappings"]
    if existing:
        print(f"SQS trigger already exists ({existing[0]['UUID']})")
        return

    mapping = lam.create_event_source_mapping(
        EventSourceArn=queue_arn,
        FunctionName=FUNCTION_NAME,
        BatchSize=10,
        Enabled=True,
    )
    print(f"Created SQS trigger {mapping['UUID']}")


def send_test_orders(sqs, queue_url):
    for _ in range(3):
        order = {
            "order_id": str(uuid.uuid4()),
            "customer_id": "CUST-LAMBDA",
            "product_name": "Laptop Stand",
            "quantity": 1,
            "unit_price": 45.0,
            "currency": "USD",
            "order_status": "PLACED",
            "order_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(order))
    print("Sent 3 test orders to the Lambda queue")


def main():
    parser = argparse.ArgumentParser(description="Deploy the sandbox Lambda and wire it to an SQS queue.")
    parser.add_argument("--test", action="store_true", help="Send sample orders after deploying")
    args = parser.parse_args()

    lam = client("lambda")
    sqs = client("sqs")

    role_arn = ensure_role(client("iam"))
    deploy_function(lam, role_arn, package_handler())

    queue_url, queue_arn = ensure_queue(sqs)
    ensure_event_mapping(lam, queue_arn)

    if args.test:
        send_test_orders(sqs, queue_url)
        print("Give LocalStack a few seconds, then run: python services/databases/dynamodb_crud.py scan")

    print("Lambda deployment complete.")


if __name__ == "__main__":
    main()
