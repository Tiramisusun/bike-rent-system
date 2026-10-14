"""Exploratory: how do models do on the data our own pipeline collects?

    python -m ml.explore_warehouse --data <csv exported from intermediate.int_station_snapshot_enriched>

Not a training script — with only a few days of data the numbers are indicative at best.
Compares, on the same rows and the same time-series folds:

  1. the deployed model (trained on December 2024) predicting October 2026 as-is
  2. the same random-forest configuration retrained on our own snapshots
  3. a station-average baseline: predict each station's mean from the training fold

Weather features are filled exactly as the app does at prediction time: current
temperature for "max air temperature", 0 for its standard deviation, current humidity.
"""

import argparse
import json
import pickle
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import TimeSeriesSplit

from ml.train import FEATURES

DEPLOYED_PARAMS = dict(n_estimators=100, max_depth=12, min_samples_leaf=20)


def prepare(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["snapshot_at_local"])
    df = df.dropna(subset=["temperature_c", "humidity_pct"]).sort_values("snapshot_at_local").reset_index(drop=True)
    t = df["snapshot_at_local"]
    return pd.DataFrame({
        "station_id": df["station_id"], "hour": t.dt.hour, "month": t.dt.month, "year": t.dt.year,
        "lat": df["latitude"], "lon": df["longitude"], "day_of_week": t.dt.dayofweek,
        "rush_hour": t.dt.hour.isin([7, 8, 9, 16, 17, 18, 19]).astype(int),
        "max_air_temperature_celsius": df["temperature_c"],
        "air_temperature_std_deviation": 0.0,
        "max_relative_humidity_percent": df["humidity_pct"],
        "available_bikes": df["available_bikes"], "time": t,
    })


def scores(y, p) -> dict:
    return {"r2": round(float(r2_score(y, p)), 3), "mae": round(float(mean_absolute_error(y, p)), 2)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--model", default="data/best_bike_model.pkl")
    args = parser.parse_args()

    df = prepare(args.data)
    X, y = df[FEATURES], df["available_bikes"]
    deployed = pickle.load(open(args.model, "rb"))
    print(f"{len(df)} snapshots, {df['station_id'].nunique()} stations, "
          f"{df['time'].min()} -> {df['time'].max()} ({df['time'].dt.date.nunique()} days)")

    folds = {"deployed (Dec 2024 model)": [], "retrained on our data": [], "station-average baseline": []}
    for i, (tr, te) in enumerate(TimeSeriesSplit(n_splits=5).split(X)):
        y_te = y.iloc[te]
        folds["deployed (Dec 2024 model)"].append(scores(y_te, deployed.predict(X.iloc[te])))
        rf = RandomForestRegressor(random_state=42, n_jobs=-1, **DEPLOYED_PARAMS).fit(X.iloc[tr], y.iloc[tr])
        folds["retrained on our data"].append(scores(y_te, rf.predict(X.iloc[te])))
        means = y.iloc[tr].groupby(X.iloc[tr]["station_id"]).mean()
        baseline = X.iloc[te]["station_id"].map(means).fillna(y.iloc[tr].mean())
        folds["station-average baseline"].append(scores(y_te, baseline))
        span = df["time"].iloc[te]
        print(f"fold {i + 1}: test {span.min():%m-%d %H:%M} -> {span.max():%m-%d %H:%M} ({len(te)} rows)")

    print(f"\n{'model':28} {'mean R²':>8} {'mean MAE':>9}   R² per fold")
    summary = {}
    for name, fs in folds.items():
        r2, mae = np.mean([f["r2"] for f in fs]), np.mean([f["mae"] for f in fs])
        summary[name] = {"mean_r2": round(float(r2), 3), "mean_mae": round(float(mae), 2), "folds": fs}
        print(f"{name:28} {r2:8.3f} {mae:9.2f}   {[f['r2'] for f in fs]}")

    out = Path("ml/results") / f"explore-warehouse-{datetime.now(timezone.utc):%Y%m%d-%H%M}.json"
    out.write_text(json.dumps({
        "note": "exploratory; few days of data",
        "data": {"rows": len(df), "from": str(df["time"].min()), "to": str(df["time"].max()),
                 "days": int(df["time"].dt.date.nunique())},
        "results": summary,
    }, indent=2))
    print(f"\nreport: {out}")


if __name__ == "__main__":
    main()
