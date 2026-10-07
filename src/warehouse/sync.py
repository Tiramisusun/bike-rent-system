"""Copy operational tables from MySQL into the warehouse `raw` schema.

- station_status grows every 5 minutes, so it is copied incrementally by id.
  An auto-increment id is assigned at insert but becomes visible at commit, so a
  slower transaction can commit a *lower* id after a higher one was synced. Each
  run therefore re-reads the last LOOKBACK_IDS ids and skips rows it already has
  (ON CONFLICT DO NOTHING) instead of trusting max(id) exactly.
- The other tables are small and can change in place (upserts), so they are
  fully refreshed inside one transaction — readers never see a half-empty table.
- `user` is deliberately not copied: it holds e-mails and password hashes that
  analytics doesn't need.
"""

import logging
from typing import Optional

from sqlalchemy import Column, MetaData, Table, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine

from src.db.models import Base

logger = logging.getLogger(__name__)

FULL_REFRESH = ["station", "weather", "weather_report", "weather_forecast", "rental"]
INCREMENTAL = {"station_status": "id"}
BATCH_SIZE = 5000
LOOKBACK_IDS = 1000


def _target_table(source: Table, metadata: MetaData, schema: Optional[str]) -> Table:
    """Same columns and primary key as the source, no foreign keys or defaults."""
    return Table(
        source.name, metadata,
        *[Column(c.name, c.type, primary_key=c.primary_key, autoincrement=False,
                 nullable=c.nullable) for c in source.columns],
        schema=schema,
    )


def _insert_ignoring_existing(target: Table, dialect: str):
    if dialect == "postgresql":
        return pg_insert(target).on_conflict_do_nothing()
    if dialect == "sqlite":
        return sqlite_insert(target).on_conflict_do_nothing()
    raise NotImplementedError(dialect)


def _copy(src: Engine, query, dst_conn, stmt) -> int:
    """Stream `query` from src in batches; return rows actually inserted."""
    copied = 0
    with src.connect() as s:
        result = s.execution_options(yield_per=BATCH_SIZE).execute(query)
        for batch in result.mappings().partitions():
            copied += dst_conn.execute(stmt, [dict(r) for r in batch]).rowcount
    return copied


def sync(source: Engine, target: Engine, schema: Optional[str] = "raw") -> dict:
    metadata = MetaData()
    tables = {name: _target_table(Base.metadata.tables[name], metadata, schema)
              for name in FULL_REFRESH + list(INCREMENTAL)}
    metadata.create_all(target)

    counts = {}
    for name in FULL_REFRESH:
        with target.begin() as conn:            # delete + reload is one transaction
            conn.execute(tables[name].delete())
            counts[name] = _copy(source, select(Base.metadata.tables[name]), conn,
                                 insert(tables[name]))

    for name, key in INCREMENTAL.items():
        src_table, dst_table = Base.metadata.tables[name], tables[name]
        with target.begin() as conn:
            high_water = conn.scalar(select(func.max(dst_table.c[key]))) or 0
            query = (select(src_table).where(src_table.c[key] > high_water - LOOKBACK_IDS)
                     .order_by(src_table.c[key]))
            counts[name] = _copy(source, query, conn,
                                 _insert_ignoring_existing(dst_table, target.dialect.name))

    logger.info(f"Synced to warehouse: {counts}")
    return counts


def run() -> dict:
    """Entry point for Airflow: MySQL (DB_URL) -> warehouse raw schema."""
    from src.db import load_engine
    from src.warehouse.config import warehouse_engine
    return sync(load_engine(), warehouse_engine())
