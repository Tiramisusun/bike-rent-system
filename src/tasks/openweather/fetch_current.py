import time

from src.db import load_engine, db_from_request, store_forecast_data
from src.services.weather_service import fetch_openweather_current, fetch_openweather_forecast


def run_once():
    engine = load_engine()

    current = fetch_openweather_current()
    db_from_request(current, "weather", engine=engine)
    print("Inserted current weather into DB")

    forecast = fetch_openweather_forecast()
    store_forecast_data(engine, forecast.get("list", []))
    print("Inserted forecast weather into DB")


if __name__ == "__main__":
    INTERVAL_SECONDS = 300  # 5 minutes
    RUNS = 576              # 2 days * 24h * 12 runs per hour

    for i in range(1, RUNS + 1):
        print(f"\n--- Run {i}/{RUNS} ---")
        try:
            run_once()
        except Exception as e:
            print(f" Error during run_once(): {repr(e)}")

        if i < RUNS:
            time.sleep(INTERVAL_SECONDS)

    print("\n Finished scheduled collection (2 days).")
