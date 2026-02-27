import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flasgger import Swagger

from src.services.routing_service import get_route_eta, compare_eta
from src.services.weather_service import fetch_openweather_current
from src.db import load_engine, init_db
from src.routes.bikes_routes import bikes_bp
from src.routes.weather_routes import weather_bp

load_dotenv()

app = Flask(__name__, static_url_path="")
Swagger(app, template={
    "info": {
        "title": "Dublin Bike & Weather API",
        "description": "API for retrieving real-time and historical Dublin bike station and weather data.",
        "version": "1.0.0",
    }
})

engine = load_engine()
init_db(engine)
app.extensions['engine'] = engine

app.register_blueprint(bikes_bp)
app.register_blueprint(weather_bp)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/route")
def api_route():
    """
    Get route distance and duration between two coordinates.
    ---
    tags:
      - Routing
    parameters:
      - name: origin
        in: query
        required: true
        type: string
        description: Origin coordinates as 'lat,lng' (e.g. 53.3498,-6.2603)
      - name: destination
        in: query
        required: true
        type: string
        description: Destination coordinates as 'lat,lng' (e.g. 53.3438,-6.2546)
      - name: profile
        in: query
        required: false
        type: string
        enum: [driving, cycling]
        default: driving
    responses:
      200:
        description: Route distance and duration from OSRM
      400:
        description: Invalid coordinates
      502:
        description: Routing service unavailable
    """
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


@app.route("/api/compare-eta")
def api_compare_eta():
    """
    Compare driving vs cycling ETA between two coordinates.
    ---
    tags:
      - Routing
    parameters:
      - name: origin
        in: query
        required: true
        type: string
        description: Origin coordinates as 'lat,lng'
      - name: destination
        in: query
        required: true
        type: string
        description: Destination coordinates as 'lat,lng'
      - name: includeWeather
        in: query
        required: false
        type: string
        enum: ["0", "1"]
        default: "0"
        description: Set to 1 to include current weather data
    responses:
      200:
        description: Driving and cycling ETA comparison
      400:
        description: Invalid coordinates
      502:
        description: External service unavailable
    """
    try:
        origin = request.args.get("origin", "")
        destination = request.args.get("destination", "")
        include_weather = request.args.get("includeWeather", "0") in ("1", "true", "True")

        cmp = compare_eta(origin=origin, destination=destination)
        payload = {"source": "osrm", "comparison": cmp}

        if include_weather:
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
    app.run(host="0.0.0.0", port=5000, debug=True)
