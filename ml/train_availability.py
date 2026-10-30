"""Train the availability model on the snapshots our own pipeline collected.

    python -m ml.train_availability --data data/snapshots.csv.gz --since 2026-10-08
                                                        # writes data/availability_model.pkl

`snapshots.csv` is an export of intermediate.int_station_snapshot_enriched (see ml/README.md).

The task is the one the app has: it is now time t, the station has b bikes — how many will it
have h minutes later? Training rows are built on a 30-minute grid of "now" times per station,
each paired with the true count at h = 10 min ... 24 h later. Features are built exactly as
src/ml/occupancy_model.py builds them at prediction time.

Evaluation is time-based: the last FOLDS x TEST_DAYS days are split into consecutive test
windows; each model trains only on rows whose *target* time is before the window (so nothing
from the window leaks in) and the usual-level profiles are recomputed from that past only.
Every model is compared at each horizon with two baselines:

    persistence   bikes later = bikes now
    profile       the station's average for that weekday/weekend and hour

Selection rule, fixed before looking at results: the learned model with the lowest MAE
averaged over all horizons. It is then refit on all rows and saved.

Serving rule, added after the first run showed persistence ahead of every model up to 1 h
(ml/README.md): from the shortest horizon up, as long as persistence's MAE is no worse than
the chosen model's, the app returns the current count; beyond that, the model.
"""

import argparse
import json
import pickle
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score

from src.ml.occupancy_model import FEATURES, LOCAL_TZ, STALE_AFTER

HORIZONS_MIN = [10, 30, 60, 120, 180, 360, 720, 1440]
ANCHOR_EVERY = "30min"
FOLDS = 4
TEST_DAYS = 2

CANDIDATES = {
    "gradient boosting": lambda: HistGradientBoostingRegressor(max_iter=300, random_state=42),
    "gradient boosting, MAE loss": lambda: HistGradientBoostingRegressor(
        loss="absolute_error", max_iter=300, random_state=42),
    "random forest": lambda: RandomForestRegressor(
        n_estimators=50, max_depth=12, min_samples_leaf=20, n_jobs=-1, random_state=42),
}
BASELINES = {
    "persistence": lambda X: X["bikes_now"],
    "profile": lambda X: X["profile_target"].fillna(X["bikes_now"]),   # station unseen in training
}


# ── Rows ──────────────────────────────────────────────────────────────────────

def load(path: str, since: str | None = None) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["is_open"].astype(str).str.lower().isin(["t", "true", "1"])]
    if since:     # e.g. skip sample rows loaded before continuous collection began
        df = df[pd.to_datetime(df["snapshot_at_utc"]) >= pd.Timestamp(since)]
    return pd.DataFrame({
        "station_id": df["station_id"].astype(int),
        "at": pd.to_datetime(df["snapshot_at_utc"]),
        "bikes": df["available_bikes"], "docks": df["available_docks"],
        "temperature_c": df["temperature_c"], "humidity_pct": df["humidity_pct"],
    }).sort_values("at").reset_index(drop=True)


