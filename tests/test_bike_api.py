"""
Tests for bike service and /api/bikes, /api/db/stations endpoints.
Run with:  pytest tests/test_bike_api.py -v

Strategy: mock requests.get so no real HTTP calls are made.
Fixture data comes from test_db.py.
"""
import pytest
from unittest.mock import patch, MagicMock
from tests.test_db import bike_dynamic_data  # reuse existing fixture


# ── Service layer tests ───────────────────────────────────────────────────────

class TestFetchJcdecauxStations:

    def test_returns_list_on_success(self, bike_dynamic_data):
        """Service returns parsed JSON list when API call succeeds."""
        from src.services.bikes_service import fetch_jcdecaux_stations

        mock_resp = MagicMock()
        mock_resp.json.return_value = [bike_dynamic_data]
        mock_resp.raise_for_status.return_value = None

        with patch("src.services.bikes_service.requests.get", return_value=mock_resp):
            result = fetch_jcdecaux_stations()

        assert isinstance(result, list)
        assert len(result) == 1

    def test_raises_on_http_error(self):
        """Service raises RequestException when API returns an error status."""
        import requests as req
        from src.services.bikes_service import fetch_jcdecaux_stations

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req.HTTPError("503 Service Unavailable")

        with patch("src.services.bikes_service.requests.get", return_value=mock_resp):
            with pytest.raises(req.HTTPError):
                fetch_jcdecaux_stations()


# ── Response data format tests ────────────────────────────────────────────────

class TestBikeDataFormat:

    def test_station_has_required_fields(self, bike_dynamic_data):
        """JCDecaux station object contains all expected keys."""
        required = {"number", "name", "address", "position", "status",
                    "totalStands", "mainStands"}
        assert required.issubset(bike_dynamic_data.keys())

    def test_availability_fields_are_non_negative(self, bike_dynamic_data):
        avail = bike_dynamic_data["totalStands"]["availabilities"]
        assert avail["bikes"] >= 0
        assert avail["stands"] >= 0


# ── API endpoint tests ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from app import app as flask_app
    from src.db import init_db, Station, StationStatus
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from datetime import datetime, timezone

    flask_app.config["TESTING"] = True
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)

    with Session(engine) as s:
        s.add(Station(station_id=42, name="SMITHFIELD NORTH",
                      contract="dublin", latitude=53.3495, longitude=-6.2781))
        s.flush()
        s.add(StationStatus(station_id=42, avail_bikes=5, avail_bike_stands=10,
                            status="OPEN", update_time=datetime.now(timezone.utc)))
        s.commit()

    flask_app.extensions["engine"] = engine
    with flask_app.test_client() as c:
        yield c


# ── /api/bikes: served from the pipeline's latest snapshot ───────────────────

@pytest.fixture
def bikes_app():
    """Fresh in-memory DB per test, swapped into the app and restored afterwards."""
    from app import app as flask_app
    from src.db import init_db
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    original = flask_app.extensions["engine"]
    flask_app.extensions["engine"] = engine
    with flask_app.test_client() as c:
        yield c, engine
    flask_app.extensions["engine"] = original


def _seed_snapshot(engine, station_id, age, bikes=5):
    from datetime import datetime, timedelta, timezone
    from sqlalchemy.orm import Session
    from src.db import Station, StationStatus
    with Session(engine) as s:
        if not s.get(Station, station_id):
            s.add(Station(station_id=station_id, name=f"S{station_id}", contract="dublin",
                          latitude=53.35, longitude=-6.26, bike_stands=20))
        s.add(StationStatus(station_id=station_id, avail_bikes=bikes, avail_bike_stands=20 - bikes,
                            status="OPEN",
                            update_time=datetime.now(timezone.utc).replace(tzinfo=None) - age))
        s.commit()


def _status_rows(engine):
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session
    from src.db import StationStatus
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(StationStatus))


def test_api_bikes_fresh_snapshot_served_from_db_without_calling_jcdecaux(bikes_app):
    from datetime import timedelta
    client, engine = bikes_app
    _seed_snapshot(engine, 42, age=timedelta(minutes=2), bikes=7)

    with patch("src.services.bikes_service.requests.get") as live:
        res = client.get("/api/bikes")

    live.assert_not_called()
    body = res.get_json()
    assert res.status_code == 200
    assert body["source"] == "database" and body["stale"] is False
    station = body["data"][0]
    # same shape as the JCDecaux payload the frontend reads
    assert station["number"] == 42
    assert station["available_bikes"] == 7
    assert station["position"] == {"lat": 53.35, "lng": -6.26}
    assert isinstance(station["last_update"], int)


def test_api_bikes_drops_stations_missing_from_feed(bikes_app):
    from datetime import timedelta
    client, engine = bikes_app
    _seed_snapshot(engine, 42, age=timedelta(minutes=2))
    _seed_snapshot(engine, 30, age=timedelta(days=3))     # gone from the live feed

    body = client.get("/api/bikes").get_json()
    assert [s["number"] for s in body["data"]] == [42]


def test_api_bikes_stale_snapshot_falls_back_to_jcdecaux_without_writing(bikes_app, bike_dynamic_data):
    from datetime import timedelta
    client, engine = bikes_app
    _seed_snapshot(engine, 42, age=timedelta(hours=1))
    mock_resp = MagicMock()
    mock_resp.json.return_value = [bike_dynamic_data]
    mock_resp.raise_for_status.return_value = None

    with patch("src.services.bikes_service.requests.get", return_value=mock_resp):
        body = client.get("/api/bikes").get_json()

    assert body["source"] == "jcdecaux"
    assert body["count"] == 1
    assert _status_rows(engine) == 1        # page loads never write


def test_api_bikes_stale_snapshot_and_jcdecaux_down_returns_stale_data(bikes_app):
    import requests as req
    from datetime import timedelta
    client, engine = bikes_app
    _seed_snapshot(engine, 42, age=timedelta(hours=1))

    with patch("src.services.bikes_service.requests.get", side_effect=req.ConnectionError("down")):
        res = client.get("/api/bikes")

    body = res.get_json()
    assert res.status_code == 200
    assert body["source"] == "database" and body["stale"] is True
    assert body["count"] == 1


def test_api_bikes_no_data_and_jcdecaux_down_returns_502(bikes_app):
    import requests as req
    client, _ = bikes_app
    with patch("src.services.bikes_service.requests.get", side_effect=req.ConnectionError("down")):
        res = client.get("/api/bikes")
    assert res.status_code == 502


def test_api_db_stations_returns_list(client):
    """/api/db/stations returns stations seeded in the test DB."""
    res = client.get("/api/db/stations")
    assert res.status_code == 200
    body = res.get_json()
    assert body["source"] == "database"
    assert body["count"] >= 1
