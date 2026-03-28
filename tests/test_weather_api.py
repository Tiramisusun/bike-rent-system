"""
Tests for weather service and /api/weather, /api/weather/forecast endpoints.
Run with:  pytest tests/test_weather_api.py -v

Strategy: mock requests.get so no real HTTP calls are made.
Fixture data comes from test_db.py.
"""
import pytest
from unittest.mock import patch, MagicMock
from tests.test_db import weather_data  # reuse existing fixture


# ── Service layer tests ───────────────────────────────────────────────────────

class TestFetchOpenweatherCurrent:

    def test_returns_dict_on_success(self, weather_data):
        """Service returns parsed JSON dict when API call succeeds."""
        from src.services.weather_service import fetch_openweather_current

        mock_resp = MagicMock()
        mock_resp.json.return_value = weather_data
        mock_resp.raise_for_status.return_value = None

        with patch("src.services.weather_service.requests.get", return_value=mock_resp):
            result = fetch_openweather_current()

        assert isinstance(result, dict)

    def test_raises_on_http_error(self):
        """Service raises HTTPError when API returns an error status."""
        import requests as req
        from src.services.weather_service import fetch_openweather_current

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req.HTTPError("401 Unauthorized")

        with patch("src.services.weather_service.requests.get", return_value=mock_resp):
            with pytest.raises(req.HTTPError):
                fetch_openweather_current()

    def test_raises_when_api_key_missing(self, monkeypatch):
        """Service raises ValueError if OPENWEATHER_API_KEY is not set."""
        from src.services.weather_service import fetch_openweather_current
        monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
        with pytest.raises(ValueError, match="OPENWEATHER_API_KEY"):
            fetch_openweather_current()


class TestFetchOpenweatherForecast:

    def test_returns_dict_on_success(self):
        """Forecast service returns parsed JSON dict on success."""
        from src.services.weather_service import fetch_openweather_forecast

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"list": [], "city": {"name": "Dublin"}}
        mock_resp.raise_for_status.return_value = None

        with patch("src.services.weather_service.requests.get", return_value=mock_resp):
            result = fetch_openweather_forecast()

        assert isinstance(result, dict)

    def test_raises_when_api_key_missing(self, monkeypatch):
        from src.services.weather_service import fetch_openweather_forecast
        monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
        with pytest.raises(ValueError, match="OPENWEATHER_API_KEY"):
            fetch_openweather_forecast()


# ── Response data format tests ────────────────────────────────────────────────

class TestWeatherDataFormat:

    def test_current_weather_has_required_fields(self, weather_data):
        """OpenWeather current response contains expected top-level keys."""
        assert "current" in weather_data
        current = weather_data["current"]
        for field in ("temp", "feels_like", "humidity", "wind_speed", "weather"):
            assert field in current, f"Missing field: {field}"

    def test_temperature_is_realistic(self, weather_data):
        """Temperature value is within a plausible range (Kelvin or Celsius)."""
        temp = weather_data["current"]["temp"]
        # Accepts both Kelvin (~293) and Celsius (20) scales
        assert -50 < temp < 400

    def test_humidity_is_percentage(self, weather_data):
        humidity = weather_data["current"]["humidity"]
        assert 0 <= humidity <= 100

    def test_weather_description_is_string(self, weather_data):
        weather_list = weather_data["current"]["weather"]
        assert isinstance(weather_list, list)
        assert len(weather_list) > 0
        assert isinstance(weather_list[0]["description"], str)

    def test_hourly_data_present(self, weather_data):
        assert "hourly" in weather_data
        assert isinstance(weather_data["hourly"], list)
        assert len(weather_data["hourly"]) > 0


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
    body = res.get_json()
    assert "source" in body or "temperature" in body or "weather" in body


def test_api_weather_upstream_error(client):
    """/api/weather returns error status when OpenWeather is unreachable."""
    import requests as req

    with patch("src.services.weather_service.requests.get",
               side_effect=req.ConnectionError("timeout")):
        res = client.get("/api/weather")

    assert res.status_code in (500, 502)


def test_api_weather_forecast_success(client):
    """/api/weather/forecast returns a list of forecast entries."""
    mock_payload = {
        "list": [
            {
                "dt": 1700000000,
                "main": {"temp": 12.5, "feels_like": 10.0, "humidity": 80},
                "weather": [{"description": "light rain", "icon": "10d"}],
                "wind": {"speed": 5.0},
            }
        ],
        "city": {"name": "Dublin"},
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_payload
    mock_resp.raise_for_status.return_value = None

    with patch("src.services.weather_service.requests.get", return_value=mock_resp):
        res = client.get("/api/weather/forecast")

    assert res.status_code == 200
