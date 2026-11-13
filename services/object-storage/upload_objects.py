"""
Upload the same sample objects to LocalStack S3 and to fake-gcs-server, then list both buckets.

Buckets are created by terraform apply. If a bucket is missing, this script creates it.

Usage (from the repo root, with requirements-dev.txt installed):
    python services/object-storage/upload_objects.py
"""
import os

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from google.auth.credentials import AnonymousCredentials
from google.cloud import storage as gcs

LOCALSTACK_ENDPOINT = os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")
FAKE_GCS_ENDPOINT = os.environ.get("FAKE_GCS_ENDPOINT", "http://localhost:4443")
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
GCP_PROJECT = os.environ.get("GCP_PROJECT_ID", "local-analytics-project")
S3_BUCKET = "sandbox-artifacts"
GCS_BUCKET = "sandbox-gcs-artifacts"

# The Google client reads this variable and sends requests to fake-gcs-server
os.environ.setdefault("STORAGE_EMULATOR_HOST", FAKE_GCS_ENDPOINT)

SAMPLE_OBJECTS = {
    "reports/daily-orders.csv": b"order_id,total\n1001,49.98\n1002,219.99\n",
    "configs/app-settings.json": b'{"env": "local", "feature_flags": {"new_checkout": false}}\n',
    "logs/startup.txt": b"sandbox object storage smoke test\n",
}


def s3_client():
    # Path-style addressing avoids bucket.localhost hostnames, which LocalStack cannot resolve
    return boto3.client(
        "s3",
        endpoint_url=LOCALSTACK_ENDPOINT,
        region_name=REGION,
        config=Config(s3={"addressing_style": "path"}),
    )


def ensure_s3_bucket(s3, name):
    try:
        s3.head_bucket(Bucket=name)
    except ClientError:
        s3.create_bucket(Bucket=name)


def upload_to_s3():
    s3 = s3_client()
    ensure_s3_bucket(s3, S3_BUCKET)
    for key, body in SAMPLE_OBJECTS.items():
        s3.put_object(Bucket=S3_BUCKET, Key=key, Body=body)
        print(f"S3   put   s3://{S3_BUCKET}/{key} ({len(body)} bytes)")
    listing = s3.list_objects_v2(Bucket=S3_BUCKET).get("Contents", [])
    print(f"S3   bucket {S3_BUCKET} holds {len(listing)} objects\n")


def upload_to_gcs():
    client = gcs.Client(project=GCP_PROJECT, credentials=AnonymousCredentials())
    bucket = client.lookup_bucket(GCS_BUCKET) or client.create_bucket(GCS_BUCKET)
    for key, body in SAMPLE_OBJECTS.items():
        bucket.blob(key).upload_from_string(body)
        print(f"GCS  put   gs://{GCS_BUCKET}/{key} ({len(body)} bytes)")
    names = [blob.name for blob in client.list_blobs(GCS_BUCKET)]
    print(f"GCS  bucket {GCS_BUCKET} holds {len(names)} objects")


def main():
    upload_to_s3()
    upload_to_gcs()


if __name__ == "__main__":
    main()
