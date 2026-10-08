from datetime import datetime, timedelta, timezone

import requests
from flask import Blueprint, jsonify, current_app

from src.services.bikes_service import fetch_jcdecaux_stations
from src.db import get_all_stations, get_latest_availability, get_latest_station_status, get_station_history

bikes_bp = Blueprint('bikes', __name__)

# The ingestion DAG refreshes station_status every 5 minutes. Older than this
# means the pipeline is down, so fall back to calling JCDecaux directly.
FRESH_FOR = timedelta(minutes=15)


@bikes_bp.route("/api/bikes")
def api_bikes():
    """
    Current availability for every station.
    Served from the latest pipeline snapshot; calls JCDecaux live only if that
    snapshot is older than 15 minutes. This endpoint never writes to the database
    (the Airflow ingestion DAG is the only writer).
    ---
    tags:
      - Bikes (Live)
    responses:
      200:
        description: >
          Stations in JCDecaux format. `source` is "database" or "jcdecaux";
          `as_of` is the newest snapshot time (UTC); `stale` is true when the
          snapshot is old and JCDecaux was unreachable.
      502:
        description: No recent snapshot and JCDecaux unavailable
    """
    engine = current_app.extensions['engine']
    try:
        stations, as_of = get_latest_availability(engine)
    except Exception as e:
        current_app.logger.error(f"[/api/bikes] DB read failed: {e}", exc_info=True)
        stations, as_of = [], None

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    fresh = as_of is not None and now - as_of <= FRESH_FOR
    if fresh:
        return jsonify({"source": "database", "as_of": as_of.isoformat(), "stale": False,
                        "count": len(stations), "data": stations})

    current_app.logger.warning(f"[/api/bikes] snapshot stale (as_of={as_of}); calling JCDecaux")
    try:
        data = fetch_jcdecaux_stations()
        return jsonify({"source": "jcdecaux", "as_of": None, "stale": False,
                        "count": len(data), "data": data})
    except requests.RequestException as e:
        current_app.logger.error(f"[/api/bikes] JCDecaux request failed: {e}", exc_info=True)
        if stations:   # an old snapshot beats an empty map
            return jsonify({"source": "database", "as_of": as_of.isoformat(), "stale": True,
                            "count": len(stations), "data": stations})
        current_app.logger.exception("Request failed with 502")
        return jsonify({"source": "jcdecaux", "error": "Request failed"}), 502


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
        current_app.logger.error(f"[/api/db/stations] Unexpected error: {e}", exc_info=True)
        return jsonify({"source": "database", "error": "Server error"}), 500


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
        current_app.logger.error(f"[/api/db/stations/{station_id}/history] Unexpected error: {e}", exc_info=True)
        return jsonify({"source": "database", "error": "Server error"}), 500


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
        current_app.logger.error(f"[/api/db/stations/status] Unexpected error: {e}", exc_info=True)
        return jsonify({"source": "database", "error": "Server error"}), 500
