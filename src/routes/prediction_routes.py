from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db import Station, StationStatus, get_latest_weather
from src.ml.occupancy_model import predict
from src.services.weather_service import fetch_openweather_current


def _get_station_history(session, station_id: int):
    """
    Return (recent_bikes, station_median) for a station.
    recent_bikes: list of avail_bikes ordered newest→oldest (up to 168 records).
    station_median: median avail_bikes across all stored records.
    """
    rows = session.scalars(
        select(StationStatus.avail_bikes)
        .where(StationStatus.station_id == station_id)
        .order_by(StationStatus.update_time.desc())
        .limit(168)
    ).all()
    recent_bikes = [r for r in rows]

    all_bikes = session.scalars(
        select(StationStatus.avail_bikes)
        .where(StationStatus.station_id == station_id)
    ).all()
    import statistics
    station_median = statistics.median(all_bikes) if all_bikes else (recent_bikes[0] if recent_bikes else 0)

    return recent_bikes, station_median

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
        description: ISO 8601 datetime (e.g. 2024-12-15T09:00). Defaults to now.
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
        lat = station.latitude
        lon = station.longitude
        station_name = station.name
        recent_bikes, station_median = _get_station_history(session, station_id)

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
            return jsonify({"error": "Weather data unavailable", "details": str(e)}), 502

    # 5. Run prediction
    try:
        predicted_bikes = predict(
            station_id, dt, lat, lon, temp, humidity,
            recent_bikes=recent_bikes, station_median=station_median,
        )
    except FileNotFoundError as e:
        return jsonify({"error": "ML model not found. Run the notebook first.", "details": str(e)}), 503
    except Exception as e:
        return jsonify({"error": "Prediction failed", "details": str(e)}), 500

    return jsonify({
        "station_id": station_id,
        "station_name": station_name,
        "predicted_bikes": predicted_bikes,
        "datetime": dt.isoformat(),
        "weather": {"temp": round(temp, 1), "humidity": humidity},
        "weather_source": weather_source,
    })


