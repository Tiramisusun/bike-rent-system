"""Ingestion health checks against MySQL, run every 10 minutes by dublinbikes_monitor.

These are the fast, operational counterpart to the dbt tests (which run hourly
on the warehouse): they answer "is data still arriving?" within the 15-minute SLA.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.db.models import StationStatus, WeatherReport


def _minutes(name: str, default: int) -> int:
    return int(os.getenv(name, default))


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _age_minutes(latest: datetime | None, now: datetime) -> float | None:
    return None if latest is None else (now - latest).total_seconds() / 60


def run_checks(engine: Engine, now: datetime | None = None) -> list[CheckResult]:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    max_snapshot_age = _minutes("MONITOR_MAX_SNAPSHOT_AGE_MIN", 15)
    max_weather_age = _minutes("MONITOR_MAX_WEATHER_AGE_MIN", 60)
    min_active_stations = _minutes("MONITOR_MIN_ACTIVE_STATIONS", 100)
    active_window = _minutes("MONITOR_ACTIVE_WINDOW_MIN", 30)

    with Session(engine) as s:
        latest_snapshot = s.scalar(select(func.max(StationStatus.update_time)))
        latest_weather = s.scalar(select(func.max(WeatherReport.update_time)))
        active = s.scalar(
            select(func.count(func.distinct(StationStatus.station_id)))
            .where(StationStatus.update_time >= now - timedelta(minutes=active_window))
        )

    results = []
    age = _age_minutes(latest_snapshot, now)
    results.append(CheckResult(
        "station_snapshots_fresh",
        age is not None and age <= max_snapshot_age,
        f"latest snapshot {latest_snapshot} UTC ({_fmt(age)} old, limit {max_snapshot_age} min)",
    ))
    age = _age_minutes(latest_weather, now)
    results.append(CheckResult(
        "weather_fresh",
        age is not None and age <= max_weather_age,
        f"latest observation {latest_weather} UTC ({_fmt(age)} old, limit {max_weather_age} min)",
    ))
    # A feed that still updates but only for a few stations is also broken.
    results.append(CheckResult(
        "stations_reporting",
        active >= min_active_stations,
        f"{active} stations reported in the last {active_window} min (minimum {min_active_stations})",
    ))
    return results


def _fmt(age: float | None) -> str:
    return "no data" if age is None else f"{age:.0f} min"


class IngestionUnhealthy(Exception):
    pass


def assert_healthy(engine: Engine | None = None) -> list[str]:
    """Entry point for Airflow: raise (-> task fails -> alert) if any check fails."""
    from src.db import load_engine
    results = run_checks(engine or load_engine())
    lines = [f"[{'OK' if r.ok else 'FAIL'}] {r.name}: {r.detail}" for r in results]
    if not all(r.ok for r in results):
        raise IngestionUnhealthy("\n".join(lines))
    return lines
