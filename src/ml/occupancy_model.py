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
    "is_morning_peak",
    "max_air_temperature_celsius",
    "air_temperature_std_deviation",
    "max_relative_humidity_percent",
    "lag_1",
    "lag_2",
    "lag_24",
    "lag_168",
    "rolling_mean_3",
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
    recent_bikes=None,
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
    hour             = dt.hour
    dow              = dt.weekday()
    rush_hour        = 1 if hour in (7, 8, 9, 16, 17, 18, 19) else 0
    is_morning_peak  = 1 if hour in (7, 8, 9) else 0

    bikes = recent_bikes or []
    lag_1          = float(bikes[0])   if len(bikes) >= 1   else 0.0
    lag_2          = float(bikes[1])   if len(bikes) >= 2   else 0.0
    lag_24         = float(bikes[23])  if len(bikes) >= 24  else 0.0
    lag_168        = float(bikes[167]) if len(bikes) >= 168 else 0.0
    rolling_mean_3 = float(sum(bikes[:3]) / 3) if len(bikes) >= 3 else (
                     float(sum(bikes) / len(bikes)) if bikes else 0.0)

    row = pd.DataFrame([{
        "station_id":                    station_id,
        "hour":                          hour,
        "month":                         dt.month,
        "year":                          dt.year,
        "lat":                           lat,
        "lon":                           lon,
        "day_of_week":                   dow,
        "rush_hour":                     rush_hour,
        "is_morning_peak":               is_morning_peak,
        "max_air_temperature_celsius":   temp,
        "air_temperature_std_deviation": 0.0,
        "max_relative_humidity_percent": humidity,
        "lag_1":                         lag_1,
        "lag_2":                         lag_2,
        "lag_24":                        lag_24,
        "lag_168":                       lag_168,
        "rolling_mean_3":                rolling_mean_3,
    }])

    model = _load_model()
    prediction = model.predict(row[FEATURES])[0]
    return max(0, round(float(prediction)))
