"""Create the warehouse role, database and raw schema in Postgres (idempotent).

Runs from airflow-init with the Postgres superuser (the Airflow metadata user):
    python -m src.warehouse.setup
"""

import os
import re

from sqlalchemy import create_engine, text

from src.warehouse.config import warehouse_settings

ADMIN_URL = os.getenv("WAREHOUSE_ADMIN_URL", "postgresql+psycopg2://airflow:airflow@postgres:5432/airflow")


def _ident(name: str) -> str:
    # role/db names are interpolated into DDL, so only allow plain identifiers
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
        raise ValueError(f"Invalid identifier: {name!r}")
    return name


def setup() -> None:
    s = warehouse_settings()
    user, db = _ident(s["user"]), _ident(s["dbname"])
    password = s["password"].replace("'", "''")

    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        if not conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": user}):
            conn.exec_driver_sql(f"CREATE ROLE {user} LOGIN PASSWORD '{password}'")
            print(f"Created role {user}.")
        else:
            conn.exec_driver_sql(f"ALTER ROLE {user} PASSWORD '{password}'")
        if not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :d"), {"d": db}):
            conn.exec_driver_sql(f"CREATE DATABASE {db} OWNER {user}")
            print(f"Created database {db}.")
    admin.dispose()

    # raw schema belongs to the warehouse role; dbt creates staging/marts itself (it owns the db)
    wh_admin = create_engine(ADMIN_URL.rsplit("/", 1)[0] + f"/{db}", isolation_level="AUTOCOMMIT")
    with wh_admin.connect() as conn:
        conn.exec_driver_sql(f"CREATE SCHEMA IF NOT EXISTS raw AUTHORIZATION {user}")
    wh_admin.dispose()
    print("Warehouse ready.")


if __name__ == "__main__":
    setup()
