"""
Tests for ML prediction endpoints and core prediction logic.

Unit tests:   calculate_cost, predict() feature building
Integration:  GET /api/predict, GET /api/predict/all

Run with:  pytest tests/test_prediction.py -v
"""
import math

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from src.routes.rental_routes import calculate_cost
from src.ml.occupancy_model import (FEATURES, MAX_HORIZON_MIN, MIN_HORIZON_MIN, build_features,
                                    predict, to_utc)


# ── Unit tests: pricing ───────────────────────────────────────────────────────

class TestCalculateCost:

    def test_free_within_30_minutes(self):
        assert calculate_cost(30) == 0.0

    def test_three_blocks_at_91_minutes(self):
        # 91 min = 30 free + 61 billable → 3 blocks (rounded up) → €1.50
        assert calculate_cost(91) == 1.50


# ── Unit tests: feature engineering ──────────────────────────────────────────

NOW = datetime(2026, 7, 1, 8, 0)          # naive UTC = 09:00 in Dublin (summer time)
ARTIFACT = {
    "profile": {(42, 0, 9): 6.0, (42, 0, 11): 3.0},
    "station_mean": {42: 7.0},
}
HISTORY = [                                # newest first: (update_time UTC, bikes, docks)
    (NOW - timedelta(minutes=4), 10, 20),
    (NOW - timedelta(minutes=58), 12, 18),
    (NOW - timedelta(minutes=63), 15, 15),
]


def _features(target=datetime(2026, 7, 1, 11, 0), history=HISTORY):
    return build_features(ARTIFACT, 42, to_utc(target), NOW, history, 14.0, 70).iloc[0]


class TestPredictFeatures:

    def test_naive_target_is_dublin_local_time(self):
        """11:00 Dublin = 10:00 UTC in summer: two hours ahead of 08:00 UTC."""
        row = _features()
        assert row["horizon_min"] == 120
        assert row["hour"] == 11
        assert row["day_of_week"] == 2 and row["is_weekend"] == 0

    def test_current_state_and_trend_from_history(self):
        row = _features()
        assert row["bikes_now"] == 10 and row["capacity"] == 30
        assert row["trend_1h"] == 10 - 15          # value as of 07:00 is the 06:57 reading

    def test_usual_level_now_and_at_target_with_fallback(self):
        row = _features()
        assert row["profile_now"] == 6.0 and row["profile_target"] == 3.0
        assert _features(target=datetime(2026, 7, 1, 15, 0))["profile_target"] == 7.0

    def test_stale_history_counts_as_unknown(self):
        old = [(NOW - timedelta(hours=2), 10, 20)]
        row = _features(history=old)
        assert math.isnan(row["bikes_now"]) and math.isnan(row["trend_1h"])

    def test_horizon_is_clamped(self):
        assert _features(target=datetime(2026, 7, 1, 9, 0))["horizon_min"] == MIN_HORIZON_MIN
        assert _features(target=datetime(2026, 7, 9, 9, 0))["horizon_min"] == MAX_HORIZON_MIN

    def test_features_passed_to_model_and_result_clipped_to_capacity(self):
        captured = {}
        def fake_predict(df):
            captured["columns"] = list(df.columns)
            return [99.0]

        m = MagicMock()
        m.predict.side_effect = fake_predict
        with patch("src.ml.occupancy_model._load_model", return_value={**ARTIFACT, "model": m}):
            bikes = predict(42, datetime(2026, 7, 1, 11, 0), 14.0, 70, history=HISTORY, now=NOW)
        assert captured["columns"] == FEATURES
        assert bikes == 30

    @pytest.mark.parametrize("target, history, expected", [
        (datetime(2026, 7, 1, 9, 30), HISTORY, 10),          # 30 min ahead: current count
        (datetime(2026, 7, 1, 10, 0), HISTORY, 10),          # 60 min: still current count
        (datetime(2026, 7, 1, 11, 0), HISTORY, 4),           # 2 h: the model
        (datetime(2026, 7, 1, 9, 30), [(NOW - timedelta(hours=2), 10, 20)], 4),   # count unknown
    ])
    def test_current_count_up_to_the_persistence_horizon(self, target, history, expected):
        m = MagicMock()
        m.predict.return_value = [4.0]
        artifact = {**ARTIFACT, "model": m, "persistence_up_to_min": 60}
        with patch("src.ml.occupancy_model._load_model", return_value=artifact):
            assert predict(42, target, 14.0, 70, history=history, now=NOW) == expected


# ── Integration tests ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from app import app as flask_app
    from src.db import init_db, Station, StationStatus, WeatherReport, Weather
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    flask_app.config["TESTING"] = True
    flask_app.config["JWT_SECRET_KEY"] = "test-secret"

    engine = create_engine("sqlite:///:memory:", echo=False)
    init_db(engine)

    with Session(engine) as s:
        s.add(Station(station_id=42, name="DAME STREET", contract="dublin",
                      latitude=53.3445, longitude=-6.2666))
        s.flush()
        now = datetime.now(timezone.utc)
        s.add(StationStatus(station_id=42, avail_bikes=5, avail_bike_stands=10,
                            status="OPEN", update_time=now))
        s.add(Weather(id=800, main="Clear", description="clear sky", icon="01d"))
        s.flush()
        s.add(WeatherReport(update_time=now, temp=12.0, feels_like=10.0,
                            humidity=75, wind_speed=3.5, visibility=10000,
                            weather_id=800))
        s.commit()

    flask_app.extensions["engine"] = engine

    with flask_app.test_client() as c:
        yield c


def _fake_predict_fn(*args, **kwargs):
    return 8


def test_successful_prediction_returns_200(client):
    with patch("src.routes.prediction_routes.predict", _fake_predict_fn):
        res = client.get("/api/predict?station_id=42")
    assert res.status_code == 200
    data = res.get_json()
    assert data["station_id"] == 42
    assert data["station_name"] == "DAME STREET"
    assert "predicted_bikes" in data
    assert data["predicted_bikes"] >= 0
    assert "weather" in data


