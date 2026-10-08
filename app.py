import os
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_jwt_extended import JWTManager
from flasgger import Swagger
from werkzeug.middleware.proxy_fix import ProxyFix

from src.extensions import limiter

from src.services.routing_service import get_route_eta, compare_eta
from src.services.weather_service import fetch_openweather_current
from src.db import load_engine, init_db
from src.routes.bikes_routes import bikes_bp
from src.routes.weather_routes import weather_bp
from src.routes.route_planner_routes import route_planner_bp
from src.routes.auth_routes import auth_bp
from src.routes.rental_routes import rental_bp
from src.routes.geocode_routes import geocode_bp
from src.routes.prediction_routes import prediction_bp

load_dotenv(override=False)  # env vars already set (e.g. in tests) take priority

DIST_DIR = os.path.join(os.path.dirname(__file__), 'frontend', 'dist')


def jwt_secret() -> str:
    """JWT signing key from the environment. No default: a key committed to a
    public repo would let anyone forge a token for any user."""
    secret = os.getenv("JWT_SECRET_KEY", "")
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be set to at least 32 characters "
                           "(e.g. `openssl rand -hex 32`)")
    return secret


app = Flask(__name__, static_folder=DIST_DIR, static_url_path='')
app.config["JWT_SECRET_KEY"] = jwt_secret()
JWTManager(app)

# Behind the Caddy reverse proxy the client IP arrives in X-Forwarded-For;
# trust exactly one proxy hop, and only when told we are behind one.
if os.getenv("TRUST_PROXY") == "1":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

app.config["RATELIMIT_ENABLED"] = os.getenv("RATELIMIT_ENABLED", "true").lower() == "true"
app.config["RATELIMIT_HEADERS_ENABLED"] = True
limiter.init_app(app)


@app.errorhandler(429)
def too_many_requests(e):
    return jsonify({"error": "Too many requests, please slow down"}), 429
Swagger(app, template={
    "info": {
        "title": "Dublin Bike & Weather API",
        "description": "API for retrieving real-time and historical Dublin bike station and weather data.",
        "version": "1.0.0",
    },
    "securityDefinitions": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "Enter: Bearer <your_token>",
        }
    },
    "security": [{"Bearer": []}],
})

engine = load_engine()
init_db(engine)
app.extensions['engine'] = engine

app.register_blueprint(bikes_bp)
app.register_blueprint(weather_bp)
app.register_blueprint(route_planner_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(rental_bp)
app.register_blueprint(geocode_bp)
app.register_blueprint(prediction_bp)


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def home(path):
    # Serve API routes normally (handled by blueprints above)
    # For everything else, return the React app's index.html
    full_path = os.path.join(DIST_DIR, path)
    if path and os.path.exists(full_path):
        return send_from_directory(DIST_DIR, path)
    return send_from_directory(DIST_DIR, 'index.html')


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
        app.logger.exception("Request failed with 502")
        return jsonify({"source": "osrm", "error": "Routing request failed"}), 502
    except Exception as e:
        app.logger.exception("Request failed with 500")
        return jsonify({"source": "osrm", "error": "Server error"}), 500


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
        app.logger.exception("Request failed with 502")
        return jsonify({"error": "External request failed"}), 502
    except Exception as e:
        app.logger.exception("Request failed with 500")
        return jsonify({"error": "Server error"}), 500


if __name__ == "__main__":
    # Development server only — production runs gunicorn (see Dockerfile).
    # The debugger allows arbitrary code execution, so it is opt-in.
    # 5001: macOS AirPlay Receiver occupies 5000
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", 5001)),
            debug=os.getenv("FLASK_DEBUG") == "1")
