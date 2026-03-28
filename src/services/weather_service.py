import os
import requests


OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
OPENWEATHER_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"


def fetch_openweather_forecast() -> dict:
    api_key = os.getenv("OPENWEATHER_API_KEY")
    city_name = os.getenv("CITY_NAME", "Dublin")

    if not api_key:
        raise ValueError("Missing OPENWEATHER_API_KEY in .env")

    params = {"q": city_name, "appid": api_key, "units": "metric", "cnt": 40}
    r = requests.get(OPENWEATHER_FORECAST_URL, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def fetch_openweather_current() -> dict:
    api_key = os.getenv("OPENWEATHER_API_KEY")
    city_name = os.getenv("CITY_NAME", "Dublin")

    if not api_key:
        raise ValueError("Missing OPENWEATHER_API_KEY in .env")

    params = {"q": city_name, "appid": api_key, "units": "metric"}
    r = requests.get(OPENWEATHER_URL, params=params, timeout=20)
    r.raise_for_status()
    return r.json()