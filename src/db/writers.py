"""Database write helpers — insert and upsert operations."""

import logging
from datetime import datetime, timezone
from typing import Literal, Optional

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.db.models import Forecast, Station, StationStatus, Weather, WeatherReport
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


def _insert_weather(session: Session, json_obj: dict, time: datetime) -> None:
    existing_ids: list[int] = list(session.scalars(select(Weather.id)).all())

    weather_data = json_obj["weather"][0]
    main = json_obj.get("main", {})
    wind = json_obj.get("wind", {})
    wid = _ensure_weather(session, weather_data, existing_ids)

    report = WeatherReport(
        update_time=time,
        temp=main.get("temp"),
        feels_like=main.get("feels_like"),
        humidity=main.get("humidity"),
        wind_speed=wind.get("speed"),
        visibility=json_obj.get("visibility", 0),
        weather_id=wid,
    )
    session.add(report)

    for entry in json_obj.get("hourly", []):
        hw = entry["weather"][0]
        hwid = _ensure_weather(session, hw, existing_ids)
        session.add(Forecast(
            weather_id=hwid,
            report=report,
            temp=entry.get("temp"),
            period="hourly",
            datetime=entry.get("dt"),
        ))


def _insert_bike_dynamic(session: Session, json_obj: list) -> None:
    for station in json_obj:
        tm = station.get("last_update")
        update_time = (
            datetime.fromtimestamp(tm / 1000, tz=timezone.utc).replace(tzinfo=None)
            if isinstance(tm, int)
            else datetime.now(timezone.utc).replace(tzinfo=None)
        )
        session.add(StationStatus(
            station_id=station.get("number"),
            update_time=update_time,
            avail_bikes=station.get("available_bikes"),
            avail_bike_stands=station.get("available_bike_stands"),
            status=station.get("status"),
        ))


def _insert_bike_static(session: Session, json_obj: list) -> None:
    for item in json_obj:
        station = Station(
            station_id=item.get("number"),
            contract=item.get("contract_name", ""),
            name=item.get("name", ""),
            longitude=item.get("position", {}).get("lng") or item.get("longitude"),
            latitude=item.get("position", {}).get("lat") or item.get("latitude"),
        )
        session.merge(station)


def db_from_request(
    json_obj: dict,
    typ: Literal["weather", "bike-dynamic", "bike-static"],
    engine: Optional[Engine] = None,
) -> None:
    """Insert records from an in-memory JSON object."""
    if not engine:
        engine = load_engine()

    with Session(engine) as session:
        if typ == "weather":
            _insert_weather(session, json_obj, datetime.now(timezone.utc).replace(tzinfo=None))
        elif typ == "bike-dynamic":
            _insert_bike_dynamic(session, json_obj)
        elif typ == "bike-static":
            _insert_bike_static(session, json_obj)
        else:
            raise ValueError(f"Unknown type: {typ}")
        session.commit()


def store_forecast_data(engine: Engine, forecast_list: list) -> None:
    """Persist a list of OpenWeather 3-hourly forecast entries."""
    with Session(engine) as session:
        existing_ids: list[int] = list(session.scalars(select(Weather.id)).all())

        for entry in forecast_list:
            w = entry["weather"][0]
            wid = _ensure_weather(session, w, existing_ids)

            update_time = datetime.fromtimestamp(entry["dt"], tz=timezone.utc).replace(tzinfo=None)
            report = WeatherReport(
                update_time=update_time,
                temp=entry["main"]["temp"],
                feels_like=entry["main"]["feels_like"],
                humidity=entry["main"]["humidity"],
                wind_speed=entry["wind"]["speed"],
                visibility=entry.get("visibility", 0),
                weather_id=wid,
            )
            session.add(report)
            session.flush()

            session.add(Forecast(
                datetime=entry["dt"],
                period="3hourly",
                temp=entry["main"]["temp"],
                weather_id=wid,
                report_id=report.id,
            ))

        session.commit()
