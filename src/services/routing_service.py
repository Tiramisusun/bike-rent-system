import requests


OSRM_BASE = "https://router.project-osrm.org/route/v1"


def _parse_latlng(s: str) -> tuple[float, float]:
    """
    Accepts 'lat,lng' (e.g. '53.3498,-6.2603')
    Returns (lat, lng) floats.
    """
    if not s or "," not in s:
        raise ValueError("Invalid coordinate format. Use 'lat,lng'.")

    lat_str, lng_str = s.split(",", 1)
    lat = float(lat_str.strip())
    lng = float(lng_str.strip())

    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError("Coordinates out of range.")

    return lat, lng


def get_route_eta(*, origin: str, destination: str, profile: str = "driving") -> dict:
    """
    Calls OSRM and returns distance/duration.
    origin, destination: 'lat,lng'
    profile: 'driving' or 'cycling' (OSRM supports these two on demo server)
    """
    if profile not in ("driving", "cycling"):
        raise ValueError("profile must be 'driving' or 'cycling'")

    o_lat, o_lng = _parse_latlng(origin)
    d_lat, d_lng = _parse_latlng(destination)

    # OSRM expects lng,lat order in the URL
    coords = f"{o_lng},{o_lat};{d_lng},{d_lat}"
    url = f"{OSRM_BASE}/{profile}/{coords}"

    params = {
        "overview": "false",   # set "full" if you want geometry for map drawing
        "alternatives": "false",
        "steps": "false",
    }

    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError(f"Routing failed: {data}")

    route0 = data["routes"][0]
    return {
        "profile": profile,
        "distance_m": route0.get("distance"),
        "duration_s": route0.get("duration"),
    }


def compare_eta(*, origin: str, destination: str) -> dict:
    """
    Compare driving vs cycling ETA.
    """
    driving = get_route_eta(origin=origin, destination=destination, profile="driving")
    cycling = get_route_eta(origin=origin, destination=destination, profile="cycling")

    def _mins(seconds: float | int | None) -> float | None:
        return None if seconds is None else round(float(seconds) / 60.0, 1)

    return {
        "origin": origin,
        "destination": destination,
        "driving": {**driving, "duration_min": _mins(driving["duration_s"])},
        "cycling": {**cycling, "duration_min": _mins(cycling["duration_s"])},
    }
