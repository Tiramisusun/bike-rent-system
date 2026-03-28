from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.db import Rental, Station

rental_bp = Blueprint('rental', __name__)

FREE_MINUTES = 30
RATE_PER_30MIN = 0.50


def calculate_cost(duration_minutes: int) -> float:
    if duration_minutes <= FREE_MINUTES:
        return 0.0
    billable = duration_minutes - FREE_MINUTES
    periods = (billable + 29) // 30
    return round(periods * RATE_PER_30MIN, 2)


@rental_bp.route("/api/rental/start", methods=["POST"])
@jwt_required()
def start_rental():
    """
    Start a bike rental from a station.
    ---
    tags:
      - Rental
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            station_id:
              type: integer
    responses:
      201:
        description: Rental started
      400:
        description: Already has an active rental
    """
    user_id = int(get_jwt_identity())
    data = request.get_json()
    station_id = data.get("station_id")

    if not station_id:
        return jsonify({"error": "station_id is required"}), 400

    engine = current_app.extensions['engine']
    with Session(engine) as session:
        active = session.scalars(
            select(Rental).where(Rental.user_id == user_id, Rental.end_time == None)
        ).first()
        if active:
            return jsonify({"error": "You already have an active rental"}), 400

        station = session.get(Station, station_id)
        if not station:
            return jsonify({"error": "Station not found"}), 404

        rental = Rental(
            user_id=user_id,
            pickup_station_id=station_id,
            start_time=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(rental)
        session.commit()
        session.refresh(rental)

        return jsonify({
            "rental_id": rental.id,
            "pickup_station": station.name,
            "start_time": rental.start_time.isoformat(),
        }), 201


@rental_bp.route("/api/rental/end", methods=["POST"])
@jwt_required()
def end_rental():
    """
    End an active bike rental.
    ---
    tags:
      - Rental
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            station_id:
              type: integer
    responses:
      200:
        description: Rental ended with cost summary
      404:
        description: No active rental found
    """
    user_id = int(get_jwt_identity())
    data = request.get_json()
    dropoff_station_id = data.get("station_id")

    if not dropoff_station_id:
        return jsonify({"error": "station_id is required"}), 400

    engine = current_app.extensions['engine']
    with Session(engine) as session:
        rental = session.scalars(
            select(Rental).where(Rental.user_id == user_id, Rental.end_time == None)
        ).first()
        if not rental:
            return jsonify({"error": "No active rental found"}), 404

        station = session.get(Station, dropoff_station_id)
        if not station:
            return jsonify({"error": "Station not found"}), 404

        end_time = datetime.now(timezone.utc).replace(tzinfo=None)
        duration = int((end_time - rental.start_time).total_seconds() / 60)
        cost = calculate_cost(duration)

        rental.end_time = end_time
        rental.dropoff_station_id = dropoff_station_id
        rental.duration_minutes = duration
        rental.cost_eur = cost
        session.commit()

        pickup_station = session.get(Station, rental.pickup_station_id)

        return jsonify({
            "rental_id": rental.id,
            "pickup_station": pickup_station.name if pickup_station else str(rental.pickup_station_id),
            "dropoff_station": station.name,
            "start_time": rental.start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_minutes": duration,
            "cost_eur": cost,
        })


@rental_bp.route("/api/rental/history", methods=["GET"])
@jwt_required()
def rental_history():
    """
    Get rental history for the logged-in user.
    ---
    tags:
      - Rental
    responses:
      200:
        description: List of past rentals
    """
    user_id = int(get_jwt_identity())
    engine = current_app.extensions['engine']

    with Session(engine) as session:
        rentals = session.scalars(
            select(Rental).where(Rental.user_id == user_id).order_by(Rental.start_time.desc())
        ).all()

        result = []
        for r in rentals:
            pickup = session.get(Station, r.pickup_station_id)
            dropoff = session.get(Station, r.dropoff_station_id) if r.dropoff_station_id else None
            result.append({
                "rental_id": r.id,
                "pickup_station": pickup.name if pickup else str(r.pickup_station_id),
                "dropoff_station": dropoff.name if dropoff else None,
                "start_time": r.start_time.isoformat(),
                "end_time": r.end_time.isoformat() if r.end_time else None,
                "duration_minutes": r.duration_minutes,
                "cost_eur": r.cost_eur,
                "status": "active" if not r.end_time else "completed",
            })

        return jsonify({"count": len(result), "rentals": result})


@rental_bp.route("/api/rental/active", methods=["GET"])
@jwt_required()
def active_rental():
    """
    Get current active rental for the logged-in user.
    ---
    tags:
      - Rental
    responses:
      200:
        description: Active rental or null
    """
    user_id = int(get_jwt_identity())
    engine = current_app.extensions['engine']

    with Session(engine) as session:
        rental = session.scalars(
            select(Rental).where(Rental.user_id == user_id, Rental.end_time == None)
        ).first()

        if not rental:
            return jsonify({"active": None})

        pickup = session.get(Station, rental.pickup_station_id)
        return jsonify({
            "active": {
                "rental_id": rental.id,
                "pickup_station": pickup.name if pickup else str(rental.pickup_station_id),
                "start_time": rental.start_time.isoformat(),
            }
        })
