"""
src/ml/occupancy_model.py

Loads the trained model and exposes a predict() function.
Model file: data/best_bike_model.pkl
"""

import math
import os
import pickle
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

FEATURES = [
    # station / location
    "station_id", "lat", "lon",
    # basic time
    "hour", "month", "year", "day_of_week",
    "is_weekend", "rush_hour", "is_morning_peak", "is_evening_peak",
    # cyclical time
    "hour_sin", "hour_cos", "dow_sin", "dow_cos",
    # weather
    "max_air_temperature_celsius",
    "air_temperature_std_deviation",
    "max_relative_humidity_percent",
    # demand history
    "lag_1", "lag_2", "lag_3", "lag_24", "lag_168",
    "rolling_mean_3", "rolling_mean_24",
    "rolling_std_3", "rolling_std_24",
    "station_median_bikes",
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
    recent_bikes: Optional[List[int]] = None,
    station_median: Optional[float] = None,
) -> int:
    """
    Predict available bikes for a station at a given datetime and weather.

    Parameters
    ----------
    station_id     : int
    dt             : datetime object
    lat            : station latitude
    lon            : station longitude
    temp           : air temperature in Celsius
    humidity       : relative humidity percent
    recent_bikes   : list of recent avail_bikes values ordered newest→oldest
                     (used to compute lag_1..168 and rolling stats).
                     Falls back to zeros if not provided.
    station_median : median bikes for this station across all history.
                     Falls back to lag_1 if not provided.

    Returns
    -------
    int : predicted number of available bikes (>= 0)
    """
    hour       = dt.hour
    dow        = dt.weekday()
    is_weekend = 1 if dow >= 5 else 0
    rush_hour         = 1 if hour in (7, 8, 9, 16, 17, 18, 19) else 0
    is_morning_peak   = 1 if hour in (7, 8, 9) else 0
    is_evening_peak   = 1 if hour in (16, 17, 18, 19) else 0
    hour_sin   = math.sin(2 * math.pi * hour / 24)
    hour_cos   = math.cos(2 * math.pi * hour / 24)
    dow_sin    = math.sin(2 * math.pi * dow / 7)
    dow_cos    = math.cos(2 * math.pi * dow / 7)

    # Build lag / rolling features from recent_bikes (newest first)
    rb = list(recent_bikes) if recent_bikes else []

    def _get(idx: int) -> float:
        return float(rb[idx]) if idx < len(rb) else 0.0

    lag_1   = _get(0)
    lag_2   = _get(1)
    lag_3   = _get(2)
    lag_24  = _get(23)
    lag_168 = _get(167)

    window3  = [rb[i] for i in range(min(3,  len(rb)))] or [0]
    window24 = [rb[i] for i in range(min(24, len(rb)))] or [0]

    rolling_mean_3  = float(np.mean(window3))
    rolling_mean_24 = float(np.mean(window24))
    rolling_std_3   = float(np.std(window3))
    rolling_std_24  = float(np.std(window24))

    if station_median is None:
        station_median = lag_1

    row = pd.DataFrame([{
        "station_id":                    station_id,
        "lat":                           lat,
        "lon":                           lon,
        "hour":                          hour,
        "month":                         dt.month,
        "year":                          dt.year,
        "day_of_week":                   dow,
        "is_weekend":                    is_weekend,
        "rush_hour":                     rush_hour,
        "is_morning_peak":               is_morning_peak,
        "is_evening_peak":               is_evening_peak,
        "hour_sin":                      hour_sin,
        "hour_cos":                      hour_cos,
        "dow_sin":                       dow_sin,
        "dow_cos":                       dow_cos,
        "max_air_temperature_celsius":   temp,
        "air_temperature_std_deviation": 0,
        "max_relative_humidity_percent": humidity,
        "lag_1":                         lag_1,
        "lag_2":                         lag_2,
        "lag_3":                         lag_3,
        "lag_24":                        lag_24,
        "lag_168":                       lag_168,
        "rolling_mean_3":                rolling_mean_3,
        "rolling_mean_24":               rolling_mean_24,
        "rolling_std_3":                 rolling_std_3,
        "rolling_std_24":                rolling_std_24,
        "station_median_bikes":          station_median,
    }])

    model = _load_model()
    prediction = model.predict(row[FEATURES])[0]
    return max(0, round(float(prediction)))
