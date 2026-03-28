"""
Tests for rental endpoints: start, end, active, history.
Run with:  pytest tests/test_rental.py -v
"""
import pytest
from datetime import datetime, timezone
from app import app as flask_app
from src.db import init_db, Station, StationStatus, Address
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture(scope="module")
def client():
    flask_app.config["TESTING"] = True
    flask_app.config["JWT_SECRET_KEY"] = "test-secret"

    engine = create_engine("sqlite:///:memory:", echo=False)
    init_db(engine)

    # Seed two stations with available bikes/stands
    with Session(engine) as s:
        st1 = Station(station_id=1, name="STATION A", contract="dublin",
                      latitude=53.34, longitude=-6.26)
        st2 = Station(station_id=2, name="STATION B", contract="dublin",
                      latitude=53.35, longitude=-6.27)
        s.add_all([st1, st2])
        s.flush()
        s.add(Address(station_id=1, street1="Addr A"))
        s.add(Address(station_id=2, street1="Addr B"))
        s.flush()
        now = datetime.now(timezone.utc)
        s.add(StationStatus(station_id=1, avail_bikes=5, avail_bike_stands=10,
                            status="OPEN", update_time=now))
        s.add(StationStatus(station_id=2, avail_bikes=3, avail_bike_stands=8,
                            status="OPEN", update_time=now))
        s.commit()

    flask_app.extensions["engine"] = engine

    with flask_app.test_client() as c:
        yield c


def _register_and_token(client, email="user@test.com"):
    client.post("/api/auth/register", json={
        "email": email, "password": "pw", "name": "Test"
    })
    res = client.post("/api/auth/login", json={"email": email, "password": "pw"})
    return res.get_json()["token"]


# ── Start rental ──────────────────────────────────────────────────────────────

def test_start_rental_success(client):
    token = _register_and_token(client, "start@test.com")
    res = client.post("/api/rental/start",
                      json={"station_id": 1},
                      headers={"Authorization": f"Bearer {token}"})
    assert res.status_code in (200, 201)
    data = res.get_json()
    assert "rental_id" in data
    assert data["pickup_station"] == "STATION A"


def test_start_rental_requires_auth(client):
    res = client.post("/api/rental/start", json={"station_id": 1})
    assert res.status_code == 401


def test_cannot_start_two_rentals(client):
    token = _register_and_token(client, "double@test.com")
    client.post("/api/rental/start", json={"station_id": 1},
                headers={"Authorization": f"Bearer {token}"})
    res = client.post("/api/rental/start", json={"station_id": 2},
                      headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 400


# ── Active rental ─────────────────────────────────────────────────────────────

def test_active_rental(client):
    token = _register_and_token(client, "active@test.com")
    client.post("/api/rental/start", json={"station_id": 1},
                headers={"Authorization": f"Bearer {token}"})
    res = client.get("/api/rental/active",
                     headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.get_json()["active"] is not None


def test_no_active_rental(client):
    token = _register_and_token(client, "noactive@test.com")
    res = client.get("/api/rental/active",
                     headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.get_json()["active"] is None


# ── End rental & cost ─────────────────────────────────────────────────────────

def test_end_rental_success(client):
    token = _register_and_token(client, "end@test.com")
    client.post("/api/rental/start", json={"station_id": 1},
                headers={"Authorization": f"Bearer {token}"})
    res = client.post("/api/rental/end", json={"station_id": 2},
                      headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.get_json()
    assert "cost_eur" in data
    assert "duration_minutes" in data


def test_end_rental_no_active(client):
    token = _register_and_token(client, "noend@test.com")
    res = client.post("/api/rental/end", json={"station_id": 2},
                      headers={"Authorization": f"Bearer {token}"})
    assert res.status_code in (400, 404)


# ── History ───────────────────────────────────────────────────────────────────

def test_rental_history(client):
    token = _register_and_token(client, "history@test.com")
    client.post("/api/rental/start", json={"station_id": 1},
                headers={"Authorization": f"Bearer {token}"})
    client.post("/api/rental/end", json={"station_id": 2},
                headers={"Authorization": f"Bearer {token}"})
    res = client.get("/api/rental/history",
                     headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert len(res.get_json()["rentals"]) == 1
