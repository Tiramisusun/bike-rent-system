import os
import time
from datetime import datetime

import requests
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

# -------- ENV --------
API_KEY = os.getenv("JCDECAUX_API_KEY")
CONTRACT = os.getenv("JCDECAUX_CONTRACT_NAME", "dublin")

DB_HOST = os.getenv("DB_HOST", "db")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "bike_app")

STATIONS_URL = "https://api.jcdecaux.com/vls/v1/stations"


# -------- Helpers --------
def fetch_stations():
    if not API_KEY:
        raise ValueError("JCDECAUX_API_KEY is missing in .env")

    params = {"contract": CONTRACT, "apiKey": API_KEY}
    r = requests.get(STATIONS_URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def get_conn():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
    )


def to_dt_utc_from_ms(ms: int) -> datetime:
    """JCDecaux last_update is milliseconds since epoch (UTC). Store as naive UTC DATETIME."""
    return datetime.utcfromtimestamp(ms / 1000).replace(microsecond=0)


# -------- DB writes --------
def upsert_station(cur, s: dict):
    """Static station metadata -> station table."""
    cur.execute(
        """
        INSERT INTO station
        (number, contract_name, name, address, banking, bonus, bike_stands, position_lat, position_lng, status)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
          contract_name=VALUES(contract_name),
          name=VALUES(name),
          address=VALUES(address),
          banking=VALUES(banking),
          bonus=VALUES(bonus),
          bike_stands=VALUES(bike_stands),
          position_lat=VALUES(position_lat),
          position_lng=VALUES(position_lng),
          status=VALUES(status)
        """,
        (
            s.get("number"),
            s.get("contract_name"),
            s.get("name"),
            s.get("address"),
            1 if s.get("banking") else 0,
            1 if s.get("bonus") else 0,
            s.get("bike_stands"),
            (s.get("position") or {}).get("lat"),
            (s.get("position") or {}).get("lng"),
            s.get("status"),
        ),
    )


def insert_availability(cur, s: dict):
    """Dynamic availability -> availability table (time series)."""
    ms = s.get("last_update")
    last_update_dt = to_dt_utc_from_ms(ms) if ms else datetime.utcnow().replace(microsecond=0)

    # Ignore duplicates for (number, last_update) primary key
    cur.execute(
        """
        INSERT IGNORE INTO availability
        (number, last_update, available_bikes, available_bike_stands, status)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            s.get("number"),
            last_update_dt,
            s.get("available_bikes"),
            s.get("available_bike_stands"),
            s.get("status"),
        ),
    )


# -------- Main loop --------
def run_once():
    stations = fetch_stations()
    print(f" Fetched {len(stations)} stations")

    conn = get_conn()
    cur = conn.cursor()
    try:
        for s in stations:
            upsert_station(cur, s)
            insert_availability(cur, s)

        conn.commit()
        print(" Inserted station + availability batch")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    INTERVAL_SECONDS = 300  # 5 minutes
    RUNS = 576  # 2 days * 24h * 12 runs per hour

    for i in range(1, RUNS + 1):
        print(f"\n--- Run {i}/{RUNS} ---")
        try:
            run_once()
        except Exception as e:
            print(f" Error during run_once(): {repr(e)}")

        if i < RUNS:
            time.sleep(INTERVAL_SECONDS)

    print("\n Finished scheduled collection (2 days).")