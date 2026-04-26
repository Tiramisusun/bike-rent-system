"""Database read helpers — query operations."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.db.models import Forecast, Station, StationStatus, WeatherReport


def get_latest_weather(engine: Engine) -> dict | None:
    """Return the most recent WeatherReport as a dict, or None."""
    with Session(engine) as session:
        report = session.scalars(
            select(WeatherReport).order_by(WeatherReport.update_time.desc()).limit(1)
        ).first()
        if not report:
            return None
        return {
            "id": report.id,
            "temp": report.temp,
            "feels_like": report.feels_like,
            "humidity": report.humidity,
            "wind_speed": report.wind_speed,
            "visibility": report.visibility,
            "update_time": report.update_time.isoformat(),
            "weather_id": report.weather_id,
        }


def get_all_stations(engine: Engine) -> list[dict]:
    """Return all stations as a list of dicts."""
    with Session(engine) as session:
        stations = session.scalars(select(Station)).all()
        return [
            {
                "station_id": s.station_id,
                "name": s.name,
                "contract": s.contract,
                "longitude": s.longitude,
                "latitude": s.latitude,
            }
            for s in stations
        ]


def get_latest_station_status(engine: Engine) -> list[dict]:
    """Return all station status rows ordered by most recent first."""
    with Session(engine) as session:
        statuses = session.scalars(
            select(StationStatus).order_by(StationStatus.update_time.desc())
        ).all()
        return [
            {
                "id": s.id,
                "station_id": s.station_id,
                "avail_bikes": s.avail_bikes,
                "avail_bike_stands": s.avail_bike_stands,
                "status": s.status,
                "update_time": s.update_time.isoformat(),
            }
            for s in statuses
        ]


def get_station_history(engine: Engine, station_id: int) -> list[dict]:
    """Return the most recent continuous segment of status records for a station.

    Looks back up to 14 days and trims the result to the latest unbroken run,
    where a break is defined as a gap of more than 2 hours between consecutive
    records.
    """
    from datetime import timedelta
    GAP_THRESHOLD = timedelta(hours=2)
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    with Session(engine) as session:
        statuses = session.scalars(
            select(StationStatus)
            .where(
                StationStatus.station_id == station_id,
                StationStatus.update_time >= cutoff,
            )
            .order_by(StationStatus.update_time.asc())
        ).all()

        if not statuses:
            return []

        # Walk backwards to find the start of the most recent continuous segment
        i = len(statuses) - 1
        while i > 0:
            gap = statuses[i].update_time - statuses[i - 1].update_time
            if gap > GAP_THRESHOLD:
                break
            i -= 1
        statuses = statuses[i:]

        return [
            {
                "avail_bikes": s.avail_bikes,
                "avail_bike_stands": s.avail_bike_stands,
                "update_time": s.update_time.isoformat(),
            }
            for s in statuses
        ]


def get_forecast_data(engine: Engine) -> list[dict]:
    """Return all forecast entries ordered by time ascending."""
    with Session(engine) as session:
        forecasts = session.scalars(
            select(Forecast).order_by(Forecast.datetime.asc())
        ).all()
        return [
            {
                "dt": f.datetime,
                "time": datetime.fromtimestamp(f.datetime, tz=timezone.utc).strftime("%a %H:%M"),
                "temp": round(f.temp),
                "period": f.period,
                "weather_id": f.weather_id,
            }
            for f in forecasts
        ]
