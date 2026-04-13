import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from sqlalchemy import and_, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.db import Station, StationStatus, Weather, WeatherReport, get_latest_weather
from src.ml.occupancy_model import predict as ml_predict

OSRM_BASE = "https://router.project-osrm.org/route/v1"
ORS_BASE  = "https://api.openrouteservice.org/v2/directions"
DEFAULT_MAX_STATION_DISTANCE_M = 1500
DEFAULT_CANDIDATES = 4

WALKING_SPEED_MS  = 1.2   # 4.3 km/h — used only as straight-line fallback
# OSRM foot-profile duration is multiplied by this factor to account for
# pedestrian crossings, traffic lights, and realistic urban pace.
WALKING_TIME_FACTOR = 1.2


def _force_bike() -> bool:
    """
    Read FORCE_BIKE_IF_AVAILABLE from .env / environment.

    True (default)  → always recommend biking when viable stations exist,
                       skipping the travel-time comparison against walking.
    False           → recommend biking only when it is genuinely faster than
                       walking the whole way.

    Keep True while validating route timing; switch to False for production.
    """
    return os.getenv("FORCE_BIKE_IF_AVAILABLE", "true").lower() not in ("false", "0", "no")

logger = logging.getLogger(__name__)


class RoutePlanningError(RuntimeError):
    pass


@dataclass
class _StationCandidate:
    station_id: int
    name: str
    lat: float
    lng: float
    distance_m: float
    avail_bikes: int
    avail_docks: int
    status: str


@dataclass
class _Leg:
    seconds: int
    # [[lat, lng], ...] — always populated; falls back to a 2-point straight line
    coords: list[list[float]] = field(default_factory=list)


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def _estimated_seconds(lat1: float, lng1: float, lat2: float, lng2: float, mode: str) -> int:
    # Haversine straight-line distance × road factor for a rough city detour correction
    straight = _haversine(lat1, lng1, lat2, lng2)
    # Dublin: canals + Liffey river mean walking detours are typically 1.4–1.5×
    road_distance = straight * (1.4 if mode == "walking" else 1.2)
    speed = WALKING_SPEED_MS if mode == "walking" else 4.5
    if mode == "walking":
        return max(60, int(road_distance / speed * WALKING_TIME_FACTOR))
    return max(60, int(road_distance / speed))


def _osrm_leg(
    lat1: float, lng1: float,
    lat2: float, lng2: float,
    mode: str,
    cache: dict,
) -> _Leg:
    """Single-segment OSRM leg (2 points). Cached."""
    return _osrm_multi_leg([(lat1, lng1), (lat2, lng2)], mode, cache)


