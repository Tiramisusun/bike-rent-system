import requests
from flask import Blueprint, jsonify, current_app

from src.services.bikes_service import fetch_jcdecaux_stations
from src.db import db_from_request, get_all_stations, get_latest_station_status, get_station_history

bikes_bp = Blueprint('bikes', __name__)


@bikes_bp.route("/api/bikes")
def api_bikes():
    """
    Fetch live bike station data from JCDecaux and save to database.
    ---
    tags:
      - Bikes (Live)
    responses:
      200:
        description: List of all Dublin bike stations with real-time availability
      502:
        description: JCDecaux API unavailable
    """
    try:
        engine = current_app.extensions['engine']
        data = fetch_jcdecaux_stations()

        try:
            db_from_request(data, "bike-static", engine=engine)   # upsert stations first (satisfies FK)
            db_from_request(data, "bike-dynamic", engine=engine)   # then insert status records
        except Exception as e:
            current_app.logger.warning(f"bike insert failed: {e}")

        return jsonify({"source": "jcdecaux", "count": len(data), "data": data})
    except requests.RequestException as e:
        return jsonify({"source": "jcdecaux", "error": "Request failed", "details": str(e)}), 502
    except Exception as e:
        return jsonify({"source": "jcdecaux", "error": "Server error", "details": str(e)}), 500


@bikes_bp.route("/api/db/stations")
def api_db_stations():
    """
    Retrieve all bike stations from the database.
    ---
    tags:
      - Bikes (Database)
    responses:
      200:
        description: List of all stations stored in the database
    """
    try:
        engine = current_app.extensions['engine']
        data = get_all_stations(engine)
        return jsonify({"source": "database", "count": len(data), "data": data})
    except Exception as e:
        return jsonify({"source": "database", "error": "Server error", "details": str(e)}), 500


@bikes_bp.route("/api/db/stations/<int:station_id>/history")
def api_db_station_history(station_id):
    """
    Retrieve historical status records for a specific station.
    ---
    tags:
      - Bikes (Database)
    parameters:
      - name: station_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Historical availability records for the station
    """
    try:
        engine = current_app.extensions['engine']
        data = get_station_history(engine, station_id)
        return jsonify({"source": "database", "station_id": station_id, "count": len(data), "data": data})
    except Exception as e:
        return jsonify({"source": "database", "error": "Server error", "details": str(e)}), 500


@bikes_bp.route("/api/db/stations/status")
def api_db_station_status():
    """
    Retrieve historical bike station status records from the database.
    ---
    tags:
      - Bikes (Database)
    responses:
      200:
        description: List of station status records ordered by most recent first
    """
    try:
        engine = current_app.extensions['engine']
        data = get_latest_station_status(engine)
        return jsonify({"source": "database", "count": len(data), "data": data})
    except Exception as e:
        return jsonify({"source": "database", "error": "Server error", "details": str(e)}), 500
