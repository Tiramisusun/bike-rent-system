import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from services.bikes_service import fetch_jcdecaux_stations
from services.weather_service import fetch_openweather_current
from services.routing_service import get_route_eta, compare_eta

load_dotenv()

app = Flask(__name__, static_url_path="")


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/bikes")
def api_bikes():
    try:
        data = fetch_jcdecaux_stations()
        return jsonify({"source": "jcdecaux", "count": len(data), "data": data})
    except requests.RequestException as e:
        return jsonify({"source": "jcdecaux", "error": "Request failed", "details": str(e)}), 502
    except Exception as e:
        return jsonify({"source": "jcdecaux", "error": "Server error", "details": str(e)}), 500


@app.route("/api/weather")
def api_weather():
    try:
        data = fetch_openweather_current()
        return jsonify({"source": "openweather", "data": data})
    except requests.RequestException as e:
        return jsonify({"source": "openweather", "error": "Request failed", "details": str(e)}), 502
    except Exception as e:
        return jsonify({"source": "openweather", "error": "Server error", "details": str(e)}), 500


# ====== NEW FEATURE: Route + ETA ======
# Example:
# /api/route?origin=53.3498,-6.2603&destination=53.3438,-6.2546&profile=cycling
@app.route("/api/route")
def api_route():
    try:
        origin = request.args.get("origin", "")
        destination = request.args.get("destination", "")
        profile = request.args.get("profile", "driving")

        result = get_route_eta(origin=origin, destination=destination, profile=profile)
        return jsonify({"source": "osrm", "route": result})
    except ValueError as e:
        return jsonify({"source": "osrm", "error": "Bad request", "details": str(e)}), 400
    except requests.RequestException as e:
        return jsonify({"source": "osrm", "error": "Routing request failed", "details": str(e)}), 502
    except Exception as e:
        return jsonify({"source": "osrm", "error": "Server error", "details": str(e)}), 500


# ====== NEW FEATURE: Compare driving vs cycling ETA (+ optional weather) ======
# Example:
# /api/compare-eta?origin=53.3498,-6.2603&destination=53.3438,-6.2546&includeWeather=1
@app.route("/api/compare-eta")
def api_compare_eta():
    try:
        origin = request.args.get("origin", "")
        destination = request.args.get("destination", "")
        include_weather = request.args.get("includeWeather", "0") in ("1", "true", "True")

        cmp = compare_eta(origin=origin, destination=destination)

        payload = {"source": "osrm", "comparison": cmp}

        if include_weather:
            # just attach current weather snapshot (city-based)
            weather = fetch_openweather_current()
            payload["weather"] = {"source": "openweather", "data": weather}

        return jsonify(payload)
    except ValueError as e:
        return jsonify({"error": "Bad request", "details": str(e)}), 400
    except requests.RequestException as e:
        return jsonify({"error": "External request failed", "details": str(e)}), 502
    except Exception as e:
        return jsonify({"error": "Server error", "details": str(e)}), 500


if __name__ == "__main__":
    # host="0.0.0.0" 允许外网通过 EC2 公网IP访问
    app.run(host="0.0.0.0", port=5000, debug=True)