def _asof(times: pd.DataFrame, snaps: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """State of each (station_id, at) as of `at`: latest snapshot at most STALE_AFTER old."""
    left = times[["station_id", "at"]].reset_index().sort_values("at")
    merged = pd.merge_asof(left, snaps[["station_id", "at", *cols]], on="at", by="station_id",
                           direction="backward", tolerance=pd.Timedelta(STALE_AFTER))
    return merged.set_index("index").loc[times.index, cols]


def local(ts: pd.Series) -> pd.Series:
    return ts.dt.tz_localize("UTC").dt.tz_convert(LOCAL_TZ)


def anchors(snaps: pd.DataFrame) -> pd.DataFrame:
    """Every station every 30 minutes, with its state at that moment (as the app sees it)."""
    grid = pd.date_range(snaps["at"].min().ceil(ANCHOR_EVERY), snaps["at"].max(), freq=ANCHOR_EVERY)
    a = pd.MultiIndex.from_product([snaps["station_id"].unique(), grid],
                                   names=["station_id", "at"]).to_frame(index=False)
    a[["bikes_now", "docks_now", "temperature_c", "humidity_pct"]] = _asof(
        a, snaps, ["bikes", "docks", "temperature_c", "humidity_pct"]).to_numpy()
    hour_ago = a.assign(at=a["at"] - pd.Timedelta(hours=1))
    a["trend_1h"] = a["bikes_now"] - _asof(hour_ago, snaps, ["bikes"])["bikes"].to_numpy()
    a["capacity"] = a["bikes_now"] + a["docks_now"]
    a = a.dropna(subset=["bikes_now"]).reset_index(drop=True)   # station silent for over an hour
    lt = local(a["at"])
    a["is_weekend"], a["hour"] = (lt.dt.dayofweek >= 5).astype(int), lt.dt.hour
    return a


def pairs(a: pd.DataFrame, snaps: pd.DataFrame) -> pd.DataFrame:
    """Each anchor x each horizon, with the true bike count at the target time."""
    out = []
    for h in HORIZONS_MIN:
        p = a.assign(horizon_min=h, target_at=a["at"] + pd.Timedelta(minutes=h))
        p = p[p["target_at"] <= snaps["at"].max()]
        p["target"] = _asof(p.rename(columns={"at": "anchor_at", "target_at": "at"}),
                            snaps, ["bikes"])["bikes"].to_numpy()
        out.append(p.dropna(subset=["target"]))
    p = pd.concat(out, ignore_index=True)
    tl = local(p["target_at"])
    p["target_hour"], p["day_of_week"] = tl.dt.hour, tl.dt.dayofweek
    p["target_is_weekend"] = (p["day_of_week"] >= 5).astype(int)
    return p


# ── Usual level per station (from the training period only) ──────────────────

def profiles(a: pd.DataFrame) -> dict:
    profile = a.groupby(["station_id", "is_weekend", "hour"])["bikes_now"].mean()
    station_mean = a.groupby("station_id")["bikes_now"].mean()
    return {
        "profile": {(int(s), int(w), int(h)): float(v) for (s, w, h), v in profile.items()},
        "station_mean": {int(s): float(v) for s, v in station_mean.items()},
    }


def features(p: pd.DataFrame, prof: dict) -> pd.DataFrame:
    """Same columns and fallbacks as occupancy_model.build_features."""
    station_mean = p["station_id"].map(prof["station_mean"])

    def lookup(weekend, hour):
        keys = zip(p["station_id"], weekend, hour)
        return pd.Series([prof["profile"].get(k, np.nan) for k in keys], index=p.index).fillna(station_mean)

    return pd.DataFrame({
        "horizon_min": p["horizon_min"],
        "bikes_now": p["bikes_now"],
        "capacity": p["capacity"],
        "trend_1h": p["trend_1h"],
        "profile_now": lookup(p["is_weekend"], p["hour"]),
        "profile_target": lookup(p["target_is_weekend"], p["target_hour"]),
        "station_mean": station_mean,
        "hour": p["target_hour"],
        "day_of_week": p["day_of_week"],
        "is_weekend": p["target_is_weekend"],
        "temperature_c": p["temperature_c"],
        "humidity_pct": p["humidity_pct"],
    })[FEATURES].astype(float)


# ── Evaluation ────────────────────────────────────────────────────────────────

def test_windows(a: pd.DataFrame, folds: int, test_days: int) -> list[tuple]:
    days = sorted(local(a["at"]).dt.normalize().unique())
    if len(days) < folds * test_days + 3:
        raise SystemExit(f"{len(days)} days of data: need at least {folds * test_days + 3} "
                         f"for {folds} test windows of {test_days} days plus 3 training days")
    starts = days[-folds * test_days::test_days]
    to_utc = lambda d: d.tz_convert("UTC").tz_localize(None)
    return [(to_utc(s), to_utc(s + pd.Timedelta(days=test_days))) for s in starts]


def evaluate(a, p, windows) -> tuple[dict, list]:
    """MAE and R² per model and horizon, averaged over the test windows."""
    scores = {name: {h: [] for h in HORIZONS_MIN} for name in [*BASELINES, *CANDIDATES]}
    fold_info = []
    for start, end in windows:
        prof = profiles(a[a["at"] < start])
        train = p[p["target_at"] < start]
        test = p[(p["at"] >= start) & (p["at"] < end)]
        X_tr, X_te = features(train, prof), features(test, prof)
        preds = {name: f(X_te) for name, f in BASELINES.items()}
        for name, make in CANDIDATES.items():
            t0 = time.time()
            preds[name] = make().fit(X_tr, train["target"]).predict(X_te)
            print(f"  {start:%m-%d} {name}: {time.time() - t0:.0f} s", flush=True)
        for name, pred in preds.items():
            pred = np.clip(np.asarray(pred, dtype=float), 0, X_te["capacity"].to_numpy())
            for h in HORIZONS_MIN:
                m = (test["horizon_min"] == h).to_numpy()
                if m.sum() < 2:       # window too close to the end of the data for this horizon
                    continue
                scores[name][h].append((mean_absolute_error(test["target"][m], pred[m]),
                                        r2_score(test["target"][m], pred[m])))
        fold_info.append({"test_from": str(start), "test_to": str(end),
                          "train_rows": len(train), "test_rows": len(test)})
    summary = {name: {h: {"mae": round(float(np.mean([s[0] for s in v])), 3),
                          "r2": round(float(np.mean([s[1] for s in v])), 3),
                          "mae_folds": [round(float(s[0]), 3) for s in v]}
                      for h, v in by_h.items() if v}
               for name, by_h in scores.items()}
    return summary, fold_info


def mean_mae(summary_model: dict) -> float:
    return float(np.mean([v["mae"] for v in summary_model.values()]))


def persistence_horizon(summary: dict, chosen: str) -> int:
    """Longest run of horizons, from the shortest, where persistence is at least as good."""
    up_to = 0
    for h in HORIZONS_MIN:
        if h not in summary[chosen] or summary["persistence"][h]["mae"] > summary[chosen][h]["mae"]:
            break
        up_to = h
    return up_to


def served(summary: dict, chosen: str, up_to: int) -> dict:
    """What the app serves: persistence up to `up_to` minutes, the model after."""
    return {h: summary["persistence" if h <= up_to else chosen][h] for h in summary[chosen]}


def table(summary: dict, metric: str) -> str:
    names = list(summary)
    lines = ["| Horizon | " + " | ".join(names) + " |", "|---" * (len(names) + 1) + "|"]
    for h in summary[names[0]]:
        label = f"{h} min" if h < 60 else f"{h // 60} h"
        lines.append(f"| {label} | " + " | ".join(f"{summary[n][h][metric]:.2f}" for n in names) + " |")
    if metric == "mae":
        lines.append("| **mean** | " + " | ".join(f"**{mean_mae(summary[n]):.2f}**" for n in names) + " |")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--since", help="ignore snapshots before this UTC date, e.g. 2026-10-08")
    parser.add_argument("--out", default="data/availability_model.pkl")
    parser.add_argument("--report-dir", default="ml/results")
    parser.add_argument("--folds", type=int, default=FOLDS)
    parser.add_argument("--test-days", type=int, default=TEST_DAYS)
    args = parser.parse_args()

    snaps = load(args.data, args.since)
    a = anchors(snaps)
    p = pairs(a, snaps)
    days = local(a["at"]).dt.normalize().nunique()
    print(f"{len(snaps)} snapshots, {snaps['station_id'].nunique()} stations, "
          f"{snaps['at'].min()} -> {snaps['at'].max()} UTC ({days} days); "
          f"{len(a)} anchors, {len(p)} training pairs", flush=True)

    windows = test_windows(a, args.folds, args.test_days)
    summary, fold_info = evaluate(a, p, windows)
    chosen = min(CANDIDATES, key=lambda n: mean_mae(summary[n]))
    up_to = persistence_horizon(summary, chosen)
    summary["served"] = served(summary, chosen, up_to)
    print("\nMAE (bikes)\n" + table(summary, "mae") + "\n\nR²\n" + table(summary, "r2"))
    print(f"\nchosen: {chosen}; served: current count up to {up_to} min, model after", flush=True)

    prof = profiles(a)
    model = CANDIDATES[chosen]().fit(features(p, prof), p["target"])
    trained_at = datetime.now(timezone.utc)
    data = {"snapshots": len(snaps), "stations": int(snaps["station_id"].nunique()), "days": int(days),
            "from_utc": str(snaps["at"].min()), "to_utc": str(snaps["at"].max()), "pairs": len(p)}
    artifact = {"model": model, **prof, "features": FEATURES, "chosen": chosen,
                "persistence_up_to_min": up_to,
                "trained_at": trained_at.isoformat(timespec="seconds"), "data": data}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "wb") as f:
        pickle.dump(artifact, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"saved {args.out} ({Path(args.out).stat().st_size / 1e6:.1f} MB)", flush=True)

    Path(args.report_dir).mkdir(parents=True, exist_ok=True)
    path = Path(args.report_dir) / f"availability-{trained_at:%Y%m%d-%H%M}.json"
    path.write_text(json.dumps({
        "trained_at": artifact["trained_at"], "data": {**data, "since": args.since}, "features": FEATURES,
        "horizons_min": HORIZONS_MIN, "anchor_every": ANCHOR_EVERY, "test_windows": fold_info,
        "selection_rule": "learned model with the lowest MAE averaged over horizons",
        "chosen": chosen,
        "serving_rule": "current count while persistence MAE <= model MAE, from the shortest horizon up",
        "persistence_up_to_min": up_to, "results": summary,
    }, indent=2))
    print(f"report: {path}", flush=True)


if __name__ == "__main__":
    main()
