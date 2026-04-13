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
    from src.db import init_db, Station, StationStatus, Address
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
        s.add(Address(station_id=42, street1="Smithfield North"))
        s.flush()
        s.add(StationStatus(station_id=42, avail_bikes=5, avail_bike_stands=10,
                            status="OPEN", update_time=datetime.now(timezone.utc)))
        s.commit()

    flask_app.extensions["engine"] = engine
    with flask_app.test_client() as c:
        yield c


def test_api_bikes_success(client, bike_dynamic_data):
    """/api/bikes returns source, count and data when JCDecaux call succeeds."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = [bike_dynamic_data]
    mock_resp.raise_for_status.return_value = None

    with patch("src.services.bikes_service.requests.get", return_value=mock_resp):
        res = client.get("/api/bikes")

    assert res.status_code == 200
    data = res.get_json()
    assert data["source"] == "jcdecaux"
    assert data["count"] == 1
    assert isinstance(data["data"], list)


def test_api_db_stations_returns_list(client):
    """/api/db/stations returns stations seeded in the test DB."""
    res = client.get("/api/db/stations")
    assert res.status_code == 200
    body = res.get_json()
    assert body["source"] == "database"
    assert body["count"] >= 1
