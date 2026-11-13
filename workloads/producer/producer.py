"""
Generate synthetic e-commerce orders and publish them to an SQS queue.

Environment variables:
    SQS_ENDPOINT_URL          SQS endpoint (LocalStack). Default: http://localhost:4566
    SQS_QUEUE_NAME            Queue to publish to. Default: order-queue
    AWS_DEFAULT_REGION        Default: us-east-1
    PUBLISH_INTERVAL_SECONDS  Delay between messages. Default: 2
    MAX_ORDERS                Stop after this many orders. 0 runs forever. Default: 0
"""
import json
import logging
import os
import random
import signal
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("producer")

SQS_ENDPOINT_URL = os.environ.get("SQS_ENDPOINT_URL", "http://localhost:4566")
SQS_QUEUE_NAME = os.environ.get("SQS_QUEUE_NAME", "order-queue")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
PUBLISH_INTERVAL_SECONDS = float(os.environ.get("PUBLISH_INTERVAL_SECONDS", "2"))
MAX_ORDERS = int(os.environ.get("MAX_ORDERS", "0"))

PRODUCTS = {
    "Wireless Mouse": 24.99,
    "Mechanical Keyboard": 89.50,
    "USB-C Hub": 39.00,
    "27in Monitor": 219.99,
    "Laptop Stand": 45.00,
}
ORDER_STATUSES = ["PLACED", "PAID", "SHIPPED"]
CURRENCY = "USD"

_running = True


def _handle_signal(signum, frame):
    global _running
    log.info("Received signal %s, stopping after the current order.", signum)
    _running = False


def build_sqs_client():
    return boto3.client("sqs", endpoint_url=SQS_ENDPOINT_URL, region_name=AWS_REGION)


def resolve_queue_url(sqs):
    """Create the queue (idempotent) and rebase its URL onto the configured endpoint.

    LocalStack can return URLs built from localhost, which pods cannot reach.
    Keeping only the path and reattaching the endpoint avoids that.
    """
    url = sqs.create_queue(QueueName=SQS_QUEUE_NAME)["QueueUrl"]
    return SQS_ENDPOINT_URL.rstrip("/") + urlparse(url).path


def generate_order():
    product_name = random.choice(list(PRODUCTS))
    return {
        "order_id": str(uuid.uuid4()),
        "customer_id": f"CUST-{random.randint(1000, 9999)}",
        "product_name": product_name,
        "quantity": random.randint(1, 5),
        "unit_price": PRODUCTS[product_name],
        "currency": CURRENCY,
        "order_status": random.choice(ORDER_STATUSES),
        "order_timestamp": datetime.now(timezone.utc).isoformat(),
    }


def main():
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    sqs = build_sqs_client()
    queue_url = resolve_queue_url(sqs)
    log.info("Publishing orders to %s", queue_url)

    sent = 0
    while _running and (MAX_ORDERS == 0 or sent < MAX_ORDERS):
        order = generate_order()
        try:
            sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(order))
        except ClientError as exc:
            log.error("Failed to publish order %s: %s", order["order_id"], exc)
            time.sleep(PUBLISH_INTERVAL_SECONDS)
            continue

        sent += 1
        log.info(
            "Published order %s (%d x %s)",
            order["order_id"],
            order["quantity"],
            order["product_name"],
        )
        time.sleep(PUBLISH_INTERVAL_SECONDS)

    log.info("Producer stopped after %d orders.", sent)


if __name__ == "__main__":
    main()
