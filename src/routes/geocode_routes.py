import os
import requests
from flask import Blueprint, jsonify, request

geocode_bp = Blueprint("geocode", __name__)

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OPENCAGE_URL = "https://api.opencagedata.com/geocode/v1/json"


def _nominatim_eircode(eircode: str):
    """Try Nominatim with the formatted Eircode + Ireland context."""
    params = {"format": "json", "q": f"{eircode}, Ireland", "limit": 1, "countrycodes": "ie"}
    resp = requests.get(NOMINATIM, params=params, headers={"Accept-Language": "en"}, timeout=8)
    resp.raise_for_status()
    data = resp.json()
    if data:
        return {
            "lat": float(data[0]["lat"]),
            "lng": float(data[0]["lon"]),
            "label": data[0]["display_name"],
            "source": "nominatim",
        }
    return None


def _opencage_eircode(eircode: str, api_key: str):
    """Resolve Eircode using OpenCage (more accurate, requires free API key)."""
    params = {
        "q": eircode,
        "key": api_key,
        "countrycode": "ie",
        "limit": 1,
        "no_annotations": 1,
    }
    resp = requests.get(OPENCAGE_URL, params=params, timeout=8)
    resp.raise_for_status()
    data = resp.json()
    if data.get("results"):
        r = data["results"][0]
        return {
            "lat": r["geometry"]["lat"],
            "lng": r["geometry"]["lng"],
            "label": r["formatted"],
            "source": "opencage",
        }
    return None


@geocode_bp.route("/api/geocode/eircode")
def api_geocode_eircode():
    """
    Geocode an Irish Eircode to lat/lng.
    Uses OpenCage if OPENCAGE_API_KEY is set, otherwise falls back to Nominatim.
    ---
    tags:
      - Geocoding
    parameters:
      - name: q
        in: query
        required: true
        type: string
        description: Eircode in canonical form, e.g. "A96 R8C4"
    responses:
      200:
        description: Geocoded coordinates
      404:
        description: Eircode not found
    """
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Missing query parameter 'q'"}), 400

    api_key = os.getenv("OPENCAGE_API_KEY", "")

    try:
        result = None
        if api_key:
            result = _opencage_eircode(q, api_key)
        if not result:
            result = _nominatim_eircode(q)
        if not result:
            return jsonify({"error": f"No results found for Eircode '{q}'"}), 404
        return jsonify(result)
    except requests.RequestException as exc:
        return jsonify({"error": f"Geocoding request failed: {exc}"}), 502
    except Exception as exc:
        return jsonify({"error": f"Geocoding error: {exc}"}), 500
