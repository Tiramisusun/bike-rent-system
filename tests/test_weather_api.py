"""
Tests for weather service and /api/weather, /api/weather/forecast endpoints.
Run with:  pytest tests/test_weather_api.py -v

Strategy: mock requests.get so no real HTTP calls are made.
"""
import pytest
from unittest.mock import patch, MagicMock
from tests.test_db import weather_data  # reuse existing fixture


# ── Service layer tests ───────────────────────────────────────────────────────

def test_returns_dict_on_success(weather_data):
    """Service returns parsed JSON dict when API call succeeds."""
    from src.services.weather_service import fetch_openweather_current

    mock_resp = MagicMock()
    mock_resp.json.return_value = weather_data
    mock_resp.raise_for_status.return_value = None

    with patch("src.services.weather_service.requests.get", return_value=mock_resp):
        result = fetch_openweather_current()

    assert isinstance(result, dict)


def test_forecast_raises_when_api_key_missing(monkeypatch):
    """Forecast service raises ValueError if OPENWEATHER_API_KEY is not set."""
    from src.services.weather_service import fetch_openweather_forecast
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENWEATHER_API_KEY"):
        fetch_openweather_forecast()


# ── API endpoint tests ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from app import app as flask_app
    from src.db import init_db
    from sqlalchemy import create_engine

    flask_app.config["TESTING"] = True
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    flask_app.extensions["engine"] = engine

    with flask_app.test_client() as c:
        yield c


def test_api_weather_success(client, weather_data):
    """/api/weather returns weather data when OpenWeather call succeeds."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = weather_data
    mock_resp.raise_for_status.return_value = None

    with patch("src.services.weather_service.requests.get", return_value=mock_resp):
        res = client.get("/api/weather")

    assert res.status_code == 200
