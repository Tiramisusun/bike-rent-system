"""Database read helpers — query operations."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.db.models import Station, StationStatus, Weather, WeatherForecast, WeatherReport


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


def get_latest_availability(
    engine: Engine, drop_after: timedelta = timedelta(hours=24)
) -> tuple[list[dict], datetime | None]:
    """Latest snapshot per station, in the JCDecaux /stations shape the frontend uses.

    Stations whose latest snapshot is more than `drop_after` older than the newest
    snapshot overall are left out (they've disappeared from the live feed).
    Returns (stations, newest snapshot time as naive UTC or None).
    """
    latest = (
        select(StationStatus.station_id, func.max(StationStatus.update_time).label("t"))
        .group_by(StationStatus.station_id)
        .subquery()
    )
    query = (
        select(Station, StationStatus)
        .join(StationStatus, StationStatus.station_id == Station.station_id)
        .join(latest, (latest.c.station_id == StationStatus.station_id)
              & (latest.c.t == StationStatus.update_time))
    )
    with Session(engine) as session:
        rows = session.execute(query).all()
    if not rows:
        return [], None

    newest = max(status.update_time for _, status in rows)
    stations = [
        {
            "number": station.station_id,
            "contract_name": station.contract,
            "name": station.name,
            "position": {"lat": station.latitude, "lng": station.longitude},
            "bike_stands": station.bike_stands,
            "available_bikes": status.avail_bikes,
            "available_bike_stands": status.avail_bike_stands,
            "status": status.status,
            "last_update": int(status.update_time.replace(tzinfo=timezone.utc).timestamp() * 1000),
        }
        for station, status in rows
        if newest - status.update_time <= drop_after
    ]
    return sorted(stations, key=lambda s: s["number"]), newest


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


def _utc_epoch(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def get_current_weather(engine: Engine) -> tuple[dict | None, datetime | None]:
    """Latest observation in the OpenWeather /weather shape, plus its time (naive UTC)."""
    with Session(engine) as session:
        row = session.execute(
            select(WeatherReport, Weather)
            .join(Weather, Weather.id == WeatherReport.weather_id, isouter=True)
            .order_by(WeatherReport.update_time.desc())
            .limit(1)
        ).first()
    if not row:
        return None, None
    report, condition = row
    payload = {
        "dt": _utc_epoch(report.update_time),
        "main": {"temp": report.temp, "feels_like": report.feels_like, "humidity": report.humidity},
        "wind": {"speed": report.wind_speed},
        "visibility": report.visibility,
        "weather": [{
            "id": report.weather_id,
            "main": condition.main if condition else None,
            "description": condition.description if condition else None,
            "icon": condition.icon if condition else None,
        }],
    }
    return payload, report.update_time


def get_forecast_data(engine: Engine) -> tuple[list[dict], datetime | None]:
    """Upcoming forecast entries (same fields as /api/weather/forecast), and when
    the newest forecast was fetched (naive UTC)."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with Session(engine) as session:
        rows = session.execute(
            select(WeatherForecast, Weather)
            .join(Weather, Weather.id == WeatherForecast.weather_id, isouter=True)
            .where(WeatherForecast.forecast_time >= now)
            .order_by(WeatherForecast.forecast_time.asc())
        ).all()
        fetched_at = session.scalar(select(func.max(WeatherForecast.fetched_at)))
    items = [
        {
            "dt": _utc_epoch(f.forecast_time),
            "time": f.forecast_time.strftime("%a %H:%M"),
            "temp": round(f.temp),
            "feels_like": round(f.feels_like) if f.feels_like is not None else None,
            "humidity": f.humidity,
            "description": w.description if w else None,
            "icon": w.icon if w else None,
            "wind_speed": f.wind_speed,
        }
        for f, w in rows
    ]
    return items, fetched_at
