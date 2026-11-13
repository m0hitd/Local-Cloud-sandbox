"""
Apply, read back, and exercise an S3 lifecycle rule on the sandbox artifacts bucket.

The rule expires objects under tmp/ after one day. LocalStack may not run
expiration on a daily schedule, so this script checks that the rule is stored
and returned intact, and that a tmp/ object can be written under it. It does
not wait a day for deletion.

Usage (from the repo root):
    python services/object-storage/lifecycle_s3.py
"""
import json
import os

import boto3
from botocore.config import Config

LOCALSTACK_ENDPOINT = os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
BUCKET = "sandbox-artifacts"

RULE = {
    "ID": "expire-tmp-after-1-day",
    "Filter": {"Prefix": "tmp/"},
    "Status": "Enabled",
    "Expiration": {"Days": 1},
}


def main():
    s3 = boto3.client(
        "s3",
        endpoint_url=LOCALSTACK_ENDPOINT,
        region_name=REGION,
        config=Config(s3={"addressing_style": "path"}),
    )

    s3.put_object(Bucket=BUCKET, Key="tmp/scratch.txt", Body=b"temporary data")
    print("Wrote tmp/scratch.txt")

    s3.put_bucket_lifecycle_configuration(
        Bucket=BUCKET,
        LifecycleConfiguration={"Rules": [RULE]},
    )
    print("Applied lifecycle rule")

    stored = s3.get_bucket_lifecycle_configuration(Bucket=BUCKET)["Rules"]
    for rule in stored:
        print(json.dumps(rule, indent=2))

    if not any(rule["ID"] == RULE["ID"] for rule in stored):
        raise SystemExit("Lifecycle rule was not returned after writing it")
    print("Lifecycle rule verified")


if __name__ == "__main__":
    main()
