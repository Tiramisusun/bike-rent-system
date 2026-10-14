from datetime import datetime, timedelta

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from src.db import Station, StationStatus, User, init_db
from src.warehouse.sync import sync


def _engines():
    source = create_engine("sqlite:///:memory:")
    init_db(source)
    target = create_engine("sqlite:///:memory:")
    return source, target


def _seed(source, n_status=3, start_id=1):
    with Session(source) as s:
        if not s.get(Station, 1):
            s.add(Station(station_id=1, contract="dublin", name="A", latitude=53.3, longitude=-6.2, bike_stands=20))
        t0 = datetime(2026, 10, 7, 9, 0)
        for i in range(n_status):
            s.add(StationStatus(id=start_id + i, station_id=1, update_time=t0 + timedelta(minutes=5 * (start_id + i)),
                                avail_bikes=i, avail_bike_stands=20 - i, status="OPEN"))
        s.commit()


def _count(engine, table):
    with engine.connect() as c:
        return c.scalar(text(f"SELECT COUNT(*) FROM {table}"))


def test_first_sync_copies_everything():
    source, target = _engines()
    _seed(source)
    sync(source, target, schema=None)
    assert _count(target, "station") == 1
    assert _count(target, "station_status") == 3


def test_incremental_sync_only_adds_new_rows():
    source, target = _engines()
    _seed(source, n_status=3)
    sync(source, target, schema=None)
    _seed(source, n_status=2, start_id=4)
    sync(source, target, schema=None)
    assert _count(target, "station_status") == 5


def test_rerun_without_changes_is_idempotent():
    source, target = _engines()
    _seed(source)
    sync(source, target, schema=None)
    sync(source, target, schema=None)
    assert _count(target, "station") == 1
    assert _count(target, "station_status") == 3


def test_late_committed_lower_id_is_still_picked_up():
    """A row whose id is below the warehouse max id (committed late) must not be lost."""
    source, target = _engines()
    _seed(source, n_status=1, start_id=1)
    _seed(source, n_status=1, start_id=3)          # id 3 visible first
    sync(source, target, schema=None)
    _seed(source, n_status=1, start_id=2)          # id 2 commits after the sync
    sync(source, target, schema=None)
    with target.connect() as c:
        assert sorted(c.scalars(text("SELECT id FROM station_status"))) == [1, 2, 3]


def test_full_refresh_reflects_updates():
    source, target = _engines()
    _seed(source)
    sync(source, target, schema=None)
    with Session(source) as s:
        s.get(Station, 1).bike_stands = 25
        s.commit()
    sync(source, target, schema=None)
    with target.connect() as c:
        assert c.scalar(text("SELECT bike_stands FROM station")) == 25


def test_user_table_is_never_copied():
    source, target = _engines()
    with Session(source) as s:
        s.add(User(email="a@b.c", password_hash="x", name="A"))
        s.commit()
    sync(source, target, schema=None)
    assert "user" not in inspect(target).get_table_names()
