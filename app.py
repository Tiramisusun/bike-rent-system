import os
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template

load_dotenv()

app = Flask(__name__, static_url_path="")

# ----- Config from .env -----
JCDECAUX_API_KEY = os.getenv("JCDECAUX_API_KEY")
JCDECAUX_CONTRACT_NAME = os.getenv("JCDECAUX_CONTRACT_NAME", "dublin")

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
CITY_NAME = os.getenv("CITY_NAME", "Dublin")

JCDECAUX_URL = "https://api.jcdecaux.com/vls/v1/stations"
OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


# ----- Helpers -----
def fetch_jcdecaux_stations() -> list:
    if not JCDECAUX_API_KEY:
        raise ValueError("Missing JCDECAUX_API_KEY in .env")

    params = {"contract": JCDECAUX_CONTRACT_NAME, "apiKey": JCDECAUX_API_KEY}
    r = requests.get(JCDECAUX_URL, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def fetch_openweather_current() -> dict:
    if not OPENWEATHER_API_KEY:
        raise ValueError("Missing OPENWEATHER_API_KEY in .env")

    params = {"q": CITY_NAME, "appid": OPENWEATHER_API_KEY, "units": "metric"}
    r = requests.get(OPENWEATHER_URL, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


# ----- Routes -----
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
"""比上次加入了host="0.0.0.0"允许外网通过EC2公网IP访问, port=5000, debug=True参数，这样可以让应用在所有网络接口上监听，并且启用调试模式，方便开发和测试。

"""