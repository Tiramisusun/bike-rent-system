"""Reproducible training for the station availability model (replaces running the notebook).

    python -m ml.train --data data/final_merged_data.csv --out data/best_bike_model.pkl

Preprocessing is identical to data/bike_availability_skeleton.ipynb, so results are comparable.
Every candidate is scored two ways:

    random split     80/20 shuffled split, as in the notebook. Neighbouring 10-minute
                     snapshots of the same station land on both sides, so this mostly
                     measures memorisation.
    time-series CV   TimeSeriesSplit(5): always train on the past, test on the future.
                     This is the number that reflects real use.

Selection rule, fixed before looking at results: among candidates whose time-series CV
MAE is within 2% of the unrestricted baseline (or better), take the smallest model.
The chosen configuration is then refit on all rows and saved.
"""

import argparse
import json
import pickle
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import TimeSeriesSplit, train_test_split

FEATURES = [
    "station_id", "hour", "month", "year", "lat", "lon", "day_of_week", "rush_hour",
    "max_air_temperature_celsius", "air_temperature_std_deviation", "max_relative_humidity_percent",
]
TARGET = "num_bikes_available"
MAE_TOLERANCE = 0.02
N_JOBS = 2                     # the unrestricted forest needs ~1 GB per parallel fit

CANDIDATES = {
    "baseline (notebook)":       dict(n_estimators=100),
    "depth 20, leaf 5, 50 trees":  dict(n_estimators=50, max_depth=20, min_samples_leaf=5),
    "depth 15, leaf 10, 50 trees": dict(n_estimators=50, max_depth=15, min_samples_leaf=10),
    "depth 12, leaf 20, 100 trees": dict(n_estimators=100, max_depth=12, min_samples_leaf=20),
    "leaf 20, 50 trees":           dict(n_estimators=50, min_samples_leaf=20),
}


def prepare(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """Same steps as notebook cells 13, 16 and 19. Rows end up in time order."""
    df = df.drop_duplicates().copy()
    df["last_reported"] = pd.to_datetime(df["last_reported"])
    df = df.sort_values("last_reported").reset_index(drop=True)
    df["date"] = pd.to_datetime(df[["year", "month", "day"]])
    df["day_of_week"] = df["date"].dt.dayofweek
    df["rush_hour"] = df["hour"].apply(lambda h: 1 if (7 <= h <= 9) or (16 <= h <= 19) else 0)
    return df[FEATURES], df[TARGET], df


def _model(params: dict) -> RandomForestRegressor:
    return RandomForestRegressor(random_state=42, n_jobs=N_JOBS, **params)


def evaluate(name: str, params: dict, X, y) -> dict:
    t0 = time.time()
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)
    model = _model(params).fit(X_tr, y_tr)
    pred = model.predict(X_te)
    blob = pickle.dumps(model, protocol=pickle.HIGHEST_PROTOCOL)
    load_t0 = time.time()
    pickle.loads(blob)
    load_s = time.time() - load_t0

    cv_mae, cv_r2 = [], []
    for train_idx, test_idx in TimeSeriesSplit(n_splits=5).split(X):
        m = clone(_model(params)).fit(X.iloc[train_idx], y.iloc[train_idx])
        p = m.predict(X.iloc[test_idx])
        cv_mae.append(mean_absolute_error(y.iloc[test_idx], p))
        cv_r2.append(r2_score(y.iloc[test_idx], p))

    result = {
        "name": name, "params": params,
        "random_split_mae": round(mean_absolute_error(y_te, pred), 4),
        "random_split_r2": round(r2_score(y_te, pred), 4),
        "ts_cv_mae": round(float(np.mean(cv_mae)), 4),
        "ts_cv_r2": round(float(np.mean(cv_r2)), 4),
        "ts_cv_r2_folds": [round(float(v), 4) for v in cv_r2],
        "size_mb": round(len(blob) / 1e6, 1),
        "load_s": round(load_s, 2),
        "eval_s": round(time.time() - t0),
    }
    print(json.dumps(result), flush=True)
    return result


def choose(results: list[dict]) -> dict:
    baseline = results[0]
    ok = [r for r in results if r["ts_cv_mae"] <= baseline["ts_cv_mae"] * (1 + MAE_TOLERANCE)]
    return min(ok, key=lambda r: r["size_mb"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/final_merged_data.csv")
    parser.add_argument("--out", default="data/best_bike_model.pkl")
    parser.add_argument("--report-dir", default="ml/results")
    args = parser.parse_args()

    X, y, df = prepare(pd.read_csv(args.data))
    print(f"{len(X)} rows, {df['station_id'].nunique()} stations, "
          f"{df['last_reported'].min()} -> {df['last_reported'].max()}", flush=True)

    results = [evaluate(name, params, X, y) for name, params in CANDIDATES.items()]
    chosen = choose(results)
    print(f"chosen: {chosen['name']}", flush=True)

    final = _model(chosen["params"]).fit(X, y)          # refit on all rows
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "wb") as f:
        pickle.dump(final, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"saved {args.out} ({Path(args.out).stat().st_size / 1e6:.1f} MB)", flush=True)

    report = {
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data": {"rows": len(X), "stations": int(df["station_id"].nunique()),
                 "from": str(df["last_reported"].min()), "to": str(df["last_reported"].max())},
        "features": FEATURES, "selection_rule": f"smallest model with ts-CV MAE within "
                                                f"{MAE_TOLERANCE:.0%} of the baseline",
        "candidates": results, "chosen": chosen["name"],
    }
    Path(args.report_dir).mkdir(parents=True, exist_ok=True)
    path = Path(args.report_dir) / f"{datetime.now(timezone.utc):%Y%m%d-%H%M}.json"
    path.write_text(json.dumps(report, indent=2))
    print(f"report: {path}", flush=True)


if __name__ == "__main__":
    main()
