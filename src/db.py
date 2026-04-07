"""Database models and helper functions for the Dublin Bike & Weather app."""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional

import click
import pymysql
from dotenv import load_dotenv
from sqlalchemy import DateTime, Double, ForeignKey, String, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Relationship, Session, mapped_column

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    def __repr__(self):
        return f"User(id={self.id}, email={self.email})"


class Rental(Base):
    __tablename__ = "rental"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    pickup_station_id: Mapped[int] = mapped_column(ForeignKey("station.station_id"), nullable=False)
    dropoff_station_id: Mapped[Optional[int]] = mapped_column(ForeignKey("station.station_id"), nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_minutes: Mapped[Optional[int]] = mapped_column(nullable=True)
    cost_eur: Mapped[Optional[float]] = mapped_column(nullable=True)

    def __repr__(self):
        return f"Rental(id={self.id}, user={self.user_id}, start={self.start_time})"


class Weather(Base):
    __tablename__ = "weather"

    id: Mapped[int] = mapped_column(primary_key=True)
    main: Mapped[str] = mapped_column(String(15))
    description: Mapped[str] = mapped_column(String(30))
    icon: Mapped[str] = mapped_column(String(10))

    def __repr__(self):
        return f"Weather(id={self.id}, main={self.main}, description={self.description})"


class WeatherReport(Base):
    __tablename__ = "weather_report"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    update_time: Mapped[datetime] = mapped_column(DateTime)
    temp: Mapped[float]
    feels_like: Mapped[float]
    visibility: Mapped[int]
    wind_speed: Mapped[float]
    humidity: Mapped[int]
    weather_id: Mapped[int] = mapped_column(ForeignKey("weather.id"))

    def __repr__(self):
        return f"WeatherReport(id={self.id}, temp={self.temp}, update_time={self.update_time})"


class Forecast(Base):
    __tablename__ = "forecast"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    datetime: Mapped[int]
    period: Mapped[str] = mapped_column(String(15))
    temp: Mapped[float]
    weather_id: Mapped[int] = mapped_column(ForeignKey("weather.id"))
    weather: Mapped["Weather"] = Relationship()
    report_id: Mapped[int] = mapped_column("report", ForeignKey("weather_report.id"))
    report: Mapped["WeatherReport"] = Relationship()

    def __repr__(self):
        return f"Forecast(id={self.id}, datetime={self.datetime}, period={self.period})"


class Station(Base):
    __tablename__ = "station"

    station_id: Mapped[int] = mapped_column(primary_key=True)
    contract: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(60))
    longitude: Mapped[float] = mapped_column(type_=Double)
    latitude: Mapped[float] = mapped_column(type_=Double)
    address: Mapped[List["Address"]] = Relationship(back_populates="station", cascade="all, delete-orphan")

    def __repr__(self):
        return f"Station(id={self.station_id}, name={self.name})"


class StationStatus(Base):
    __tablename__ = "station_status"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    station_id = mapped_column(ForeignKey("station.station_id"))
    station: Mapped["Station"] = Relationship()
    update_time: Mapped[datetime] = mapped_column(DateTime)
    avail_bikes: Mapped[int]
    avail_bike_stands: Mapped[int]
    status: Mapped[str] = mapped_column(String(15))

    def __repr__(self):
        return f"StationStatus(id={self.id}, station_id={self.station_id}, avail_bikes={self.avail_bikes})"


class Address(Base):
    __tablename__ = "address"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    station_id = mapped_column(ForeignKey("station.station_id"))
    station: Mapped["Station"] = Relationship()
    street1: Mapped[str] = mapped_column(String(30))
    street2: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    county: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    eircode: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)

    def __repr__(self):
        return f"Address(id={self.id}, street={self.street1}, eircode={self.eircode})"


# ---------------------------------------------------------------------------
# Engine / init
# ---------------------------------------------------------------------------

def load_engine() -> Engine:
    """Load and return a SQLAlchemy engine from DB_URL in .env."""
    try:
        assert load_dotenv(), "Could not load .env variables."
        db_url = os.getenv("DB_URL")
        assert db_url, "Could not find required DB_URL."
        return create_engine(db_url)
    except Exception as e:
        logger.error(f"Failed to load SQL engine: {e}")
        raise


