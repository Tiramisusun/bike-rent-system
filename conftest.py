"""
Root conftest — patches MySQL-specific init before any test imports app modules.
"""
import os
from unittest.mock import patch, MagicMock

import pytest

# Set env vars BEFORE app.py is imported so load_dotenv(override=False) keeps them
os.environ["DB_URL"] = "sqlite:///:memory:"
os.environ["JWT_SECRET_KEY"] = "test-secret-not-for-production-0123456789"
os.environ["FLASK_DEBUG"] = "0"   # a developer .env with FLASK_DEBUG=1 must not leak into tests
os.environ["JCDECAUX_API_KEY"] = "test"
os.environ["JCDECAUX_CONTRACT_NAME"] = "dublin"
os.environ["OPENWEATHER_API_KEY"] = "test"
os.environ["CITY_NAME"] = "Dublin,IE"

# Patch init_db to skip the pymysql.connect call (not needed for SQLite)
import src.db as _db
from sqlalchemy.orm import declarative_base

_original_init_db = _db.init_db

def _sqlite_safe_init_db(engine):
    """Skip the MySQL-specific CREATE DATABASE step; just create tables."""
    _db.Base.metadata.create_all(engine)

_db.init_db = _sqlite_safe_init_db


@pytest.fixture(autouse=True)
def _rate_limits_off():
    """Many tests log in and register from the same client IP; limits are switched
    off per test and re-enabled by the tests that check them (limits_on)."""
    import app  # noqa: F401  — make sure limiter.init_app has run first
    from src.extensions import limiter
    limiter.enabled = False
    yield
