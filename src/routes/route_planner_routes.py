from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request

from src.services.route_planner_service import (
    RoutePlanningError, plan_route, get_candidates, plan_route_simple,
)

route_planner_bp = Blueprint("route_planner", __name__)


def _float_param(key: str) -> float:
    value = request.args.get(key)
    if value is None:
        raise ValueError(f"Missing required query parameter: {key}")
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"Invalid value for '{key}': must be a number")


def _int_param(key: str, default):
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
        current_app.logger.warning(f"[/api/plan] Invalid params: {exc}")
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
        except Exception as exc:
            current_app.logger.warning(f"[/api/plan] Invalid waypoints '{waypoints_raw}': {exc}")
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
        current_app.logger.error(f"[/api/plan] RoutePlanningError: {exc}", exc_info=True)
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:
        current_app.logger.exception(f"[/api/plan] Unexpected route planning failure: {exc}")
        return jsonify({"error": f"Route planning failed: {exc}"}), 500


@route_planner_bp.route("/api/plan/candidates")
def api_plan_candidates():
    """
    Step 1: return ML-ranked pickup and dropoff candidate stations.
    GET /api/plan/candidates?start_lat=&start_lng=&end_lat=&end_lng=&departure_time=ISO8601
    """
    try:
        start_lat = _float_param("start_lat")
        start_lng = _float_param("start_lng")
        end_lat   = _float_param("end_lat")
        end_lng   = _float_param("end_lng")
    except ValueError as exc:
        current_app.logger.warning(f"[/api/plan/candidates] Invalid params: {exc}")
        return jsonify({"error": str(exc)}), 400

    dt_raw = request.args.get("departure_time", "").strip()
    if dt_raw:
        try:
            departure_dt = datetime.fromisoformat(dt_raw).replace(tzinfo=timezone.utc)
        except ValueError as exc:
            current_app.logger.warning(f"[/api/plan/candidates] Invalid departure_time '{dt_raw}': {exc}")
            return jsonify({"error": "Invalid departure_time format. Use ISO 8601."}), 400
    else:
        departure_dt = datetime.now(timezone.utc)

    try:
        engine = current_app.extensions["engine"]
        result = get_candidates(
            engine=engine,
            start_lat=start_lat, start_lng=start_lng,
            end_lat=end_lat,     end_lng=end_lng,
            departure_dt=departure_dt,
        )
        return jsonify(result)
    except Exception as exc:
        current_app.logger.exception(f"[/api/plan/candidates] get_candidates failed: {exc}")
        return jsonify({"error": str(exc)}), 500


@route_planner_bp.route("/api/plan/route")
def api_plan_route():
    """
    Step 2: compute the three-leg route for user-selected stations.
    GET /api/plan/route?pickup_id=&dropoff_id=&start_lat=&start_lng=&end_lat=&end_lng=&preference=recommended
    """
    try:
        start_lat  = _float_param("start_lat")
        start_lng  = _float_param("start_lng")
        end_lat    = _float_param("end_lat")
        end_lng    = _float_param("end_lng")
        pickup_id  = _int_param("pickup_id",  None)
        dropoff_id = _int_param("dropoff_id", None)
    except ValueError as exc:
        current_app.logger.warning(f"[/api/plan/route] Invalid params: {exc}")
        return jsonify({"error": str(exc)}), 400

    if pickup_id is None or dropoff_id is None:
        return jsonify({"error": "pickup_id and dropoff_id are required"}), 400

    preference = request.args.get("preference", "recommended")
    if preference not in ("recommended", "fastest", "shortest"):
        return jsonify({"error": "preference must be recommended, fastest, or shortest"}), 400

    try:
        engine = current_app.extensions["engine"]
        result = plan_route_simple(
            engine=engine,
            pickup_id=pickup_id,   dropoff_id=dropoff_id,
            start_lat=start_lat,   start_lng=start_lng,
            end_lat=end_lat,       end_lng=end_lng,
            preference=preference,
        )
        return jsonify(result)
    except RoutePlanningError as exc:
        current_app.logger.error(f"[/api/plan/route] RoutePlanningError: {exc}", exc_info=True)
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        current_app.logger.exception(f"[/api/plan/route] plan_route_simple failed: {exc}")
        return jsonify({"error": str(exc)}), 500
