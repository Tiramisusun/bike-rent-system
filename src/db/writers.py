"""Database write helpers — insert and upsert operations."""

import logging
from datetime import datetime, timezone
from typing import Literal, Optional

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.db.models import Station, StationStatus, Weather, WeatherForecast, WeatherReport
from src.db.engine import load_engine

logger = logging.getLogger(__name__)


def _ensure_weather(session: Session, weather_data: dict, existing_ids: list[int]) -> int:
    """Insert a Weather row if not already present; return its id."""
    wid = weather_data["id"]
    if wid not in existing_ids:
        session.add(Weather(
            id=wid,
            main=weather_data["main"],
            description=weather_data["description"],
            icon=weather_data["icon"],
        ))
        existing_ids.append(wid)
    return wid


def _epoch_to_utc(ts) -> Optional[datetime]:
    """OpenWeather `dt` (epoch seconds) -> naive UTC datetime."""
    if not isinstance(ts, (int, float)):
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)


def _insert_weather(session: Session, json_obj: dict, fallback_time: datetime) -> None:
    """Upsert one current-weather observation, keyed on its observation time."""
    existing_ids: list[int] = list(session.scalars(select(Weather.id)).all())
    wid = _ensure_weather(session, json_obj["weather"][0], existing_ids)
    session.flush()  # weather row must exist before the FK'd upsert below

    main = json_obj.get("main", {})
    wind = json_obj.get("wind", {})
    row = {
        "update_time": _epoch_to_utc(json_obj.get("dt")) or fallback_time,
        "temp": main.get("temp"),
        "feels_like": main.get("feels_like"),
        "humidity": main.get("humidity"),
        "wind_speed": wind.get("speed"),
        "visibility": json_obj.get("visibility", 0),
        "weather_id": wid,
    }
    _upsert(session, WeatherReport.__table__, [row], key_cols=["update_time"],
            update_cols=[c for c in row if c != "update_time"])


def _ms_to_utc(tm) -> Optional[datetime]:
    """JCDecaux `last_update` (epoch ms) -> naive UTC datetime."""
    if not isinstance(tm, (int, float)):
        return None
    return datetime.fromtimestamp(tm / 1000, tz=timezone.utc).replace(tzinfo=None)


def _upsert(session: Session, table, rows: list[dict], key_cols: list[str],
            update_cols: list[str]) -> None:
    """Insert rows; on key conflict update `update_cols` (or skip if empty)."""
    if not rows:
        return
    dialect = session.get_bind().dialect.name
    if dialect == "mysql":
        stmt = mysql_insert(table).values(rows)
        if update_cols:
            stmt = stmt.on_duplicate_key_update({c: stmt.inserted[c] for c in update_cols})
        else:
            # No-op update: duplicate rows are silently skipped.
            stmt = stmt.on_duplicate_key_update({key_cols[0]: table.c[key_cols[0]]})
    elif dialect == "sqlite":
        stmt = sqlite_insert(table).values(rows)
        if update_cols:
            stmt = stmt.on_conflict_do_update(
                index_elements=key_cols,
                set_={c: stmt.excluded[c] for c in update_cols},
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=key_cols)
    else:
        raise NotImplementedError(f"Upsert not supported for dialect: {dialect}")
    session.execute(stmt)


def _insert_bike_dynamic(session: Session, json_obj: list) -> int:
    """Upsert station snapshots; returns how many were new."""
    rows = []
    for station in json_obj:
        update_time = _ms_to_utc(station.get("last_update"))
        if update_time is None or station.get("number") is None:
            # Without the source timestamp the row can't be deduplicated.
            logger.warning(f"Skipping status without last_update/number: {station.get('number')}")
            continue
        rows.append({
            "station_id": station["number"],
            "update_time": update_time,
            "avail_bikes": station.get("available_bikes"),
            "avail_bike_stands": station.get("available_bike_stands"),
            "status": station.get("status"),
        })
    if not rows:
        return 0

    # Count genuinely new snapshots (MySQL rowcount can't tell inserts from no-ops).
    existing = set(session.execute(
        select(StationStatus.station_id, StationStatus.update_time)
        .where(StationStatus.update_time >= min(r["update_time"] for r in rows))
    ).tuples())
    new_count = sum((r["station_id"], r["update_time"]) not in existing for r in rows)

    _upsert(session, StationStatus.__table__, rows,
            key_cols=["station_id", "update_time"], update_cols=[])
    return new_count


def _insert_bike_static(session: Session, json_obj: list) -> int:
    """Upsert station metadata; returns the number of stations in the payload."""
    rows = [
        {
            "station_id": item.get("number"),
            "contract": item.get("contract_name", ""),
            "name": item.get("name", ""),
            "longitude": item.get("position", {}).get("lng") or item.get("longitude"),
            "latitude": item.get("position", {}).get("lat") or item.get("latitude"),
            "bike_stands": item.get("bike_stands"),
        }
        for item in json_obj
    ]
    _upsert(session, Station.__table__, rows, key_cols=["station_id"],
            update_cols=["contract", "name", "longitude", "latitude", "bike_stands"])
    return len(rows)


def db_from_request(
    json_obj: dict,
    typ: Literal["weather", "bike-dynamic", "bike-static"],
    engine: Optional[Engine] = None,
) -> Optional[int]:
    """Insert records from an in-memory JSON object.

    For bike payloads, returns the number of rows inserted/changed.
    """
    if not engine:
        engine = load_engine()

    with Session(engine) as session:
        count = None
        if typ == "weather":
            _insert_weather(session, json_obj, datetime.now(timezone.utc).replace(tzinfo=None))
        elif typ == "bike-dynamic":
            count = _insert_bike_dynamic(session, json_obj)
        elif typ == "bike-static":
            count = _insert_bike_static(session, json_obj)
        else:
            raise ValueError(f"Unknown type: {typ}")
        session.commit()
        return count


def store_forecast_data(engine: Engine, forecast_list: list,
                        fetched_at: Optional[datetime] = None) -> int:
    """Upsert OpenWeather 3-hourly forecast entries (one row per forecast_time).

    Returns the number of forecast rows written.
    """
    fetched_at = fetched_at or datetime.now(timezone.utc).replace(tzinfo=None)
    with Session(engine) as session:
        existing_ids: list[int] = list(session.scalars(select(Weather.id)).all())
        rows = []
        for entry in forecast_list:
            wid = _ensure_weather(session, entry["weather"][0], existing_ids)
            main = entry.get("main", {})
            rows.append({
                "forecast_time": _epoch_to_utc(entry["dt"]),
                "fetched_at": fetched_at,
                "temp": main.get("temp"),
                "feels_like": main.get("feels_like"),
                "humidity": main.get("humidity"),
                "wind_speed": entry.get("wind", {}).get("speed"),
                "visibility": entry.get("visibility"),
                "weather_id": wid,
            })
        session.flush()
        _upsert(session, WeatherForecast.__table__, rows, key_cols=["forecast_time"],
                update_cols=[c for c in rows[0] if c != "forecast_time"] if rows else [])
        session.commit()
        return len(rows)
