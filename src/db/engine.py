"""Database engine creation and table initialisation."""

import logging
import os

import pymysql
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from src.db.models import Base

logger = logging.getLogger(__name__)

# The engine the web app uses. app.py sets it once at startup; tests swap in
# an in-memory SQLite engine with set_engine().
_engine: Engine | None = None


def set_engine(engine: Engine) -> None:
    """Set the engine returned by get_engine()."""
    global _engine
    _engine = engine


def get_engine() -> Engine:
    """Return the engine set by set_engine()."""
    if _engine is None:
        raise RuntimeError("Database engine not set; call set_engine() first.")
    return _engine


def load_engine() -> Engine:
    """Load and return a SQLAlchemy engine from DB_URL (env var or .env)."""
    try:
        load_dotenv()  # optional: in Docker/Airflow DB_URL comes from the environment
        db_url = os.getenv("DB_URL")
        assert db_url, "Could not find required DB_URL."
        return create_engine(db_url, pool_pre_ping=True)
    except Exception as e:
        logger.error(f"Failed to load SQL engine: {e}")
        raise


def init_db(engine: Engine) -> None:
    """Create database and all tables if they do not exist."""
    try:
        url = engine.url
        conn = pymysql.connect(
            host=url.host,
            port=url.port or 3306,
            user=url.username,
            password=url.password,
        )
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{url.database}`")
        conn.close()

        Base.metadata.create_all(engine)
        logger.info(f"Initialized {len(Base.metadata.tables)} tables.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
