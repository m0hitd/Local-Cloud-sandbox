"""
Poll the SQS order queue, validate and transform each order, and stream the
results into a BigQuery table on the local BigQuery emulator.

Messages that cannot be parsed or validated are logged and deleted so they do
not block the queue. Messages whose rows fail to reach BigQuery stay on the
queue and are redelivered after the visibility timeout.

A small HTTP server on HEALTH_PORT serves /healthz for Kubernetes probes and
reports running counters.

Environment variables:
    SQS_ENDPOINT_URL        SQS endpoint (LocalStack). Default: http://localhost:4566
    SQS_QUEUE_NAME          Queue to poll. Default: order-queue
    AWS_DEFAULT_REGION      Default: us-east-1
    BQ_EMULATOR_HOST        BigQuery emulator URL. Default: http://localhost:9050
    GCP_PROJECT_ID          Default: local-analytics-project
    BQ_DATASET_ID           Default: ecommerce_data
    BQ_TABLE_NAME           Default: processed_orders
    MAX_MESSAGES_PER_POLL   Up to 10. Default: 10
    WAIT_TIME_SECONDS       SQS long-poll wait, up to 20. Default: 20
    HEALTH_PORT             Health endpoint port. Default: 8080
"""
import json
import logging
import os
import signal
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from google.api_core.client_options import ClientOptions
from google.auth.credentials import AnonymousCredentials
from google.cloud import bigquery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("consumer")

SQS_ENDPOINT_URL = os.environ.get("SQS_ENDPOINT_URL", "http://localhost:4566")
SQS_QUEUE_NAME = os.environ.get("SQS_QUEUE_NAME", "order-queue")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
BQ_EMULATOR_HOST = os.environ.get("BQ_EMULATOR_HOST", "http://localhost:9050")
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "local-analytics-project")
BQ_DATASET_ID = os.environ.get("BQ_DATASET_ID", "ecommerce_data")
BQ_TABLE_NAME = os.environ.get("BQ_TABLE_NAME", "processed_orders")
MAX_MESSAGES_PER_POLL = min(int(os.environ.get("MAX_MESSAGES_PER_POLL", "10")), 10)
WAIT_TIME_SECONDS = min(int(os.environ.get("WAIT_TIME_SECONDS", "20")), 20)
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", "8080"))

TABLE_ID = f"{GCP_PROJECT_ID}.{BQ_DATASET_ID}.{BQ_TABLE_NAME}"
REQUIRED_FIELDS = {
    "order_id",
    "customer_id",
    "product_name",
    "quantity",
    "unit_price",
    "currency",
    "order_timestamp",
}

# Written by the main loop and read by the health handler thread
stats = {
    "batches_ok": 0,
    "batches_failed": 0,
    "orders_loaded": 0,
    "orders_discarded": 0,
}

_running = True


class InvalidOrder(Exception):
    """Raised when a queue message cannot be turned into a valid order row."""


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/healthz":
            self.send_error(404)
            return
        body = json.dumps({"status": "ok", **stats}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Keep probe traffic out of the logs
        pass


def start_health_server():
    server = HTTPServer(("0.0.0.0", HEALTH_PORT), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("Health endpoint listening on port %d", HEALTH_PORT)
    return server


def _handle_signal(signum, frame):
    global _running
    log.info("Received signal %s, finishing the current batch before exit.", signum)
    _running = False


def build_sqs_client():
    return boto3.client("sqs", endpoint_url=SQS_ENDPOINT_URL, region_name=AWS_REGION)


def build_bq_client():
    # The emulator does not validate credentials, so anonymous credentials
    # keep the client from trying to reach real Google auth endpoints.
    return bigquery.Client(
        project=GCP_PROJECT_ID,
        credentials=AnonymousCredentials(),
        client_options=ClientOptions(api_endpoint=BQ_EMULATOR_HOST),
    )


def resolve_queue_url(sqs):
    """Create the queue (idempotent) and rebase its URL onto the configured endpoint.

    LocalStack can return URLs built from localhost, which pods cannot reach.
    Keeping only the path and reattaching the endpoint avoids that.
    """
    url = sqs.create_queue(QueueName=SQS_QUEUE_NAME)["QueueUrl"]
    return SQS_ENDPOINT_URL.rstrip("/") + urlparse(url).path


def parse_and_transform(body):
    """Validate a raw SQS message body and return a BigQuery-ready row."""
    try:
        order = json.loads(body)
    except json.JSONDecodeError as exc:
        raise InvalidOrder(f"malformed JSON: {exc}") from exc

    if not isinstance(order, dict):
        raise InvalidOrder("payload is not a JSON object")

    missing = REQUIRED_FIELDS - order.keys()
    if missing:
        raise InvalidOrder(f"missing fields: {sorted(missing)}")

    try:
        quantity = int(order["quantity"])
        unit_price = float(order["unit_price"])
    except (TypeError, ValueError) as exc:
        raise InvalidOrder(f"non-numeric quantity or unit_price: {exc}") from exc

    if quantity <= 0 or unit_price < 0:
        raise InvalidOrder("quantity must be positive and unit_price must not be negative")

    return {
        "order_id": str(order["order_id"]),
        "customer_id": str(order["customer_id"]),
        "product_name": str(order["product_name"]),
        "quantity": quantity,
        "unit_price": unit_price,
        "total_amount": round(quantity * unit_price, 2),
        "currency": str(order["currency"]),
        "order_status": str(order.get("order_status") or "UNKNOWN"),
        "order_timestamp": order["order_timestamp"],
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }


def process_batch(sqs, queue_url, bq, messages):
    """Transform a batch, stream it to BigQuery, and delete the messages it handled.

    Raises if BigQuery rejects rows. In that case nothing is deleted, so the
    messages are redelivered after the visibility timeout.
    """
    rows = []
    receipts = []
    for message in messages:
        receipts.append(message["ReceiptHandle"])
        try:
            rows.append(parse_and_transform(message["Body"]))
        except InvalidOrder as exc:
            stats["orders_discarded"] += 1
            log.warning("Discarding invalid message %s: %s", message.get("MessageId"), exc)

    if rows:
        errors = bq.insert_rows_json(TABLE_ID, rows)
        if errors:
            raise RuntimeError(f"BigQuery rejected {len(rows)} rows: {errors}")
        stats["orders_loaded"] += len(rows)
        log.info("ETL Success: Loaded %d orders into BigQuery!", len(rows))

    for receipt in receipts:
        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt)
    stats["batches_ok"] += 1


def main():
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    server = start_health_server()
    sqs = build_sqs_client()
    queue_url = resolve_queue_url(sqs)
    bq = build_bq_client()

    log.info("Consumer listening for orders on SQS...")
    while _running:
        try:
            response = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=MAX_MESSAGES_PER_POLL,
                WaitTimeSeconds=WAIT_TIME_SECONDS,
            )
        except (ClientError, BotoCoreError) as exc:
            log.error("SQS receive failed, retrying in 5 seconds: %s", exc)
            time.sleep(5)
            continue

        messages = response.get("Messages", [])
        if not messages:
            continue

        try:
            process_batch(sqs, queue_url, bq, messages)
        except Exception:
            stats["batches_failed"] += 1
            log.exception("Batch failed, messages will be redelivered after the visibility timeout.")

    server.shutdown()
    log.info("Consumer stopped.")


if __name__ == "__main__":
    main()
