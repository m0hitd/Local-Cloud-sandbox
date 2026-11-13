"""
AWS Lambda handler for sandbox order events.

Triggered by an SQS event source mapping. Each record body is a JSON order.
Valid orders are written to the sandbox-orders DynamoDB table. Records that
cannot be parsed are logged and skipped. A DynamoDB error raises, so Lambda
retries the batch under the queue's redrive settings.
"""
import json
import logging
import os
from decimal import Decimal, InvalidOperation

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ.get("ORDERS_TABLE", "sandbox-orders")
# Set by deploy_lambda.py so the function reaches LocalStack. Unset on real AWS.
ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL")
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

_table = None


def get_table():
    # Created on first use and reused across warm invocations
    global _table
    if _table is None:
        resource = boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL, region_name=REGION)
        _table = resource.Table(TABLE_NAME)
    return _table


def to_item(order):
    return {
        "order_id": str(order["order_id"]),
        "customer_id": str(order.get("customer_id", "unknown")),
        "product_name": str(order.get("product_name", "unknown")),
        "quantity": int(order.get("quantity", 0)),
        "unit_price": Decimal(str(order.get("unit_price", "0"))),
        "order_status": str(order.get("order_status", "UNKNOWN")),
        "source": "lambda",
    }


def lambda_handler(event, context):
    records = event.get("Records", [])
    written = 0
    skipped = 0

    for record in records:
        try:
            order = json.loads(record["body"], parse_float=Decimal)
            item = to_item(order)
        except (KeyError, ValueError, TypeError, InvalidOperation) as exc:
            skipped += 1
            logger.warning("Skipping record %s: %s", record.get("messageId"), exc)
            continue

        get_table().put_item(Item=item)
        written += 1

    logger.info("Processed %d records: %d written, %d skipped", len(records), written, skipped)
    return {"processed": len(records), "written": written, "skipped": skipped}
