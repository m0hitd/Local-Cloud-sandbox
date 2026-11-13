"""
DynamoDB CRUD sandbox for the sandbox-orders table created by Terraform.

Usage (from the repo root):
    python services/databases/dynamodb_crud.py demo    # create, read, update, scan, delete one item
    python services/databases/dynamodb_crud.py scan    # list items written by the Lambda or producers
"""
import argparse
import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr

ENDPOINT = os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
TABLE_NAME = os.environ.get("ORDERS_TABLE", "sandbox-orders")
DEMO_KEY = "DEMO-0001"


def get_table():
    resource = boto3.resource("dynamodb", endpoint_url=ENDPOINT, region_name=REGION)
    return resource.Table(TABLE_NAME)


def demo(table):
    print("CREATE")
    table.put_item(
        Item={
            "order_id": DEMO_KEY,
            "customer_id": "CUST-0042",
            "quantity": 2,
            "unit_price": Decimal("24.99"),
            "order_status": "PLACED",
        }
    )
    print(f"  wrote {DEMO_KEY}")

    print("READ")
    item = table.get_item(Key={"order_id": DEMO_KEY}).get("Item")
    print(f"  {item}")

    print("UPDATE")
    result = table.update_item(
        Key={"order_id": DEMO_KEY},
        UpdateExpression="SET order_status = :status",
        ExpressionAttributeValues={":status": "SHIPPED"},
        ReturnValues="UPDATED_NEW",
    )
    print(f"  {result['Attributes']}")

    print("SCAN for customer CUST-0042")
    matches = table.scan(FilterExpression=Attr("customer_id").eq("CUST-0042"))["Items"]
    for match in matches:
        print(f"  {match['order_id']}  {match.get('order_status', '-')}")

    print("DELETE")
    table.delete_item(Key={"order_id": DEMO_KEY})
    print(f"  deleted {DEMO_KEY}")


def scan(table):
    items = []
    kwargs = {}
    while True:
        response = table.scan(**kwargs)
        items.extend(response["Items"])
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    print(f"{len(items)} items in {TABLE_NAME}")
    for item in items[:20]:
        print(f"  {item.get('order_id', '-')}  {item.get('product_name', '-'):<20} {item.get('order_status', '-')}")
    if len(items) > 20:
        print(f"  ... and {len(items) - 20} more")


def main():
    parser = argparse.ArgumentParser(description="DynamoDB CRUD sandbox for sandbox-orders.")
    parser.add_argument("command", choices=["demo", "scan"])
    args = parser.parse_args()

    table = get_table()
    if args.command == "demo":
        demo(table)
    else:
        scan(table)


if __name__ == "__main__":
    main()
