"""
Tests for ML prediction endpoints and core prediction logic.

Unit tests:   calculate_cost, predict() feature building
Integration:  GET /api/predict, GET /api/predict/all

Run with:  pytest tests/test_prediction.py -v
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from src.routes.rental_routes import calculate_cost
from src.ml.occupancy_model import predict, FEATURES


# ── Unit tests: pricing ───────────────────────────────────────────────────────

class TestCalculateCost:

    def test_free_within_30_minutes(self):
        assert calculate_cost(30) == 0.0

    def test_three_blocks_at_91_minutes(self):
        # 91 min = 30 free + 61 billable → 3 blocks (rounded up) → €1.50
        assert calculate_cost(91) == 1.50


# ── Unit tests: feature engineering ──────────────────────────────────────────

class TestPredictFeatures:

    def test_rush_hour_morning(self):
        """hour=8 should produce rush_hour=1 and is_morning_peak=1."""
        captured = {}
        def fake_predict(df):
            captured["rush_hour"] = df["rush_hour"].iloc[0]
            captured["is_morning_peak"] = df["is_morning_peak"].iloc[0]
            return [5.0]

        m = MagicMock()
        m.predict.side_effect = fake_predict
        with patch("src.ml.occupancy_model._load_model", return_value=m):
            predict(1, datetime(2024, 12, 15, 8, 0, tzinfo=timezone.utc),
                    53.34, -6.26, 12.0, 75)
        assert captured["rush_hour"] == 1
        assert captured["is_morning_peak"] == 1

    def test_lag_features_from_recent_bikes(self):
        captured = {}
        def fake_predict(df):
            captured["lag_1"] = df["lag_1"].iloc[0]
            captured["lag_2"] = df["lag_2"].iloc[0]
            captured["rolling_mean_3"] = df["rolling_mean_3"].iloc[0]
            return [5.0]

        m = MagicMock()
        m.predict.side_effect = fake_predict
        recent = [10, 8, 6, 4, 2]  # newest first
        with patch("src.ml.occupancy_model._load_model", return_value=m):
            predict(1, datetime(2024, 12, 15, 9, 0, tzinfo=timezone.utc),
                    53.34, -6.26, 12.0, 75, recent_bikes=recent)
        assert captured["lag_1"] == 10.0
        assert captured["lag_2"] == 8.0
        assert abs(captured["rolling_mean_3"] - (10 + 8 + 6) / 3) < 1e-9

    def test_missing_lag_falls_back_to_zero(self):
        captured = {}
        def fake_predict(df):
            captured["lag_24"] = df["lag_24"].iloc[0]
            captured["lag_168"] = df["lag_168"].iloc[0]
            return [5.0]

        m = MagicMock()
        m.predict.side_effect = fake_predict
        with patch("src.ml.occupancy_model._load_model", return_value=m):
            predict(1, datetime(2024, 12, 15, 9, 0, tzinfo=timezone.utc),
                    53.34, -6.26, 12.0, 75, recent_bikes=[5, 4, 3])
        assert captured["lag_24"] == 0.0
        assert captured["lag_168"] == 0.0


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


def test_predict_all_contains_bikes_and_docks(client):
    with patch("src.routes.prediction_routes.predict", _fake_predict_fn):
        res = client.get("/api/predict/all")
    assert res.status_code == 200
    pred = res.get_json()["predictions"][0]
    assert "predicted_bikes" in pred
    assert "predicted_docks" in pred
    assert pred["predicted_bikes"] >= 0
    assert pred["predicted_docks"] >= 0