def _osrm_multi_leg(
    points: list[tuple[float, float]],
    mode: str,
    cache: dict,
) -> _Leg:
    """
    Fetch a routed leg from OSRM through an arbitrary number of waypoints.

    points is a list of (lat, lng) tuples.
    Returns a _Leg with real route duration and [[lat, lng], ...] coords for Leaflet.
    Falls back to haversine straight-line on any failure.
    """
    key = (tuple((round(p[0], 6), round(p[1], 6)) for p in points), mode)
    if key in cache:
        return cache[key]

    profile = "foot" if mode == "walking" else "cycling"
    # OSRM expects lng,lat order
    coords_str = ";".join(f"{p[1]},{p[0]}" for p in points)
    url = f"{OSRM_BASE}/{profile}/{coords_str}"

    try:
        resp = requests.get(
            url,
            params={"overview": "full", "geometries": "geojson"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != "Ok" or not data.get("routes"):
            raise RuntimeError(f"OSRM returned code={data.get('code')}")

        route = data["routes"][0]
        # OSRM GeoJSON coords are [lng, lat] — swap to [lat, lng] for Leaflet
        coords = [[c[1], c[0]] for c in route["geometry"]["coordinates"]]

        if mode == "walking":
            # Use OSRM's own duration (based on real road network) with a
            # urban-pedestrian correction factor for crossings and real pace.
            seconds = max(60, int(route["duration"] * WALKING_TIME_FACTOR))
        else:
            seconds = int(route["duration"])

        leg = _Leg(seconds=seconds, coords=coords)

    except Exception as exc:
        logger.warning("OSRM %s routing failed (%s) — using straight-line fallback", mode, exc)
        # Fallback: straight line through all points, sum of haversine distances
        total_seconds = 0
        for i in range(len(points) - 1):
            total_seconds += _estimated_seconds(points[i][0], points[i][1], points[i+1][0], points[i+1][1], mode)
        leg = _Leg(
            seconds=max(60, total_seconds),
            coords=[[p[0], p[1]] for p in points],
        )

    cache[key] = leg
    return leg


def _latest_status(session: Session) -> dict[int, dict]:
    subq = (
        select(
            StationStatus.station_id.label("sid"),
            func.max(StationStatus.update_time).label("t"),
        )
        .group_by(StationStatus.station_id)
        .subquery()
    )
    rows = session.execute(
        select(
            StationStatus.station_id,
            StationStatus.avail_bikes,
            StationStatus.avail_bike_stands,
            StationStatus.status,
        ).join(subq, and_(
            StationStatus.station_id == subq.c.sid,
            StationStatus.update_time == subq.c.t,
        ))
    )
    result: dict[int, dict] = {}
    for row in rows:
        sid = int(row.station_id)
        if sid not in result:
            result[sid] = {
                "avail_bikes": int(row.avail_bikes or 0),
                "avail_docks": int(row.avail_bike_stands or 0),
                "status": str(row.status or ""),
            }
    return result


def _nearest_candidates(
    session: Session,
    origin_lat: float,
    origin_lng: float,
    max_distance_m: int,
    limit: int,
) -> list[_StationCandidate]:
    statuses = _latest_status(session)
    candidates: list[_StationCandidate] = []

    for station in session.scalars(select(Station)).all():
        if station.latitude is None or station.longitude is None:
            continue
        status = statuses.get(station.station_id)
        if not status:
            continue
        dist = _haversine(origin_lat, origin_lng, station.latitude, station.longitude)
        if dist > max_distance_m:
            continue
        candidates.append(_StationCandidate(
            station_id=station.station_id,
            name=station.name,
            lat=float(station.latitude),
            lng=float(station.longitude),
            distance_m=dist,
            avail_bikes=status["avail_bikes"],
            avail_docks=status["avail_docks"],
            status=status["status"],
        ))

    candidates.sort(key=lambda c: c.distance_m)
    return candidates[:limit]


def _mins(seconds: int) -> float:
    return round(seconds / 60.0, 2)


def _availability_penalty(start: _StationCandidate, end: _StationCandidate) -> float:
    penalty = 0.0
    if start.avail_bikes <= 1:
        penalty += 6.0
    elif start.avail_bikes <= 3:
        penalty += 2.5
    if end.avail_docks <= 1:
        penalty += 6.0
    elif end.avail_docks <= 3:
        penalty += 2.5
    return penalty


def _weather_penalty(session: Session) -> tuple[float, dict]:
    row = session.execute(
        select(WeatherReport, Weather)
        .join(Weather, WeatherReport.weather_id == Weather.id, isouter=True)
        .order_by(WeatherReport.update_time.desc())
        .limit(1)
    ).first()

    if not row:
        return 0.0, {"reason": "no_weather_data"}

    report, weather = row
    penalty = 0.0
    main = (weather.main or "").lower() if weather else ""
    desc = (weather.description or "").lower() if weather else ""

    if "rain" in main or "rain" in desc:
        penalty += 8.0
    if report.wind_speed >= 10.0:
        penalty += 10.0
    elif report.wind_speed >= 8.0:
        penalty += 6.0
    if report.feels_like <= 0.0:
        penalty += 4.0
    elif report.feels_like <= 5.0:
        penalty += 2.0

    return penalty, {
        "condition": desc or main,
        "wind_speed_ms": report.wind_speed,
        "feels_like_c": report.feels_like,
    }


def _night_penalty() -> float:
    hour = datetime.now(timezone.utc).hour
    return 4.0 if hour >= 22 or hour < 6 else 0.0


def _walk_penalty(walk1_min: float, walk2_min: float, bike_min: float) -> float:
    total_walk = walk1_min + walk2_min
    penalty = 0.0
    if total_walk > 15:
        penalty += min(10.0, (total_walk - 15.0) * 0.5)
    if total_walk > bike_min:
        penalty += min(8.0, (total_walk - bike_min) * 0.5)
    return penalty


def _ors_cycling_leg(
    lat1: float, lng1: float,
    lat2: float, lng2: float,
    preference: str,
    cache: dict,
) -> _Leg:
    """
    Fetch a cycling leg from OpenRouteService with the given preference.
    Falls back to OSRM if ORS_API_KEY is not set or the request fails.
    preference: 'recommended' | 'fastest' | 'shortest'
    """
    api_key = os.getenv("ORS_API_KEY")
    if not api_key:
        return _osrm_leg(lat1, lng1, lat2, lng2, "cycling", cache)

    key = (round(lat1, 6), round(lng1, 6), round(lat2, 6), round(lng2, 6), preference)
    if key in cache:
        return cache[key]

    try:
        resp = requests.get(
            f"{ORS_BASE}/cycling-regular",
            params={
                "api_key": api_key,
                "start": f"{lng1},{lat1}",
                "end": f"{lng2},{lat2}",
                "preference": preference,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        feature = data["features"][0]
        coords = [[c[1], c[0]] for c in feature["geometry"]["coordinates"]]
        seconds = int(feature["properties"]["segments"][0]["duration"])
        leg = _Leg(seconds=seconds, coords=coords)
    except Exception as exc:
        logger.warning("ORS cycling failed (%s) — falling back to OSRM", exc)
        leg = _osrm_leg(lat1, lng1, lat2, lng2, "cycling", cache)

    cache[key] = leg
    return leg


def _station_dict(s: _StationCandidate) -> dict:
    return {
        "station_id": s.station_id,
        "name": s.name,
        "lat": s.lat,
        "lng": s.lng,
        "distance_m": round(s.distance_m, 1),
        "avail_bikes": s.avail_bikes,
        "avail_docks": s.avail_docks,
        "status": s.status,
    }


def plan_route(
    *,
    engine: Engine,
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    waypoints: list[tuple[float, float]] | None = None,
    max_station_distance_m: int = DEFAULT_MAX_STATION_DISTANCE_M,
    candidates_per_side: int = DEFAULT_CANDIDATES,
) -> dict[str, Any]:
    # Shared cache so each unique (A→B, mode) pair is fetched from OSRM only once,
    # even when the same leg appears in both the scoring loop and the winner output.
    leg_cache: dict = {}

    def leg(lat1, lng1, lat2, lng2, mode):
        return _osrm_leg(lat1, lng1, lat2, lng2, mode, leg_cache)

    with Session(engine) as session:
        start_candidates = _nearest_candidates(session, start_lat, start_lng, max_station_distance_m, candidates_per_side)
        end_candidates = _nearest_candidates(session, end_lat, end_lng, max_station_distance_m, candidates_per_side)

        direct_walk = leg(start_lat, start_lng, end_lat, end_lng, "walking")
        direct_walk_min = _mins(direct_walk.seconds)

        viable_start = [s for s in start_candidates if s.avail_bikes >= 1 and s.status.upper() == "OPEN"]
        viable_end = [s for s in end_candidates if s.avail_docks >= 1 and s.status.upper() == "OPEN"]

        if not viable_start or not viable_end:
            return {
                "mode": "walk_only",
                "reason": "No bike stations with live availability found near start or destination.",
                "walk_minutes": direct_walk_min,
                "walk_coords": direct_walk.coords,
                "start_candidates": [_station_dict(s) for s in start_candidates],
                "end_candidates": [_station_dict(s) for s in end_candidates],
            }

        weather_penalty, weather_meta = _weather_penalty(session)
        night_penalty = _night_penalty()

        # Pre-fetch walk legs for all viable stations (results go into leg_cache)
        walk_to_pickup = {
            s.station_id: leg(start_lat, start_lng, s.lat, s.lng, "walking")
            for s in viable_start
        }
        walk_to_dest = {
            s.station_id: leg(s.lat, s.lng, end_lat, end_lng, "walking")
            for s in viable_end
        }

        # Build the intermediate waypoint coords for the cycling leg
        via_points: list[tuple[float, float]] = [(wp[0], wp[1]) for wp in (waypoints or [])]

        options: list[dict] = []
        for pickup in viable_start:
            for dropoff in viable_end:
                # Cycling leg: pickup → [waypoints] → dropoff
                bike_points = [(pickup.lat, pickup.lng)] + via_points + [(dropoff.lat, dropoff.lng)]
                bike_leg = _osrm_multi_leg(bike_points, "cycling", leg_cache)

                walk1_min = _mins(walk_to_pickup[pickup.station_id].seconds)
                bike_min = _mins(bike_leg.seconds)
                walk2_min = _mins(walk_to_dest[dropoff.station_id].seconds)
                travel_min = round(walk1_min + bike_min + walk2_min, 2)

                avail_pen = _availability_penalty(pickup, dropoff)
                walk_pen = _walk_penalty(walk1_min, walk2_min, bike_min)
                total_pen = round(avail_pen + weather_penalty + night_penalty + walk_pen, 2)
                score = round(travel_min + total_pen, 2)

                options.append({
                    "pickup": _station_dict(pickup),
                    "dropoff": _station_dict(dropoff),
                    "times_minutes": {
                        "walk_to_pickup": walk1_min,
                        "bike": bike_min,
                        "walk_to_destination": walk2_min,
                        "total_travel": travel_min,
                    },
                    "penalties": {
                        "availability": avail_pen,
                        "weather": weather_penalty,
                        "night": night_penalty,
                        "excess_walking": walk_pen,
                        "total": total_pen,
                    },
                    "score": score,
                })

        options.sort(key=lambda o: o["score"])
        best = options[0]
        best_travel_min = best["times_minutes"]["total_travel"]

        # Compare raw travel times only — penalties rank bike options against each other
        # but shouldn't penalise biking vs walking (weather is bad for walkers too).
        # Set FORCE_BIKE_IF_AVAILABLE=false in .env to enable this check.
        if not _force_bike() and best_travel_min >= direct_walk_min:
            return {
                "mode": "walk_only",
                "reason": (
                    f"Biking takes {best_travel_min} min (walk + ride + walk) "
                    f"vs {direct_walk_min} min walking directly — no time saved."
                ),
                "walk_minutes": direct_walk_min,
                "bike_minutes": best_travel_min,
                "walk_coords": direct_walk.coords,
                "start_candidates": [_station_dict(s) for s in start_candidates],
                "end_candidates": [_station_dict(s) for s in end_candidates],
            }

        # Winner legs are already in leg_cache — no second OSRM round-trip needed
        pickup = best["pickup"]
        dropoff = best["dropoff"]
        walk1 = leg(start_lat, start_lng, pickup["lat"], pickup["lng"], "walking")
        bike_points = [(pickup["lat"], pickup["lng"])] + via_points + [(dropoff["lat"], dropoff["lng"])]
        bike  = _osrm_multi_leg(bike_points, "cycling", leg_cache)
        walk2 = leg(dropoff["lat"], dropoff["lng"], end_lat, end_lng, "walking")

        # ── ML prediction: predicted stands at dropoff on arrival ──────────
        arrival_dt = datetime.now(timezone.utc) + timedelta(
            minutes=best["times_minutes"]["total_travel"]
        )
        predicted_stands = None
        try:
            weather = get_latest_weather(engine)
            temp     = weather["temp"]     if weather else 12.0
            humidity = weather["humidity"] if weather else 75.0
            dropoff_candidate = next(
                s for s in end_candidates if s.station_id == dropoff["station_id"]
            )
            capacity = dropoff_candidate.avail_bikes + dropoff_candidate.avail_docks
            from sqlalchemy.orm import Session as _Session
            from src.routes.prediction_routes import _get_station_history
            with _Session(engine) as _sess:
                recent_bikes, station_median = _get_station_history(_sess, dropoff["station_id"])
            predicted_bikes = ml_predict(
                station_id=dropoff["station_id"],
                dt=arrival_dt,
                lat=dropoff["lat"],
                lon=dropoff["lng"],
                temp=temp,
                humidity=humidity,
                recent_bikes=recent_bikes,
                station_median=station_median,
            )
            predicted_stands = max(0, capacity - predicted_bikes)
        except Exception as exc:
            logger.warning("ML prediction for dropoff failed: %s", exc)
        # ────────────────────────────────────────────────────────────────────

        return {
            "mode": "bike",
            "pickup_station": {
                "station_id": pickup["station_id"],
                "name": pickup["name"],
                "position": {"lat": pickup["lat"], "lng": pickup["lng"]},
                "available_bikes": pickup["avail_bikes"],
                "walking_distance_m": round(pickup["distance_m"]),
                "status": pickup["status"],
            },
            "dropoff_station": {
                "station_id": dropoff["station_id"],
                "name": dropoff["name"],
                "position": {"lat": dropoff["lat"], "lng": dropoff["lng"]},
                "available_bike_stands": dropoff["avail_docks"],
                "predicted_stands": predicted_stands,
                "walking_distance_m": round(dropoff["distance_m"]),
                "status": dropoff["status"],
            },
            "start": {"lat": start_lat, "lng": start_lng},
            "end": {"lat": end_lat, "lng": end_lng},
            "times_minutes": best["times_minutes"],
            "penalties": best["penalties"],
            "total_walking_m": round(pickup["distance_m"] + dropoff["distance_m"]),
            # coords are [[lat, lng], ...] — ready for Leaflet <Polyline positions={...}>
            "polylines": {
                "walk_to_pickup": walk1.coords,
                "bike": bike.coords,
                "walk_to_destination": walk2.coords,
            },
            "alternatives": options[1:5],
            "weather": weather_meta,
            "baseline_walk_minutes": direct_walk_min,
        }


# ── New candidate-based planning ──────────────────────────────────────────────

def get_candidates(
    *,
    engine: Engine,
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    departure_dt: datetime,
) -> dict[str, Any]:
    """
    Step 1 of new planning flow.
    Returns ML-ranked pickup and dropoff candidate stations.
    Pickup candidates: predicted_bikes > 2 at departure_dt, sorted desc.
    Dropoff candidates: all within 1500m, sorted by predicted_docks desc.
    """
    from src.routes.prediction_routes import _get_station_history

    cache: dict = {}

    with Session(engine) as session:
        weather = get_latest_weather(engine)
        temp     = weather["temp"]     if weather else 12.0
        humidity = weather["humidity"] if weather else 75.0

        pickup_nearby  = _nearest_candidates(session, start_lat, start_lng, DEFAULT_MAX_STATION_DISTANCE_M, 10)
        dropoff_nearby = _nearest_candidates(session, end_lat,   end_lng,   DEFAULT_MAX_STATION_DISTANCE_M, 10)

        # Estimate ride time (start → end, cycling) to approximate arrival time
        est_leg      = _osrm_leg(start_lat, start_lng, end_lat, end_lng, "cycling", cache)
        est_ride_min = _mins(est_leg.seconds)
        arrival_dt   = departure_dt + timedelta(minutes=est_ride_min)

        # ML predict for pickup candidates
        pickup_candidates: list[dict] = []
        for s in pickup_nearby:
            try:
                recent_bikes, station_median = _get_station_history(session, s.station_id)
                predicted = ml_predict(
                    station_id=s.station_id,
                    dt=departure_dt,
                    lat=s.lat, lon=s.lng,
                    temp=temp, humidity=humidity,
                    recent_bikes=recent_bikes,
                    station_median=station_median,
                )
            except Exception:
                predicted = s.avail_bikes

            if predicted > 2:
                pickup_candidates.append({**_station_dict(s), "predicted_bikes": predicted})

        pickup_candidates.sort(key=lambda x: x["predicted_bikes"], reverse=True)

        # ML predict for dropoff candidates
        dropoff_candidates: list[dict] = []
        for s in dropoff_nearby:
            try:
                recent_bikes, station_median = _get_station_history(session, s.station_id)
                predicted_bikes = ml_predict(
                    station_id=s.station_id,
                    dt=arrival_dt,
                    lat=s.lat, lon=s.lng,
                    temp=temp, humidity=humidity,
                    recent_bikes=recent_bikes,
                    station_median=station_median,
                )
                capacity        = s.avail_bikes + s.avail_docks
                predicted_docks = max(0, capacity - predicted_bikes)
            except Exception:
                predicted_docks = s.avail_docks

            dropoff_candidates.append({**_station_dict(s), "predicted_docks": predicted_docks})

        dropoff_candidates.sort(key=lambda x: x["predicted_docks"], reverse=True)

        return {
            "pickup_candidates":      pickup_candidates,
            "dropoff_candidates":     dropoff_candidates,
            "estimated_ride_minutes": round(est_ride_min, 1),
            "arrival_time":           arrival_dt.isoformat(),
        }


def plan_route_simple(
    *,
    engine: Engine,
    pickup_id: int,
    dropoff_id: int,
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    preference: str = "recommended",
) -> dict[str, Any]:
    """
    Step 2 of new planning flow.
    Given user-selected pickup and dropoff stations, compute the three-leg route.
    Cycling leg uses ORS with the given preference (falls back to OSRM if no key).
    preference: 'recommended' | 'fastest' | 'shortest'
    """
    cache: dict = {}

    with Session(engine) as session:
        statuses   = _latest_status(session)
        pickup_st  = session.get(Station, pickup_id)
        dropoff_st = session.get(Station, dropoff_id)

        if not pickup_st or not dropoff_st:
            raise RoutePlanningError("Station not found")

        pickup_status  = statuses.get(pickup_id,  {})
        dropoff_status = statuses.get(dropoff_id, {})

        walk1 = _osrm_leg(start_lat, start_lng,
                          float(pickup_st.latitude), float(pickup_st.longitude),
                          "walking", cache)
        bike  = _ors_cycling_leg(float(pickup_st.latitude),  float(pickup_st.longitude),
                                  float(dropoff_st.latitude), float(dropoff_st.longitude),
                                  preference, cache)
        walk2 = _osrm_leg(float(dropoff_st.latitude), float(dropoff_st.longitude),
                          end_lat, end_lng,
                          "walking", cache)

        walk1_min = _mins(walk1.seconds)
        bike_min  = _mins(bike.seconds)
        walk2_min = _mins(walk2.seconds)

        return {
            "mode": "bike",
            "pickup_station": {
                "station_id":    pickup_st.station_id,
                "name":          pickup_st.name,
                "position":      {"lat": float(pickup_st.latitude), "lng": float(pickup_st.longitude)},
                "available_bikes": pickup_status.get("avail_bikes", 0),
                "status":        pickup_status.get("status", ""),
            },
            "dropoff_station": {
                "station_id":          dropoff_st.station_id,
                "name":                dropoff_st.name,
                "position":            {"lat": float(dropoff_st.latitude), "lng": float(dropoff_st.longitude)},
                "available_bike_stands": dropoff_status.get("avail_docks", 0),
                "status":              dropoff_status.get("status", ""),
            },
            "times_minutes": {
                "walk_to_pickup":       walk1_min,
                "bike":                 bike_min,
                "walk_to_destination":  walk2_min,
                "total_travel":         round(walk1_min + bike_min + walk2_min, 2),
            },
            "cycling_preference": preference,
            "polylines": {
                "walk_to_pickup":      walk1.coords,
                "bike":                bike.coords,
                "walk_to_destination": walk2.coords,
            },
        }
