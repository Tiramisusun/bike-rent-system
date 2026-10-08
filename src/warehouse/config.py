"""Warehouse connection settings, shared by the sync job and dbt (warehouse/profiles.yml)."""

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def warehouse_settings() -> dict:
    return {
        "host": os.getenv("WAREHOUSE_HOST", "postgres"),
        "port": int(os.getenv("WAREHOUSE_PORT", 5432)),
        "user": os.getenv("WAREHOUSE_USER", "warehouse"),
        "password": os.getenv("WAREHOUSE_PASSWORD", "warehouse"),
        "dbname": os.getenv("WAREHOUSE_DB", "warehouse"),
    }


def warehouse_engine() -> Engine:
    url = os.getenv("WAREHOUSE_URL")
    if not url:
        s = warehouse_settings()
        url = f"postgresql+psycopg2://{s['user']}:{s['password']}@{s['host']}:{s['port']}/{s['dbname']}"
    return create_engine(url, pool_pre_ping=True)


def agent_settings() -> dict:
    """Read-only role used by the Text-to-SQL agent (see src/warehouse/setup.py)."""
    s = warehouse_settings()
    return {**s, "user": os.getenv("AGENT_DB_USER", "agent_ro"),
            "password": os.getenv("AGENT_DB_PASSWORD", "agent_ro")}


def agent_engine() -> Engine:
    url = os.getenv("AGENT_DB_URL")
    if not url:
        s = agent_settings()
        url = f"postgresql+psycopg2://{s['user']}:{s['password']}@{s['host']}:{s['port']}/{s['dbname']}"
    return create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=2)

