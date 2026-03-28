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
    Plan a bike route between two coordinates, with optional waypoints.
    ---
    tags:
      - Route Planning
    parameters:
      - name: start_lat
        in: query
        required: true
        type: number
      - name: start_lng
        in: query
        required: true
        type: number
      - name: end_lat
        in: query
        required: true
        type: number
      - name: end_lng
        in: query
        required: true
        type: number
      - name: waypoints
        in: query
        required: false
        type: string
        description: Semicolon-separated waypoints as "lat,lng;lat,lng"
      - name: max_distance_m
        in: query
        required: false
        type: integer
        default: 1500
      - name: candidates
        in: query
        required: false
        type: integer
        default: 4
    responses:
      200:
        description: Route plan. Contains 'segments' array if waypoints were given, else a single plan.
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

    # Parse optional waypoints: "lat1,lng1;lat2,lng2"
    waypoints_raw = request.args.get("waypoints", "").strip()
    waypoints = []
    if waypoints_raw:
        try:
            for pair in waypoints_raw.split(";"):
                pair = pair.strip()
                if pair:
                    lat_s, lng_s = pair.split(",")
                    waypoints.append((float(lat_s), float(lng_s)))
        except Exception:
            return jsonify({"error": "Invalid waypoints format. Use 'lat,lng;lat,lng'"}), 400

    try:
        engine = current_app.extensions["engine"]
        result = plan_route(
            engine=engine,
            start_lat=start_lat, start_lng=start_lng,
            end_lat=end_lat, end_lng=end_lng,
            waypoints=waypoints if waypoints else None,
            max_station_distance_m=max_distance_m,
            candidates_per_side=candidates,
        )
        return jsonify(result)

    except RoutePlanningError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:
        current_app.logger.exception("Unexpected route planning failure")
        return jsonify({"error": f"Route planning failed: {exc}"}), 500
