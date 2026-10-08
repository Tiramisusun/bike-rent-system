"""Run a validated query on the agent's read-only connection and return JSON-safe rows."""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list]


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    return value


def run_query(engine: Engine, sql: str) -> QueryResult:
    """Execute `sql` (already passed guardrails.validate_sql) read-only.

    The agent_ro role already forces read-only transactions and a statement
    timeout; SET LOCAL repeats both so a misconfigured role can't remove them.
    """
    with engine.connect() as conn:
        with conn.begin():
            conn.exec_driver_sql("SET LOCAL TRANSACTION READ ONLY")
            conn.exec_driver_sql("SET LOCAL statement_timeout = '5s'")
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = [[_json_safe(v) for v in row] for row in result.fetchall()]
    return QueryResult(columns, rows)
