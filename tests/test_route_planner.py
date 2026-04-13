"""
Tests for the route planner service (unit) and /api/plan endpoint (integration).
Run with:  pytest tests/test_route_planner.py -v
"""
import pytest
from unittest.mock import patch, MagicMock
from src.services.route_planner_service import _haversine, _mins


# ── Pure unit tests (no DB, no HTTP) ─────────────────────────────────────────

class TestHaversine:
    def test_same_point_is_zero(self):
        assert _haversine(53.34, -6.26, 53.34, -6.26) == 0.0

    def test_known_distance(self):
        # Grafton St to Trinity College — roughly 300 m
        d = _haversine(53.3410, -6.2605, 53.3453, -6.2593)
        assert 200 < d < 500

    def test_symmetry(self):
        d1 = _haversine(53.34, -6.26, 53.35, -6.27)
        d2 = _haversine(53.35, -6.27, 53.34, -6.26)
        assert abs(d1 - d2) < 0.01


class TestMins:
    def test_one_minute(self):
        assert _mins(60) == 1.0

    def test_rounding(self):
        assert _mins(90) == 1.5


# ── Integration: /api/plan endpoint ──────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from app import app as flask_app
    from src.db import init_db, Station, StationStatus, Address
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from datetime import datetime, timezone

    flask_app.config["TESTING"] = True
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)

    with Session(engine) as s:
        s.add(Station(station_id=10, name="GRAFTON ST", contract="dublin",
                      latitude=53.3410, longitude=-6.2605))
        s.add(Station(station_id=11, name="TRINITY", contract="dublin",
                      latitude=53.3453, longitude=-6.2593))
        s.flush()
        s.add(Address(station_id=10, street1="Grafton Street"))
        s.add(Address(station_id=11, street1="Trinity College"))
        s.flush()
        now = datetime.now(timezone.utc)
        s.add(StationStatus(station_id=10, avail_bikes=8, avail_bike_stands=5,
                            status="OPEN", update_time=now))
        s.add(StationStatus(station_id=11, avail_bikes=3, avail_bike_stands=10,
                            status="OPEN", update_time=now))
        s.commit()

    flask_app.extensions["engine"] = engine
    with flask_app.test_client() as c:
        yield c


def test_plan_missing_params(client):
    res = client.get("/api/plan?start_lat=53.34&start_lng=-6.26")
    assert res.status_code == 400


def test_plan_returns_result(client):
    # Patch OSRM so the test never makes real HTTP calls
    mock_leg = MagicMock()
    mock_leg.seconds = 300
    mock_leg.coords = [[53.34, -6.26], [53.35, -6.27]]

    with patch("src.services.route_planner_service._osrm_multi_leg", return_value=mock_leg):
        res = client.get("/api/plan?start_lat=53.341&start_lng=-6.260"
                         "&end_lat=53.345&end_lng=-6.259")
    assert res.status_code == 200
    data = res.get_json()
    assert data["mode"] in ("bike", "walk_only")


def test_plan_walk_only_when_no_stations(client):
    mock_leg = MagicMock()
    mock_leg.seconds = 600
    mock_leg.coords = [[53.0, -6.0], [53.1, -6.1]]

    with patch("src.services.route_planner_service._osrm_multi_leg", return_value=mock_leg):
        # Far from any station
        res = client.get("/api/plan?start_lat=52.0&start_lng=-7.0"
                         "&end_lat=52.1&end_lng=-7.1")
    assert res.status_code == 200
    assert res.get_json()["mode"] == "walk_only"


def test_plan_with_waypoints(client):
    mock_leg = MagicMock()
    mock_leg.seconds = 300
    mock_leg.coords = [[53.34, -6.26], [53.35, -6.27]]

    with patch("src.services.route_planner_service._osrm_multi_leg", return_value=mock_leg):
        res = client.get("/api/plan?start_lat=53.341&start_lng=-6.260"
                         "&end_lat=53.345&end_lng=-6.259"
                         "&waypoints=53.342,-6.261")
    assert res.status_code == 200
