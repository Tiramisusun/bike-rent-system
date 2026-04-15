"""SQLAlchemy ORM models — one class per database table."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Double, ForeignKey, String
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



