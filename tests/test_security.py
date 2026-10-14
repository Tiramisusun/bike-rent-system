"""Security behaviour required before exposing the app publicly."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests as req
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from src.db import Weather, WeatherForecast, WeatherReport, init_db


@pytest.fixture
def app_with_db():
    """Fresh in-memory DB per test, swapped into the app and restored afterwards."""
    from app import app as flask_app
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    original = flask_app.extensions["engine"]
    flask_app.extensions["engine"] = engine
    with flask_app.test_client() as c:
        yield flask_app, c, engine
    flask_app.extensions["engine"] = original


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── 1. JWT secret ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value", [None, "", "dublin-bikes-secret-key"])
def test_missing_or_short_jwt_secret_refuses_to_start(monkeypatch, value):
    from app import jwt_secret
    if value is None:
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    else:
        monkeypatch.setenv("JWT_SECRET_KEY", value)
    with pytest.raises(RuntimeError):
        jwt_secret()


def test_long_jwt_secret_is_accepted(monkeypatch):
    from app import jwt_secret
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 64)
    assert jwt_secret() == "x" * 64


# ── 2. Debugger off ───────────────────────────────────────────────────────────

def test_app_does_not_run_in_debug_mode():
    from app import app as flask_app
    assert flask_app.debug is False


# ── 6a. Rate limiting ─────────────────────────────────────────────────────────

@pytest.fixture
def limits_on():
    from src.extensions import limiter
    was = limiter.enabled
    limiter.enabled = True
    limiter.reset()
    yield
    limiter.reset()
    limiter.enabled = was


def test_login_is_rate_limited(app_with_db, limits_on):
    _, client, _ = app_with_db
    body = {"email": "nobody@example.com", "password": "wrong"}
    codes = [client.post("/api/auth/login", json=body).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429
    assert client.post("/api/auth/login", json=body).get_json() == {"error": "Too many requests, please slow down"}


def test_register_is_rate_limited(app_with_db, limits_on):
    _, client, _ = app_with_db
    codes = [
        client.post("/api/auth/register",
                    json={"email": f"u{i}@example.com", "password": "pw123456", "name": f"U{i}"}).status_code
        for i in range(6)
    ]
    assert codes[:5] == [201] * 5
    assert codes[5] == 429


# ── 6b. Weather served from the pipeline, never written by page loads ────────

def _seed_weather(engine, observed_age, forecast_fetched_age=None):
    with Session(engine) as s:
        s.add(Weather(id=500, main="Rain", description="light rain", icon="10d"))
        s.add(WeatherReport(update_time=_now() - observed_age, temp=9.5, feels_like=7.0,
                            visibility=10000, wind_speed=6.2, humidity=88, weather_id=500))
        if forecast_fetched_age is not None:
            for h in (3, 6):
                s.add(WeatherForecast(forecast_time=(_now() + timedelta(hours=h)).replace(microsecond=0),
                                      fetched_at=_now() - forecast_fetched_age, temp=10.4, feels_like=8.1,
                                      humidity=80, wind_speed=5.0, visibility=10000, weather_id=500))
        s.commit()


def _count(engine, model):
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(model))


def test_weather_fresh_observation_served_without_calling_openweather(app_with_db):
    _, client, engine = app_with_db
    _seed_weather(engine, observed_age=timedelta(minutes=10))
    with patch("src.services.weather_service.requests.get") as live:
        body = client.get("/api/weather").get_json()
    live.assert_not_called()
    assert body["source"] == "database" and body["stale"] is False
    assert body["data"]["main"]["temp"] == 9.5
    assert body["data"]["weather"][0]["description"] == "light rain"


def test_weather_stale_falls_back_to_openweather_without_writing(app_with_db, weather_data):
    _, client, engine = app_with_db
    _seed_weather(engine, observed_age=timedelta(hours=3))
    resp = MagicMock(); resp.json.return_value = weather_data; resp.raise_for_status.return_value = None
    with patch("src.services.weather_service.requests.get", return_value=resp):
        body = client.get("/api/weather").get_json()
    assert body["source"] == "openweather"
    assert _count(engine, WeatherReport) == 1


def test_weather_stale_and_openweather_down_serves_stale_data(app_with_db):
    _, client, engine = app_with_db
    _seed_weather(engine, observed_age=timedelta(hours=3))
    with patch("src.services.weather_service.requests.get", side_effect=req.ConnectionError("down")):
        res = client.get("/api/weather")
    assert res.status_code == 200 and res.get_json()["stale"] is True


def test_forecast_fresh_served_from_database_with_frontend_fields(app_with_db):
    _, client, engine = app_with_db
    _seed_weather(engine, observed_age=timedelta(minutes=10), forecast_fetched_age=timedelta(minutes=30))
    with patch("src.services.weather_service.requests.get") as live:
        body = client.get("/api/weather/forecast").get_json()
    live.assert_not_called()
    assert body["source"] == "database" and body["count"] == 2
    assert {"dt", "time", "temp", "humidity", "description", "icon", "wind_speed"} <= set(body["data"][0])


def test_forecast_stale_falls_back_to_openweather_without_writing(app_with_db):
    _, client, engine = app_with_db
    _seed_weather(engine, observed_age=timedelta(minutes=10), forecast_fetched_age=timedelta(hours=6))
    live = {"list": [{"dt": 1775865600, "main": {"temp": 11.2, "feels_like": 10.0, "humidity": 70},
                      "weather": [{"id": 800, "main": "Clear", "description": "clear sky", "icon": "01d"}],
                      "wind": {"speed": 3.0}}]}
    resp = MagicMock(); resp.json.return_value = live; resp.raise_for_status.return_value = None
    with patch("src.services.weather_service.requests.get", return_value=resp):
        body = client.get("/api/weather/forecast").get_json()
    assert body["source"] == "openweather" and body["data"][0]["description"] == "clear sky"
    assert _count(engine, WeatherForecast) == 2


# ── 7. Server errors don't leak internals ────────────────────────────────────

def test_server_error_hides_exception_details(app_with_db):
    _, client, _ = app_with_db
    secret = "mysql+pymysql://root:hunter2@db/bike_app is unreachable"
    with patch("src.routes.bikes_routes.get_all_stations", side_effect=Exception(secret)):
        res = client.get("/api/db/stations")
    assert res.status_code == 500
    assert "hunter2" not in res.get_data(as_text=True)
    assert "details" not in res.get_json()


@pytest.fixture
def weather_data():
    return {
        "dt": 1775865600, "name": "Dublin",
        "weather": [{"id": 800, "main": "Clear", "description": "clear sky", "icon": "01d"}],
        "main": {"temp": 12.0, "feels_like": 11.0, "humidity": 70}, "wind": {"speed": 3.0}, "visibility": 10000,
    }
