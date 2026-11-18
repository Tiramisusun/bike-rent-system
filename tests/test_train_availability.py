"""Training rows for the availability model: same features as at prediction time, no leakage."""

import numpy as np
import pandas as pd
import pytest

from ml import train_availability as ta
from src.ml.occupancy_model import FEATURES, build_features


@pytest.fixture(scope="module")
def snaps():
    """Two stations, 12 days, a reading every 5 minutes with a daily pattern and some gaps."""
    rng = np.random.default_rng(0)
    times = pd.date_range("2026-10-01", "2026-10-13", freq="5min")
    rows = []
    for station, capacity in ((1, 30), (2, 20)):
        for t in times:
            if station == 2 and pd.Timestamp("2026-10-05 02:00") <= t < pd.Timestamp("2026-10-05 05:00"):
                continue                                    # outage: no readings for 3 hours
            bikes = int(np.clip(capacity / 2 + capacity / 3 * np.sin(t.hour / 24 * 2 * np.pi)
                                + rng.integers(-2, 3), 0, capacity))
            rows.append({"station_id": station, "at": t, "bikes": bikes, "docks": capacity - bikes,
                         "temperature_c": 10.0, "humidity_pct": 80.0})
    return pd.DataFrame(rows).sort_values("at").reset_index(drop=True)


@pytest.fixture(scope="module")
def built(snaps):
    a = ta.anchors(snaps)
    return a, ta.pairs(a, snaps)


def test_training_features_match_prediction_features(snaps, built):
    a, p = built
    prof = ta.profiles(a)
    X = ta.features(p, prof)
    sample = p.sample(25, random_state=1)
    for i, row in sample.iterrows():
        station = snaps[snaps["station_id"] == row["station_id"]]
        history = [(r.at.to_pydatetime(), r.bikes, r.docks)
                   for r in station[station["at"] <= row["at"]].iloc[::-1].itertuples()]
        live = build_features(prof, row["station_id"], row["target_at"].to_pydatetime(),
                              row["at"].to_pydatetime(), history, 10.0, 80.0).iloc[0]
        pd.testing.assert_series_equal(X.loc[i, FEATURES], live[FEATURES].astype(float),
                                       check_names=False)


def test_target_is_the_count_at_the_target_time(snaps, built):
    _, p = built
    row = p[(p["station_id"] == 1) & (p["horizon_min"] == 60)].iloc[100]
    actual = snaps[(snaps["station_id"] == 1) & (snaps["at"] <= row["target_at"])].iloc[-1]["bikes"]
    assert row["target"] == actual


def test_silent_station_has_no_anchors_during_outage(built):
    a, _ = built
    outage = a[(a["station_id"] == 2) & (a["at"] >= "2026-10-05 03:30") & (a["at"] < "2026-10-05 05:00")]
    assert outage.empty


def test_test_windows_are_consecutive_days_at_the_end(built):
    a, _ = built
    windows = ta.test_windows(a, folds=2, test_days=2)
    assert [(str(s), str(e)) for s, e in windows] == [   # Dublin midnight = 23:00 UTC in October
        ("2026-10-09 23:00:00", "2026-10-11 23:00:00"), ("2026-10-11 23:00:00", "2026-10-13 23:00:00")]
    with pytest.raises(SystemExit):
        ta.test_windows(a, folds=6, test_days=2)


def test_evaluation_trains_only_on_targets_before_the_window(built, monkeypatch):
    a, p = built
    seen = []

    class Spy:
        def fit(self, X, y):
            seen.append(X.index)
            return self

        def predict(self, X):
            return np.zeros(len(X))

    monkeypatch.setattr(ta, "CANDIDATES", {"spy": Spy})
    windows = ta.test_windows(a, folds=2, test_days=2)
    summary, _ = ta.evaluate(a, p, windows)
    for (start, _), idx in zip(windows, seen):
        assert p.loc[idx, "target_at"].max() < start
    assert set(summary) == {"persistence", "profile", "spy"}
    assert summary["persistence"][10]["mae"] < summary["persistence"][1440]["mae"]


def test_persistence_horizon_is_the_leading_run_where_persistence_wins():
    mae = lambda *v: {h: {"mae": m} for h, m in zip(ta.HORIZONS_MIN, v)}
    summary = {"persistence": mae(0.4, 0.9, 1.5, 2.4, 3.0, 2.0, 2.0, 2.0),
               "model":       mae(0.6, 1.0, 1.5, 2.2, 2.9, 4.0, 5.0, 5.0)}
    assert ta.persistence_horizon(summary, "model") == 60   # ties count; a later win doesn't
    served = ta.served(summary, "model", 60)
    assert served[60]["mae"] == 1.5 and served[120]["mae"] == 2.2
    summary["persistence"][10]["mae"] = 0.7
    assert ta.persistence_horizon(summary, "model") == 0
