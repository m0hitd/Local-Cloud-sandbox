"""
PostgreSQL CRUD sandbox against the local postgres-rds container.

Connection details come from the Secrets Manager secret that Terraform creates
(sandbox/postgres/credentials). If the secret cannot be read, the script uses
the defaults in docker-compose.yml instead.

Usage (from the repo root, after docker compose up -d and terraform apply):
    python services/databases/postgres_crud.py
"""
import json
import os
from contextlib import closing

import boto3
import psycopg2

ENDPOINT = os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
SECRET_ID = os.environ.get("POSTGRES_SECRET_ID", "sandbox/postgres/credentials")

FALLBACK_SETTINGS = {
    "host": "localhost",
    "port": 5432,
    "dbname": "cloud_sandbox_db",
    "user": "sandbox_admin",
    "password": "localdevpassword",
}


def load_connection_settings():
    try:
        sm = boto3.client("secretsmanager", endpoint_url=ENDPOINT, region_name=REGION)
        secret = json.loads(sm.get_secret_value(SecretId=SECRET_ID)["SecretString"])
        settings = {
            "host": secret["host"],
            "port": int(secret["port"]),
            "dbname": secret["dbname"],
            "user": secret["username"],
            "password": secret["password"],
        }
        print(f"Loaded connection settings from secret {SECRET_ID}")
        return settings
    except Exception as exc:  # any failure falls back to the compose defaults
        print(f"Could not read secret {SECRET_ID} ({exc}). Using compose defaults.")
        return FALLBACK_SETTINGS


def run_crud(conn):
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id         SERIAL PRIMARY KEY,
                name       TEXT NOT NULL,
                email      TEXT UNIQUE NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        print("CREATE table customers ready")

        cur.execute(
            """
            INSERT INTO customers (name, email) VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            ("Ada Sandbox", "ada@example.com"),
        )
        customer_id = cur.fetchone()[0]
        print(f"CREATE (upsert) customer id={customer_id}")

        cur.execute(
            "SELECT id, name, email, created_at FROM customers WHERE id = %s",
            (customer_id,),
        )
        print(f"READ   {cur.fetchone()}")

        cur.execute(
            "UPDATE customers SET name = %s WHERE id = %s RETURNING name",
            ("Ada Updated", customer_id),
        )
        print(f"UPDATE name is now {cur.fetchone()[0]}")

        cur.execute("SELECT count(*) FROM customers")
        print(f"LIST   {cur.fetchone()[0]} customers in table")

        cur.execute("DELETE FROM customers WHERE id = %s", (customer_id,))
        print(f"DELETE removed {cur.rowcount} row")


def main():
    settings = load_connection_settings()
    with closing(psycopg2.connect(**settings)) as conn:
        run_crud(conn)


if __name__ == "__main__":
    main()
