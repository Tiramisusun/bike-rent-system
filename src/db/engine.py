"""Database engine creation and table initialisation."""

import logging
import os

import pymysql
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from src.db.models import Base

logger = logging.getLogger(__name__)


def load_engine() -> Engine:
    """Load and return a SQLAlchemy engine from DB_URL in .env."""
    try:
        assert load_dotenv(), "Could not load .env variables."
        db_url = os.getenv("DB_URL")
        assert db_url, "Could not find required DB_URL."
        return create_engine(db_url)
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
