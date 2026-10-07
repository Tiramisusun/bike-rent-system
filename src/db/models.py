"""SQLAlchemy ORM models — one class per database table."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Double, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, Relationship, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )

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
    """Observed (current) weather only. Forecasts live in weather_forecast."""
    __tablename__ = "weather_report"
    # update_time is OpenWeather's observation time (`dt`), so re-polling is a no-op.
    __table_args__ = (UniqueConstraint("update_time", name="uq_weather_report_time"),)

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


class WeatherForecast(Base):
    """Latest 3-hourly forecast per target time (every vintage is kept in data/raw/)."""
    __tablename__ = "weather_forecast"

    forecast_time: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    # When we fetched this forecast; NULL for rows migrated from the legacy forecast table.
    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    temp: Mapped[float]
    feels_like: Mapped[Optional[float]]
    humidity: Mapped[Optional[int]]
    wind_speed: Mapped[Optional[float]]
    visibility: Mapped[Optional[int]]
    weather_id: Mapped[int] = mapped_column(ForeignKey("weather.id"))
    weather: Mapped["Weather"] = Relationship()

    def __repr__(self):
        return f"WeatherForecast(forecast_time={self.forecast_time}, temp={self.temp})"


class Station(Base):
    __tablename__ = "station"

    station_id: Mapped[int] = mapped_column(primary_key=True)
    contract: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(60))
    longitude: Mapped[float] = mapped_column(type_=Double)
    latitude: Mapped[float] = mapped_column(type_=Double)
    bike_stands: Mapped[Optional[int]] = mapped_column(nullable=True)  # total docks

    def __repr__(self):
        return f"Station(id={self.station_id}, name={self.name})"


class StationStatus(Base):
    __tablename__ = "station_status"
    # One row per station per JCDecaux update — repeated polls are no-ops.
    __table_args__ = (
        UniqueConstraint("station_id", "update_time", name="uq_station_status_station_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    station_id = mapped_column(ForeignKey("station.station_id"))
    station: Mapped["Station"] = Relationship()
    update_time: Mapped[datetime] = mapped_column(DateTime)
    avail_bikes: Mapped[int]
    avail_bike_stands: Mapped[int]
    status: Mapped[str] = mapped_column(String(15))

    def __repr__(self):
        return f"StationStatus(id={self.id}, station_id={self.station_id}, avail_bikes={self.avail_bikes})"
