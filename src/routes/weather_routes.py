import requests
from flask import Blueprint, jsonify, current_app

from src.services.weather_service import fetch_openweather_current
from src.db import db_from_request, get_latest_weather

weather_bp = Blueprint('weather', __name__)


@weather_bp.route("/api/weather")
def api_weather():
    """
    Fetch current weather data from OpenWeather and save to database.
    ---
    tags:
      - Weather (Live)
    responses:
      200:
        description: Current weather conditions for Dublin
      502:
        description: OpenWeather API unavailable
    """
    try:
        engine = current_app.extensions['engine']
        data = fetch_openweather_current()

        try:
            db_from_request(data, "weather", engine=engine)
        except Exception as e:
            current_app.logger.error(f"weather insert failed: {e}", exc_info=True)
            return jsonify({"source": "openweather", "data": data, "db_warning": str(e)}), 200

        return jsonify({"source": "openweather", "data": data})
    except requests.RequestException as e:
        return jsonify({"source": "openweather", "error": "Request failed", "details": str(e)}), 502
    except Exception as e:
        return jsonify({"source": "openweather", "error": "Server error", "details": str(e)}), 500


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
        return jsonify({"source": "database", "error": "Server error", "details": str(e)}), 500
