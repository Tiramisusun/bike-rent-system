from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db import Station, StationStatus, get_latest_weather
from src.ml.occupancy_model import predict
from src.services.weather_service import fetch_openweather_current


def _get_station_history(session, station_id: int) -> list[tuple]:
    """
    Recent (update_time, bikes, docks) for a station, newest first: enough to cover
    the last hour plus gaps, which is all the model looks back.
    """
    rows = session.execute(
        select(StationStatus.update_time, StationStatus.avail_bikes, StationStatus.avail_bike_stands)
        .where(StationStatus.station_id == station_id)
        .order_by(StationStatus.update_time.desc())
        .limit(60)
    ).all()
    return [tuple(r) for r in rows]

prediction_bp = Blueprint("prediction", __name__)


@prediction_bp.route("/api/predict", methods=["GET"])
def api_predict():
    """
    Predict available bikes for a station at a given datetime.
    ---
    tags:
      - Prediction
    parameters:
      - name: station_id
        in: query
        required: true
        type: integer
      - name: datetime
        in: query
        required: false
        type: string
        description: >
          ISO 8601 datetime (e.g. 2026-11-02T09:00); without an offset it is Dublin local
          time. Defaults to now. Predictions use the station's current state, so they are
          most accurate a few hours ahead; beyond 24 h they fall back to its usual level.
    responses:
      200:
        description: Predicted available bikes
      400:
        description: Missing or invalid parameters
      404:
        description: Station not found
      502:
        description: Weather data unavailable
      503:
        description: ML model not loaded
    """
    # 1. Parse station_id
    station_id_raw = request.args.get("station_id")
    if not station_id_raw:
        return jsonify({"error": "station_id is required"}), 400
    try:
        station_id = int(station_id_raw)
    except ValueError:
        return jsonify({"error": "station_id must be an integer"}), 400

    # 2. Parse datetime (default: now)
    dt_str = request.args.get("datetime")
    if dt_str:
        try:
            dt = datetime.fromisoformat(dt_str)
        except ValueError:
            return jsonify({"error": "Invalid datetime. Use ISO 8601 e.g. 2024-12-15T09:00"}), 400
    else:
        dt = datetime.now(timezone.utc)

    # 3. Look up station lat/lon from DB + fetch history
    engine = current_app.extensions["engine"]
    with Session(engine) as session:
        station = session.get(Station, station_id)
        if not station:
            return jsonify({"error": f"Station {station_id} not found"}), 404
        station_name = station.name
        history = _get_station_history(session, station_id)

    # 4. Get weather: DB first, fallback to OpenWeather API
    weather = get_latest_weather(engine)
    if weather:
        temp = weather["temp"]
        humidity = weather["humidity"]
        weather_source = "db"
    else:
        try:
            raw = fetch_openweather_current()
            temp = raw["main"]["temp"]
            humidity = raw["main"]["humidity"]
            weather_source = "openweather"
        except Exception as e:
            current_app.logger.error(f"[/api/predict] Weather fetch failed: {e}", exc_info=True)
            return jsonify({"error": "Weather data unavailable"}), 502

    # 5. Run prediction
    try:
        predicted_bikes = predict(station_id, dt, temp, humidity, history=history)
    except FileNotFoundError as e:
        current_app.logger.error(f"[/api/predict] Model file not found: {e}", exc_info=True)
        return jsonify({"error": "ML model not found. Run python -m ml.train_availability first."}), 503
    except Exception as e:
        current_app.logger.error(f"[/api/predict] Prediction failed: {e}", exc_info=True)
        return jsonify({"error": "Prediction failed"}), 500

    return jsonify({
        "station_id": station_id,
        "station_name": station_name,
        "predicted_bikes": predicted_bikes,
        "datetime": dt.isoformat(),
        "weather": {"temp": round(temp, 1), "humidity": humidity},
        "weather_source": weather_source,
    })


