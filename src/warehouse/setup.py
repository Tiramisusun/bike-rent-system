"""Create the warehouse role, database and raw schema in Postgres (idempotent).

Runs from airflow-init with the Postgres superuser (the Airflow metadata user):
    python -m src.warehouse.setup
"""

import os
import re

from sqlalchemy import create_engine, text

from src.warehouse.config import agent_settings, warehouse_settings

ADMIN_URL = os.getenv("WAREHOUSE_ADMIN_URL", "postgresql+psycopg2://airflow:airflow@postgres:5432/airflow")


def _ident(name: str) -> str:
    # role/db names are interpolated into DDL, so only allow plain identifiers
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
        raise ValueError(f"Invalid identifier: {name!r}")
    return name


# Limits for the Text-to-SQL agent's role, enforced by Postgres itself.
AGENT_STATEMENT_TIMEOUT = "5s"


def setup() -> None:
    s = warehouse_settings()
    user, db = _ident(s["user"]), _ident(s["dbname"])
    password = s["password"].replace("'", "''")
    a = agent_settings()
    agent, agent_password = _ident(a["user"]), a["password"].replace("'", "''")

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

        # Text-to-SQL agent: can log in, cannot write anything, queries time out.
        if not conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": agent}):
            conn.exec_driver_sql(f"CREATE ROLE {agent} LOGIN PASSWORD '{agent_password}'")
            print(f"Created role {agent}.")
        else:
            conn.exec_driver_sql(f"ALTER ROLE {agent} PASSWORD '{agent_password}'")
        conn.exec_driver_sql(f"ALTER ROLE {agent} SET default_transaction_read_only = on")
        conn.exec_driver_sql(f"ALTER ROLE {agent} SET statement_timeout = '{AGENT_STATEMENT_TIMEOUT}'")
        conn.exec_driver_sql(f"ALTER ROLE {agent} SET idle_in_transaction_session_timeout = '30s'")
        conn.exec_driver_sql(f"ALTER ROLE {agent} CONNECTION LIMIT 5")
        # Postgres lets PUBLIC connect to every database by default; only the
        # warehouse should be reachable by the warehouse and agent roles.
        for other in conn.scalars(text(
            "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> :d"), {"d": db}):
            conn.exec_driver_sql(f'REVOKE CONNECT ON DATABASE "{other}" FROM PUBLIC')
    admin.dispose()

    # raw schema belongs to the warehouse role; dbt creates staging/marts itself (it owns the db)
    wh_admin = create_engine(ADMIN_URL.rsplit("/", 1)[0] + f"/{db}", isolation_level="AUTOCOMMIT")
    with wh_admin.connect() as conn:
        conn.exec_driver_sql(f"CREATE SCHEMA IF NOT EXISTS raw AUTHORIZATION {user}")
        # The agent sees marts only — not raw/staging/intermediate, not other databases.
        conn.exec_driver_sql(f"CREATE SCHEMA IF NOT EXISTS marts AUTHORIZATION {user}")
        conn.exec_driver_sql(f"REVOKE ALL ON DATABASE {db} FROM PUBLIC")
        conn.exec_driver_sql(f"GRANT CONNECT ON DATABASE {db} TO {user}, {agent}")
        conn.exec_driver_sql(f"REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA marts TO {agent}")
        conn.exec_driver_sql(f"GRANT SELECT ON ALL TABLES IN SCHEMA marts TO {agent}")
        # dbt rebuilds the marts tables every run; new tables inherit the grant.
        conn.exec_driver_sql(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {user} IN SCHEMA marts GRANT SELECT ON TABLES TO {agent}"
        )
    wh_admin.dispose()
    print("Warehouse ready.")


if __name__ == "__main__":
    setup()
