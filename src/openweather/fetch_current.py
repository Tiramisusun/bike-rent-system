import requests
import json 
""" change dict in Python to .json"""
from pathlib import Path
from datetime import datetime
from src.common.config import settings
"""from src.db.engine import SessionLocal
from src.db.models import OpenWeatherCurrentSnapshot"""




def fetch_openweather_current() -> dict:
    """Fetch current weather data from OpenWeather API."""
    if not settings.openweather_api_key:
        raise RuntimeError("OPENWEATHER_API_KEY is empty")

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": settings.openweather_city,
        "appid": settings.openweather_api_key,
        "units": settings.openweather_units,
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status() 
    """ raise_for_status() will raise an HTTPError if the response was an error (4xx or 5xx) """
    return r.json()
    """change JSON to python dict and return"""


def save_json(json_data: dict, filename_prefix: str='weather') -> Path:
    """Save JSON data to a file with a timestamp."""
    

    folder = Path("data")
    folder.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    """Create a filename with the given prefix and current timestamp."""
    path = folder / f"{filename_prefix}_{timestamp}.json"

    with path.open("w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    return path

def main():
    payload = fetch_openweather_current()
    save_path = save_json(payload, filename_prefix="weather")
    print(f"Saved OpenWeather JSON to: {save_path}")

if __name__ == "__main__":
    main()

"""
def save_snapshot(payload: dict) -> None:
    
    main = payload.get("main") or {}
    row = OpenWeatherCurrentSnapshot(
        city=settings.openweather_city,
        temp=main.get("temp"),
        humidity=main.get("humidity"),
        pressure=main.get("pressure"),
        raw=payload,
    )
    db = SessionLocal()
   
    try:
        db.add(row)
        db.commit()
    finally:
        db.close()

def run():
    payload = fetch_openweather_current()
    save_snapshot(payload)

if __name__ == "__main__":
    run()
    print("OpenWeather snapshot saved.")   """