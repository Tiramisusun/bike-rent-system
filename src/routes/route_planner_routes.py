from flask import Blueprint, current_app, jsonify, request

from src.services.route_planner_service import RoutePlanningError, plan_route

route_planner_bp = Blueprint("route_planner", __name__)


def _float_param(key: str) -> float:
    value = request.args.get(key)
    if value is None:
        raise ValueError(f"Missing required query parameter: {key}")
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"Invalid value for '{key}': must be a number")


def _int_param(key: str, default: int) -> int:
    value = request.args.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Invalid value for '{key}': must be an integer")


@route_planner_bp.route("/api/plan")
def api_plan():
    """
    Plan a bike route between two coordinates.
    ---
    tags:
      - Route Planning
    parameters:
      - name: start_lat
        in: query
        required: true
        type: number
        description: Start latitude
      - name: start_lng
        in: query
        required: true
        type: number
        description: Start longitude
      - name: end_lat
        in: query
        required: true
        type: number
        description: Destination latitude
      - name: end_lng
        in: query
        required: true
        type: number
        description: Destination longitude
      - name: max_distance_m
        in: query
        required: false
        type: integer
        default: 1500
        description: Max walking distance to a station in metres
      - name: candidates
        in: query
        required: false
        type: integer
        default: 4
        description: Number of station candidates to consider per side
    responses:
      200:
        description: Optimal route plan (bike or walk-only)
      400:
        description: Missing or invalid parameters
      500:
        description: Unexpected server error
    """
    try:
        start_lat = _float_param("start_lat")
        start_lng = _float_param("start_lng")
        end_lat = _float_param("end_lat")
        end_lng = _float_param("end_lng")
        max_distance_m = _int_param("max_distance_m", 1500)
        candidates = _int_param("candidates", 4)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        engine = current_app.extensions["engine"]
        result = plan_route(
            engine=engine,
            start_lat=start_lat,
            start_lng=start_lng,
            end_lat=end_lat,
            end_lng=end_lng,
            max_station_distance_m=max_distance_m,
            candidates_per_side=candidates,
        )
    except RoutePlanningError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:
        current_app.logger.exception("Unexpected route planning failure")
        return jsonify({"error": f"Route planning failed: {exc}"}), 500

    return jsonify(result)
