"""
src/db — database package.

Re-exports everything so that other modules can continue to use:
    from src.db import Station, get_latest_weather, db_from_request, ...
without any changes.
"""

from src.db.models import (
    Base,
    User,
    Rental,
    Weather,
    WeatherReport,
    Forecast,
    Station,
    StationStatus,
    Address,
)

from src.db.engine import load_engine, init_db

from src.db.writers import db_from_request, store_forecast_data

from src.db.readers import (
    get_latest_weather,
    get_all_stations,
    get_latest_station_status,
    get_station_history,
    get_forecast_data,
)

__all__ = [
    # models
    "Base", "User", "Rental", "Weather", "WeatherReport",
    "Forecast", "Station", "StationStatus", "Address",
    # engine
    "load_engine", "init_db",
    # writers
    "db_from_request", "store_forecast_data",
    # readers
    "get_latest_weather", "get_all_stations",
    "get_latest_station_status", "get_station_history", "get_forecast_data",
]
