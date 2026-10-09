"""Extract/load steps used by the Airflow DAG (and runnable by hand).

extract_* : call the API and archive the raw JSON; return the file path.
load_*    : read an archived file and write it to MySQL idempotently.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.engine import Engine

from src.db import db_from_request, load_engine, store_forecast_data
from src.ingest.raw_archive import fetched_at_from_path, load_raw, save_raw
from src.services.bikes_service import fetch_jcdecaux_stations
from src.services.weather_service import fetch_openweather_current, fetch_openweather_forecast

logger = logging.getLogger(__name__)


def extract_bikes(fetched_at: Optional[datetime] = None) -> str:
    stations = fetch_jcdecaux_stations()
    if not stations:
        raise ValueError("JCDecaux returned no stations")
    path = save_raw("bikes", stations, fetched_at)
    logger.info(f"Archived {len(stations)} stations -> {path}")
    return str(path)


def load_bikes(path: str, engine: Optional[Engine] = None) -> dict:
    stations = load_raw(path)
    engine = engine or load_engine()
    n_stations = db_from_request(stations, "bike-static", engine=engine)
    n_new = db_from_request(stations, "bike-dynamic", engine=engine)
    result = {"stations": n_stations, "new_snapshots": n_new,
              "duplicates_skipped": len(stations) - n_new}
    logger.info(f"Loaded {path}: {result}")
    return result


def extract_weather(fetched_at: Optional[datetime] = None) -> str:
    path = save_raw("weather_current", fetch_openweather_current(), fetched_at)
    logger.info(f"Archived current weather -> {path}")
    return str(path)


def load_weather(path: str, engine: Optional[Engine] = None) -> None:
    engine = engine or load_engine()
    db_from_request(load_raw(path), "weather", engine=engine)
    logger.info(f"Loaded current weather from {path}")


def extract_forecast(fetched_at: Optional[datetime] = None) -> str:
    payload = fetch_openweather_forecast()
    if not payload.get("list"):
        raise ValueError("OpenWeather returned an empty forecast")
    path = save_raw("weather_forecast", payload, fetched_at)
    logger.info(f"Archived {len(payload['list'])} forecast entries -> {path}")
    return str(path)


def load_forecast(path: str, engine: Optional[Engine] = None) -> int:
    engine = engine or load_engine()
    n = store_forecast_data(engine, load_raw(path).get("list", []),
                            fetched_at=fetched_at_from_path(path))
    logger.info(f"Loaded {n} forecast rows from {path}")
    return n
