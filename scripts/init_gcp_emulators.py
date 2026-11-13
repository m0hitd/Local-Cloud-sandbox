"""
Provision GCP emulator resources for the sandbox.

    BigQuery  dataset ecommerce_data and table processed_orders   (bigquery-emulator, :9050)
    GCS       bucket sandbox-gcs-artifacts                        (fake-gcs-server, :4443)
    Pub/Sub   topic order-events and subscription order-events-sub (emulator, :8085)

Safe to re-run. Each step reports its own failure. The script exits non-zero
if any step failed, so bootstrap.ps1 can stop early.

Usage (from the repo root, after docker compose up -d):
    python scripts/init_gcp_emulators.py
"""
import os
import sys

from google.api_core.client_options import ClientOptions
from google.api_core.exceptions import AlreadyExists
from google.auth.credentials import AnonymousCredentials
from google.cloud import bigquery, pubsub_v1, storage

PROJECT = os.environ.get("GCP_PROJECT_ID", "local-analytics-project")
BQ_EMULATOR_HOST = os.environ.get("BQ_EMULATOR_HOST", "http://localhost:9050")
FAKE_GCS_ENDPOINT = os.environ.get("FAKE_GCS_ENDPOINT", "http://localhost:4443")
PUBSUB_EMULATOR_HOST = os.environ.get("PUBSUB_EMULATOR_HOST", "localhost:8085")
DATASET_ID = os.environ.get("BQ_DATASET_ID", "ecommerce_data")
TABLE_NAME = os.environ.get("BQ_TABLE_NAME", "processed_orders")
GCS_BUCKET = "sandbox-gcs-artifacts"
TOPIC_ID = "order-events"
SUBSCRIPTION_ID = "order-events-sub"

# Client libraries read these variables when they create their clients
os.environ.setdefault("STORAGE_EMULATOR_HOST", FAKE_GCS_ENDPOINT)
os.environ.setdefault("PUBSUB_EMULATOR_HOST", PUBSUB_EMULATOR_HOST)

BQ_SCHEMA = [
    bigquery.SchemaField("order_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("customer_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("product_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("quantity", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("unit_price", "FLOAT", mode="REQUIRED"),
    bigquery.SchemaField("total_amount", "FLOAT", mode="REQUIRED"),
    bigquery.SchemaField("currency", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("order_status", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("order_timestamp", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
]


def ensure_bigquery():
    client = bigquery.Client(
        project=PROJECT,
        credentials=AnonymousCredentials(),
        client_options=ClientOptions(api_endpoint=BQ_EMULATOR_HOST),
    )
    client.create_dataset(bigquery.Dataset(f"{PROJECT}.{DATASET_ID}"), exists_ok=True)
    table = bigquery.Table(f"{PROJECT}.{DATASET_ID}.{TABLE_NAME}", schema=BQ_SCHEMA)
    client.create_table(table, exists_ok=True)
    return f"BigQuery {PROJECT}.{DATASET_ID}.{TABLE_NAME}"


def ensure_gcs():
    client = storage.Client(project=PROJECT, credentials=AnonymousCredentials())
    bucket = client.lookup_bucket(GCS_BUCKET) or client.create_bucket(GCS_BUCKET)
    return f"GCS gs://{bucket.name}"


def ensure_pubsub():
    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()
    topic_path = publisher.topic_path(PROJECT, TOPIC_ID)
    subscription_path = subscriber.subscription_path(PROJECT, SUBSCRIPTION_ID)

    try:
        publisher.create_topic(name=topic_path)
    except AlreadyExists:
        pass

    try:
        subscriber.create_subscription(name=subscription_path, topic=topic_path)
    except AlreadyExists:
        pass

    return f"Pub/Sub topic {TOPIC_ID} with subscription {SUBSCRIPTION_ID}"


STEPS = [ensure_bigquery, ensure_gcs, ensure_pubsub]


def main():
    failures = 0
    for step in STEPS:
        try:
            print(f"OK    {step()}")
        except Exception as exc:
            failures += 1
            print(f"FAIL  {step.__name__}: {exc}")

    if failures:
        print(f"{failures} step(s) failed. Check that docker compose is running.")
        sys.exit(1)
    print("All GCP emulator resources are ready.")


if __name__ == "__main__":
    main()
