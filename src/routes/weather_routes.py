import requests
from datetime import datetime, timedelta, timezone
from flask import Blueprint, jsonify, current_app

from src.services.weather_service import fetch_openweather_current, fetch_openweather_forecast
from src.db import get_current_weather, get_forecast_data, get_latest_weather

weather_bp = Blueprint('weather', __name__)

# Ingestion refreshes current weather every 5 min and the forecast hourly.
# Older than this means the pipeline is down, so fall back to OpenWeather.
WEATHER_FRESH_FOR = timedelta(minutes=60)
FORECAST_FRESH_FOR = timedelta(hours=4)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _forecast_item(entry: dict) -> dict:
    return {
        "dt": entry["dt"],
        "time": datetime.fromtimestamp(entry["dt"], tz=timezone.utc).strftime("%a %H:%M"),
        "temp": round(entry["main"]["temp"]),
        "feels_like": round(entry["main"]["feels_like"]),
        "humidity": entry["main"]["humidity"],
        "description": entry["weather"][0]["description"],
        "icon": entry["weather"][0]["icon"],
        "wind_speed": entry["wind"]["speed"],
    }


@weather_bp.route("/api/weather")
def api_weather():
    """
    Current weather for Dublin.
    Served from the latest pipeline observation; calls OpenWeather only if it is
    more than 60 minutes old. Never writes to the database.
    ---
    tags:
      - Weather (Live)
    responses:
      200:
        description: OpenWeather-style payload; `source` is "database" or "openweather", `stale` true if old
      502:
        description: No recent observation and OpenWeather unavailable
    """
    engine = current_app.extensions['engine']
    try:
        payload, observed_at = get_current_weather(engine)
    except Exception:
        current_app.logger.exception("[/api/weather] DB read failed")
        payload, observed_at = None, None

    if observed_at is not None and _now() - observed_at <= WEATHER_FRESH_FOR:
        return jsonify({"source": "database", "as_of": observed_at.isoformat(), "stale": False, "data": payload})

    try:
        return jsonify({"source": "openweather", "as_of": None, "stale": False,
                        "data": fetch_openweather_current()})
    except requests.RequestException:
        current_app.logger.exception("[/api/weather] OpenWeather request failed")
        if payload:
            return jsonify({"source": "database", "as_of": observed_at.isoformat(), "stale": True, "data": payload})
        return jsonify({"source": "openweather", "error": "Weather unavailable"}), 502


@weather_bp.route("/api/weather/forecast")
def api_weather_forecast():
    """
    5-day forecast for Dublin (every 3 hours).
    Served from the hourly pipeline load; calls OpenWeather only if the newest
    forecast is more than 4 hours old. Never writes to the database.
    ---
    tags:
      - Weather (Live)
    responses:
      200:
        description: Forecast entries; `source` is "database" or "openweather"
      502:
        description: No recent forecast and OpenWeather unavailable
    """
    engine = current_app.extensions['engine']
    try:
        items, fetched_at = get_forecast_data(engine)
    except Exception:
        current_app.logger.exception("[/api/weather/forecast] DB read failed")
        items, fetched_at = [], None

    if items and fetched_at is not None and _now() - fetched_at <= FORECAST_FRESH_FOR:
        return jsonify({"source": "database", "as_of": fetched_at.isoformat(), "stale": False,
                        "count": len(items), "data": items})

    try:
        live = [_forecast_item(e) for e in fetch_openweather_forecast().get("list", [])]
        return jsonify({"source": "openweather", "as_of": None, "stale": False, "count": len(live), "data": live})
    except requests.RequestException:
        current_app.logger.exception("[/api/weather/forecast] OpenWeather request failed")
        if items:
            return jsonify({"source": "database", "as_of": fetched_at.isoformat() if fetched_at else None,
                            "stale": True, "count": len(items), "data": items})
        return jsonify({"source": "openweather", "error": "Forecast unavailable"}), 502


@weather_bp.route("/api/db/weather")
def api_db_weather():
    """
    Retrieve the most recent weather report from the database.
    ---
    tags:
      - Weather (Database)
    responses:
      200:
        description: Latest weather report stored in the database
      404:
        description: No weather data found in database
    """
    try:
        engine = current_app.extensions['engine']
        data = get_latest_weather(engine)
        if not data:
            return jsonify({"source": "database", "error": "No weather data found"}), 404
        return jsonify({"source": "database", "data": data})
    except Exception as e:
        current_app.logger.error(f"[/api/db/weather] Unexpected error: {e}", exc_info=True)
        return jsonify({"source": "database", "error": "Server error"}), 500