def init_db(engine: Engine) -> None:
    """Create database and all tables if they do not exist."""
    try:
        url = engine.url
        conn = pymysql.connect(
            host=url.host,
            port=url.port or 3306,
            user=url.username,
            password=url.password,
        )
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{url.database}`")
        conn.close()

        Base.metadata.create_all(engine)
        logger.info(f"Initialized {len(Base.metadata.tables)} tables.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

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


def db_from_file(
    filepath,
    typ: Literal["weather", "bike-dynamic", "bike-static"],
    engine: Optional[Engine] = None,
    parse_time: bool = False,
) -> None:
    """Insert records from a single JSON file."""
    if not engine:
        engine = load_engine()

    fp = Path(filepath)
    assert fp.suffix == ".json", "Expected a .json file."

    time = None
    if parse_time:
        timestamp = fp.stem.split("_")[1]
        time = datetime.strptime(timestamp, "%Y%m%dT%H%M%S")

    with open(fp) as f:
        json_obj = json.load(f)

    with Session(engine) as session:
        if typ == "weather":
            _insert_weather(session, json_obj, time or datetime.now(timezone.utc).replace(tzinfo=None))
        elif typ == "bike-dynamic":
            _insert_bike_dynamic(session, json_obj)
        elif typ == "bike-static":
            _insert_bike_static(session, json_obj)
        else:
            raise ValueError(f"Unknown type: {typ}")
        session.commit()


def db_from_directory(
    directory,
    typ: Literal["weather", "bike-dynamic", "bike-static"],
    engine: Optional[Engine] = None,
    parse_time: bool = False,
) -> None:
    """Insert records from all JSON files in a directory."""
    if not engine:
        engine = load_engine()

    for root, _, files in os.walk(directory):
        for fname in files:
            fp = Path(root) / fname
            if fp.suffix != ".json":
                continue
            try:
                db_from_file(fp, typ, engine, parse_time)
            except Exception as e:
                logger.warning(f"Skipping {fp}: {e}")


def db_from_multi_dir(
    dir_list: list[tuple[str, Literal["weather", "bike-dynamic", "bike-static"]]],
    engine: Optional[Engine] = None,
) -> None:
    """Insert records from multiple directories."""
    if not engine:
        engine = load_engine()
    for directory, typ in dir_list:
        db_from_directory(directory, typ, engine)


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

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
    """Return historical status records for a single station."""
    with Session(engine) as session:
        statuses = session.scalars(
            select(StationStatus)
            .where(StationStatus.station_id == station_id)
            .order_by(StationStatus.update_time.asc())
        ).all()
        return [
            {
                "avail_bikes": s.avail_bikes,
                "avail_bike_stands": s.avail_bike_stands,
                "update_time": s.update_time.isoformat(),
            }
            for s in statuses
        ]


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


# ---------------------------------------------------------------------------
# Click CLI
# ---------------------------------------------------------------------------

@click.command(name="init-db", short_help="Initialize db, create all required tables")
def init_db_click():
    engine = load_engine()
    init_db(engine)
    click.echo("DB successfully initialized.")


@click.command(name="file", short_help="Insert data from a single JSON file")
@click.argument("filepath", type=click.Path(exists=True))
@click.argument("typ", type=click.Choice(["weather", "bike-dynamic", "bike-static"]))
@click.option("-p", "--parse-time", is_flag=True, default=False)
def db_from_file_click(filepath, typ, parse_time):
    db_from_file(filepath, typ, parse_time=parse_time)
    click.echo(f"Processed: {filepath}")


@click.command(name="dir", short_help="Insert data from a directory of JSON files")
@click.argument("directory", type=click.Path(exists=True))
@click.argument("typ", type=click.Choice(["weather", "bike-dynamic", "bike-static"]))
@click.option("-p", "--parse-time", is_flag=True, default=False)
def db_from_directory_click(directory, typ, parse_time):
    db_from_directory(directory, typ, parse_time=parse_time)
    click.echo(f"Processed directory: {directory}")


@click.command(name="multi-dir", short_help="Insert to DB from multiple directories")
@click.option(
    "-d", "--directories",
    multiple=True,
    type=(click.Path(exists=True), click.Choice(["weather", "bike-dynamic", "bike-static"])),
)
def db_from_multi_dir_click(directories):
    db_from_multi_dir(list(directories))
    click.echo(f"Processed: {directories}")


@click.group(name="db", short_help="DB initialization and bulk insertion tools")
def cli():
    pass


cli.add_command(init_db_click)
cli.add_command(db_from_file_click)
cli.add_command(db_from_directory_click)
cli.add_command(db_from_multi_dir_click)


if __name__ == "__main__":
    cli()
