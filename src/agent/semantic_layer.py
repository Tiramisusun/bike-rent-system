"""The agent's view of the warehouse: marts tables, their columns, and the dbt docs.

Columns and types come from the database (what actually exists right now);
descriptions and metric definitions come from the dbt YAML in warehouse/models/
(what the columns *mean*). With `include_docs=False` the agent only gets names
and types — the baseline for the ablation in agent/eval.
"""

import os
import time
from pathlib import Path

import yaml
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.agent.guardrails import ALLOWED_SCHEMA

DBT_MODELS_DIR = Path(os.getenv("DBT_MODELS_DIR", Path(__file__).resolve().parents[2] / "warehouse" / "models"))
_CACHE_SECONDS = 600
_cache: dict = {}

# Business conventions defined in warehouse/dbt_project.yml (vars) and the marts SQL.
BUSINESS_RULES = """\
- All *_local columns and hour_key are Europe/Dublin local time; *_utc columns are UTC.
- Peak hours: working days (Mon-Fri, not an Irish public holiday), local hours 7-9 and 16-19.
  Use dim_time.is_peak_hour rather than re-deriving it.
- A station is "empty" when open with 0 bikes and "full" when open with 0 free docks.
- minutes_observed: how long a snapshot's state lasted, capped at 30 min. Durations such as
  empty/full minutes are sums of minutes_observed, never counts of snapshots.
- Prefer the pre-computed metrics in mart_station_kpis and agg_station_hourly over recomputing them."""


def _load_dbt_docs() -> dict[str, dict]:
    """{model_name: {"description": str, "columns": {col: description}}} for marts models."""
    docs: dict[str, dict] = {}
    for path in sorted((DBT_MODELS_DIR / "marts").glob("*.yml")):
        for model in (yaml.safe_load(path.read_text()) or {}).get("models", []):
            docs[model["name"]] = {
                "description": " ".join((model.get("description") or "").split()),
                "columns": {c["name"]: " ".join((c.get("description") or "").split())
                            for c in model.get("columns", [])},
            }
    return docs


def _load_columns(engine: Engine) -> dict[str, list[tuple[str, str]]]:
    query = text("""
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = :schema
        ORDER BY table_name, ordinal_position
    """)
    tables: dict[str, list[tuple[str, str]]] = {}
    with engine.connect() as conn:
        for table, column, dtype in conn.execute(query, {"schema": ALLOWED_SCHEMA}):
            tables.setdefault(table, []).append((column, dtype))
    return tables


def _load_data_range(engine: Engine) -> str:
    try:
        with engine.connect() as conn:
            first, last = conn.execute(text(
                f"SELECT min(snapshot_at_local), max(snapshot_at_local) FROM {ALLOWED_SCHEMA}.fct_station_snapshot"
            )).one()
        return f"Station snapshots cover {first:%Y-%m-%d %H:%M} to {last:%Y-%m-%d %H:%M} (Dublin local time)."
    except Exception:
        return ""


def build_schema_context(engine: Engine, include_docs: bool = True) -> tuple[str, set[str]]:
    """Prompt text describing the marts, and the set of table names the agent may query."""
    key = (id(engine), include_docs)
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < _CACHE_SECONDS:
        return cached[1], cached[2]

    columns = _load_columns(engine)
    docs = _load_dbt_docs() if include_docs else {}
    lines = []
    for table in sorted(columns):
        table_doc = docs.get(table, {})
        header = f"Table {ALLOWED_SCHEMA}.{table}"
        if table_doc.get("description"):
            header += f" — {table_doc['description']}"
        lines.append(header)
        for column, dtype in columns[table]:
            line = f"  - {column} ({dtype})"
            description = table_doc.get("columns", {}).get(column)
            if description:
                line += f": {description}"
            lines.append(line)
        lines.append("")

    if include_docs:
        lines += ["Business rules:", BUSINESS_RULES, ""]
    data_range = _load_data_range(engine)
    if data_range:
        lines.append(data_range)

    context = "\n".join(lines).strip()
    _cache[key] = (time.monotonic(), context, set(columns))
    return context, set(columns)
