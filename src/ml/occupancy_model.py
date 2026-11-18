"""
src/ml/occupancy_model.py

Loads the trained availability model (built by `python -m ml.train_availability`)
and exposes predict().

The model forecasts bikes at a station `horizon_min` minutes ahead from what the
station looks like now: current bikes and capacity, the change over the last hour,
the station's usual level at this hour and at the target hour, calendar and weather.
Training and prediction build features with the same helpers below, so they agree.

Up to `persistence_up_to_min` (stored with the model; 60 in the first training) the
current count is returned instead: in evaluation it beat every model at those horizons.
"""

import math
import os
import pickle
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

LOCAL_TZ = ZoneInfo("Europe/Dublin")
MIN_HORIZON_MIN = 10
MAX_HORIZON_MIN = 24 * 60
STALE_AFTER = timedelta(minutes=60)   # older readings count as "unknown", as in training

FEATURES = [
    "horizon_min",
    "bikes_now",
    "capacity",
    "trend_1h",
    "profile_now",
    "profile_target",
    "station_mean",
    "hour",
    "day_of_week",
    "is_weekend",
    "temperature_c",
    "humidity_pct",
]

_DEFAULT_MODEL_PATH = Path(__file__).parent.parent.parent / "data" / "availability_model.pkl"

_model = None


def _load_model() -> dict:
    global _model
    if _model is None:
        path = Path(os.getenv("MODEL_PATH", str(_DEFAULT_MODEL_PATH)))
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")
        with open(path, "rb") as f:
            _model = pickle.load(f)
    return _model


def profile_lookup(artifact: dict, station_id, local_time) -> tuple[float, float]:
    """(usual bikes at this station, weekday/weekend and hour; station mean). NaN if unseen."""
    station_mean = artifact["station_mean"].get(station_id, math.nan)
    key = (station_id, int(local_time.weekday() >= 5), local_time.hour)
    return artifact["profile"].get(key, station_mean), station_mean


def _value_at(history, t):
    """Latest (bikes, docks) at or before t and at most STALE_AFTER old; history is newest first."""
    for update_time, bikes, docks in history:
        if update_time <= t:
            return (bikes, docks) if t - update_time <= STALE_AFTER else None
    return None


def build_features(artifact: dict, station_id: int, target_utc: datetime, now_utc: datetime,
                   history, temp, humidity) -> pd.DataFrame:
    """One feature row. Times are naive UTC, like StationStatus.update_time."""
    horizon = (target_utc - now_utc).total_seconds() / 60
    horizon = min(max(horizon, MIN_HORIZON_MIN), MAX_HORIZON_MIN)
    now_local = now_utc.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ)
    target_local = target_utc.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ)

    now_state = _value_at(history, now_utc)
    hour_ago = _value_at(history, now_utc - timedelta(hours=1))
    bikes_now = now_state[0] if now_state else math.nan
    capacity = sum(now_state) if now_state else math.nan
    trend = bikes_now - hour_ago[0] if now_state and hour_ago else math.nan
    profile_now, station_mean = profile_lookup(artifact, station_id, now_local)
    profile_target, _ = profile_lookup(artifact, station_id, target_local)

    return pd.DataFrame([{
        "horizon_min": horizon,
        "bikes_now": bikes_now,
        "capacity": capacity,
        "trend_1h": trend,
        "profile_now": profile_now,
        "profile_target": profile_target,
        "station_mean": station_mean,
        "hour": target_local.hour,
        "day_of_week": target_local.weekday(),
        "is_weekend": int(target_local.weekday() >= 5),
        "temperature_c": temp if temp is not None else math.nan,
        "humidity_pct": humidity if humidity is not None else math.nan,
    }])[FEATURES]


def to_utc(dt: datetime) -> datetime:
    """Naive datetimes are Dublin local time (what the date/time pickers send) -> naive UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def predict(station_id: int, dt: datetime, temp: float, humidity: float,
            history=(), now: datetime | None = None) -> int:
    """
    Predict available bikes at a station at time dt.

    Parameters
    ----------
    station_id : int
    dt         : target time; naive = Dublin local time
    temp       : current air temperature in Celsius
    humidity   : current relative humidity percent
    history    : recent (update_time naive UTC, bikes, docks) for the station, newest first
    now        : current time (naive UTC); defaults to the clock

    Returns
    -------
    int : predicted number of available bikes, between 0 and the station's capacity
    """
    artifact = _load_model()
    now_utc = now or datetime.now(timezone.utc).replace(tzinfo=None)
    row = build_features(artifact, station_id, to_utc(dt), now_utc, history, temp, humidity)
    bikes_now, capacity = row["bikes_now"].iloc[0], row["capacity"].iloc[0]
    if not math.isnan(bikes_now) and row["horizon_min"].iloc[0] <= artifact.get("persistence_up_to_min", 0):
        return int(bikes_now)
    prediction = max(0.0, float(artifact["model"].predict(row)[0]))
    if not math.isnan(capacity):
        prediction = min(prediction, capacity)
    return round(prediction)
