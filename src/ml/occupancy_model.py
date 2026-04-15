"""
src/ml/occupancy_model.py

Loads the trained model and exposes a predict() function.
Model file: data/best_bike_model.pkl

Features used:
    station_id, hour, month, year, lat, lon,
    day_of_week, rush_hour,
    max_air_temperature_celsius, air_temperature_std_deviation,
    max_relative_humidity_percent
"""

import math
import os
import pickle
from pathlib import Path

import pandas as pd

FEATURES = [
    "station_id",
    "hour",
    "month",
    "year",
    "lat",
    "lon",
    "day_of_week",
    "rush_hour",
    "max_air_temperature_celsius",
    "air_temperature_std_deviation",
    "max_relative_humidity_percent",
]

_DEFAULT_MODEL_PATH = Path(__file__).parent.parent.parent / "data" / "best_bike_model.pkl"

_model = None


def _load_model():
    global _model
    if _model is None:
        path = Path(os.getenv("MODEL_PATH", str(_DEFAULT_MODEL_PATH)))
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")
        with open(path, "rb") as f:
            _model = pickle.load(f)
    return _model


def predict(
    station_id: int,
    dt,
    lat: float,
    lon: float,
    temp: float,
    humidity: float,
    **kwargs,
) -> int:
    """
    Predict available bikes for a station at a given datetime and weather.

    Parameters
    ----------
    station_id : int
    dt         : datetime object
    lat        : station latitude
    lon        : station longitude
    temp       : air temperature in Celsius
    humidity   : relative humidity percent

    Returns
    -------
    int : predicted number of available bikes (>= 0)
    """
    hour      = dt.hour
    dow       = dt.weekday()
    rush_hour = 1 if hour in (7, 8, 9, 16, 17, 18, 19) else 0

    row = pd.DataFrame([{
        "station_id":                    station_id,
        "hour":                          hour,
        "month":                         dt.month,
        "year":                          dt.year,
        "lat":                           lat,
        "lon":                           lon,
        "day_of_week":                   dow,
        "rush_hour":                     rush_hour,
        "max_air_temperature_celsius":   temp,
        "air_temperature_std_deviation": 0.0,
        "max_relative_humidity_percent": humidity,
    }])

    model = _load_model()
    prediction = model.predict(row[FEATURES])[0]
    return max(0, round(float(prediction)))
