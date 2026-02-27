import requests
import json
from pathlib import Path
from datetime import datetime
from src.common.config import settings

from src.db import load_engine, db_from_request

OPENWEATHER_BASE = "https://pro.openweathermap.org/data/2.5"
CURRENT_URL = f"{OPENWEATHER_BASE}/weather"
FORECAST_URL = f"{OPENWEATHER_BASE}/forecast"   # 5 days / 3-hour forecast


def fetch_openweather_current() -> dict:
    """Fetch current weather data from OpenWeather API (PRO)."""
    if not settings.openweather_api_key:
        raise RuntimeError("OPENWEATHER_API_KEY is empty")

    params = {
        "q": settings.openweather_city,          # e.g. "Dublin,ie"
        "APPID": settings.openweather_api_key,   # PRO email recommend APPID
        "units": settings.openweather_units,     # "metric"
    }
    r = requests.get(CURRENT_URL, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def fetch_openweather_forecast_5d3h() -> dict:
    """Fetch 5-day / 3-hour forecast data from OpenWeather API (PRO)."""
    if not settings.openweather_api_key:
        raise RuntimeError("OPENWEATHER_API_KEY is empty")

    params = {
        "q": settings.openweather_city,
        "APPID": settings.openweather_api_key,
        "units": settings.openweather_units,
    }
    r = requests.get(FORECAST_URL, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def save_json(json_data: dict, filename_prefix: str = "weather") -> Path:
    """Save JSON data to a file with a timestamp."""
    folder = Path("data")
    folder.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    path = folder / f"{filename_prefix}_{timestamp}.json"

    with path.open("w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    return path


def main():
    # Fetch both current weather and forecast, then save to files.
    current = fetch_openweather_current()
    forecast = fetch_openweather_forecast_5d3h()
    # Note: You could also insert into DB here if desired, but for now we just save to files.
    p1 = save_json(current, filename_prefix="weather_current")
    p2 = save_json(forecast, filename_prefix="weather_forecast_5d3h")

    print(f"Saved OpenWeather CURRENT JSON to: {p1}")
    print(f"Saved OpenWeather FORECAST JSON to: {p2}")

    try: 
        engine = load_engine() 
        db_from_request(current, typ="weather", engine=engine) 
        print("Inserted CURRENT weather into DB ") 

        db_from_request(forecast, typ="weather_forecast_5d3h", engine=engine)
        print("Inserted FORECAST weather into DB ")
    except Exception as e: 
        print(f"DB insert skipped/failed : {e}")

if __name__ == "__main__":
    main()