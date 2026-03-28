"""
Tests for /api/auth/register and /api/auth/login endpoints.
Run with:  pytest tests/test_auth.py -v
"""
import pytest
from app import app as flask_app
from src.db import init_db
from sqlalchemy import create_engine


@pytest.fixture(scope="module")
def client():
    """Flask test client backed by an in-memory SQLite database."""
    flask_app.config["TESTING"] = True
    flask_app.config["JWT_SECRET_KEY"] = "test-secret"

    # Swap to SQLite so tests never touch the real MySQL DB
    from sqlalchemy import create_engine
    engine = create_engine("sqlite:///:memory:", echo=False)
    init_db(engine)
    flask_app.extensions["engine"] = engine

    with flask_app.test_client() as c:
        yield c


# ── Registration ──────────────────────────────────────────────────────────────

def test_register_success(client):
    res = client.post("/api/auth/register", json={
        "email": "alice@example.com",
        "password": "password123",
        "name": "Alice"
    })
    assert res.status_code in (200, 201)
    data = res.get_json()
    assert "token" in data
    assert data["name"] == "Alice"


def test_register_duplicate_email(client):
    client.post("/api/auth/register", json={
        "email": "bob@example.com", "password": "pw", "name": "Bob"
    })
    res = client.post("/api/auth/register", json={
        "email": "bob@example.com", "password": "other", "name": "Bob2"
    })
    assert res.status_code in (400, 409)


def test_register_missing_fields(client):
    res = client.post("/api/auth/register", json={"email": "x@x.com"})
    assert res.status_code == 400


# ── Login ─────────────────────────────────────────────────────────────────────

def test_login_success(client):
    client.post("/api/auth/register", json={
        "email": "carol@example.com", "password": "secret", "name": "Carol"
    })
    res = client.post("/api/auth/login", json={
        "email": "carol@example.com", "password": "secret"
    })
    assert res.status_code == 200
    assert "token" in res.get_json()


def test_login_wrong_password(client):
    client.post("/api/auth/register", json={
        "email": "dave@example.com", "password": "correct", "name": "Dave"
    })
    res = client.post("/api/auth/login", json={
        "email": "dave@example.com", "password": "wrong"
    })
    assert res.status_code == 401


def test_login_unknown_email(client):
    res = client.post("/api/auth/login", json={
        "email": "nobody@example.com", "password": "pw"
    })
    assert res.status_code == 401
