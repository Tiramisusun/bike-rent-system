import time

from src.db import load_engine, db_from_request
from src.services.bikes_service import fetch_jcdecaux_stations


def run_once():
    stations = fetch_jcdecaux_stations()
    print(f" Fetched {len(stations)} stations")

    engine = load_engine()
    db_from_request(stations, "bike-static", engine=engine)
    db_from_request(stations, "bike-dynamic", engine=engine)
    print(" Inserted station + availability batch")


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
