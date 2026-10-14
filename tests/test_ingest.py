from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from src.db import (
    Station, StationStatus, WeatherForecast, WeatherReport,
    db_from_request, get_latest_weather, init_db, store_forecast_data,
)
from src.ingest import jobs
from src.ingest.raw_archive import fetched_at_from_path, load_raw, raw_path, save_raw


def _make_engine():
    engine = create_engine("sqlite:///:memory:", echo=False)
    init_db(engine)
    return engine


def _count(engine, model):
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(model))


@pytest.fixture
def jcdecaux_payload():
    """Two stations in the shape returned by the JCDecaux /stations endpoint."""
    return [
        {
            "number": 42, "contract_name": "dublin", "name": "SMITHFIELD NORTH",
            "position": {"lat": 53.349562, "lng": -6.278198},
            "bike_stands": 30, "available_bikes": 12, "available_bike_stands": 18,
            "status": "OPEN", "last_update": 1775865600000,
        },
        {
            "number": 30, "contract_name": "dublin", "name": "PARNELL SQUARE NORTH",
            "position": {"lat": 53.353741, "lng": -6.265301},
            "bike_stands": 20, "available_bikes": 0, "available_bike_stands": 20,
            "status": "OPEN", "last_update": 1775865660000,
        },
    ]


# ── Idempotent writes ─────────────────────────────────────────────────────────

class TestIdempotentBikeWrites:

    def test_repeated_snapshot_is_not_duplicated(self, jcdecaux_payload):
        engine = _make_engine()
        db_from_request(jcdecaux_payload, "bike-static", engine=engine)

        assert db_from_request(jcdecaux_payload, "bike-dynamic", engine=engine) == 2
        assert db_from_request(jcdecaux_payload, "bike-dynamic", engine=engine) == 0
        assert _count(engine, StationStatus) == 2

    def test_new_update_time_is_inserted(self, jcdecaux_payload):
        engine = _make_engine()
        db_from_request(jcdecaux_payload, "bike-static", engine=engine)
        db_from_request(jcdecaux_payload, "bike-dynamic", engine=engine)

        jcdecaux_payload[0]["last_update"] += 300_000
        jcdecaux_payload[0]["available_bikes"] = 11
        assert db_from_request(jcdecaux_payload, "bike-dynamic", engine=engine) == 1
        assert _count(engine, StationStatus) == 3

    def test_snapshot_without_last_update_is_skipped(self, jcdecaux_payload):
        engine = _make_engine()
        db_from_request(jcdecaux_payload, "bike-static", engine=engine)
        jcdecaux_payload[1]["last_update"] = None
        assert db_from_request(jcdecaux_payload, "bike-dynamic", engine=engine) == 1

    def test_station_upsert_updates_bike_stands(self, jcdecaux_payload):
        engine = _make_engine()
        db_from_request(jcdecaux_payload, "bike-static", engine=engine)
        jcdecaux_payload[0]["bike_stands"] = 35
        db_from_request(jcdecaux_payload, "bike-static", engine=engine)

        assert _count(engine, Station) == 2
        with Session(engine) as s:
            assert s.get(Station, 42).bike_stands == 35


# ── Raw archive ───────────────────────────────────────────────────────────────

class TestRawArchive:

    def test_path_is_partitioned_by_date(self, tmp_path):
        ts = datetime(2026, 10, 7, 9, 5, 0, tzinfo=timezone.utc)
        assert raw_path("bikes", ts, tmp_path) == tmp_path / "bikes" / "date=2026-10-07" / "bikes_090500.json"

    def test_round_trip(self, tmp_path, jcdecaux_payload):
        path = save_raw("bikes", jcdecaux_payload, root=tmp_path)
        assert load_raw(path) == jcdecaux_payload
        assert not list(tmp_path.rglob("*.tmp"))


# ── Extract → load job ────────────────────────────────────────────────────────

class TestBikeJob:

    def test_extract_then_load_twice_is_idempotent(self, tmp_path, monkeypatch, jcdecaux_payload):
        monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path))
        engine = _make_engine()
        with patch.object(jobs, "fetch_jcdecaux_stations", return_value=jcdecaux_payload):
            path = jobs.extract_bikes()

        assert path.startswith(str(tmp_path / "bikes"))
        first = jobs.load_bikes(path, engine=engine)
        second = jobs.load_bikes(path, engine=engine)
        assert first == {"stations": 2, "new_snapshots": 2, "duplicates_skipped": 0}
        assert second == {"stations": 2, "new_snapshots": 0, "duplicates_skipped": 2}

    def test_extract_rejects_empty_response(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path))
        with patch.object(jobs, "fetch_jcdecaux_stations", return_value=[]):
            with pytest.raises(ValueError):
                jobs.extract_bikes()


# ── Weather: observations vs forecasts ────────────────────────────────────────

def _current(dt, temp):
    return {
        "dt": dt, "weather": [{"id": 500, "main": "Rain", "description": "light rain", "icon": "10d"}],
        "main": {"temp": temp, "feels_like": temp - 2, "humidity": 80},
        "wind": {"speed": 5.0}, "visibility": 10000,
    }


def _forecast_list(start_dt, temps):
    return [
        {"dt": start_dt + i * 10800,
         "weather": [{"id": 800, "main": "Clear", "description": "clear sky", "icon": "01d"}],
         "main": {"temp": t, "feels_like": t, "humidity": 60}, "wind": {"speed": 3.0}, "visibility": 10000}
        for i, t in enumerate(temps)
    ]


class TestWeatherWrites:

    def test_same_observation_is_not_duplicated(self):
        engine = _make_engine()
        db_from_request(_current(1775865600, 9.0), "weather", engine=engine)
        db_from_request(_current(1775865600, 9.0), "weather", engine=engine)
        assert _count(engine, WeatherReport) == 1

    def test_observation_time_comes_from_payload(self):
        engine = _make_engine()
        db_from_request(_current(1775865600, 9.0), "weather", engine=engine)
        assert get_latest_weather(engine)["update_time"] == "2026-04-11T00:00:00"

    def test_forecast_rerun_is_idempotent_and_keeps_latest(self):
        engine = _make_engine()
        store_forecast_data(engine, _forecast_list(1775865600, [10, 11, 12]))
        store_forecast_data(engine, _forecast_list(1775865600, [10, 11, 15]))
        assert _count(engine, WeatherForecast) == 3
        with Session(engine) as s:
            assert s.get(WeatherForecast, datetime(2026, 4, 11, 6)).temp == 15

    def test_latest_weather_is_never_a_forecast(self):
        """Regression: forecasts used to live in weather_report with future times."""
        engine = _make_engine()
        db_from_request(_current(1775865600, 9.0), "weather", engine=engine)
        store_forecast_data(engine, _forecast_list(1775865600 + 86400, [20, 21]))
        assert get_latest_weather(engine)["temp"] == 9.0


class TestForecastJob:

    def test_fetched_at_recovered_from_path(self, tmp_path):
        ts = datetime(2026, 10, 7, 21, 7, 3, tzinfo=timezone.utc)
        path = raw_path("weather_forecast", ts, tmp_path)
        assert fetched_at_from_path(path) == datetime(2026, 10, 7, 21, 7, 3)

    def test_extract_then_load_twice(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path))
        engine = _make_engine()
        payload = {"list": _forecast_list(1775865600, [10, 11, 12, 13])}
        with patch.object(jobs, "fetch_openweather_forecast", return_value=payload):
            path = jobs.extract_forecast()
        assert jobs.load_forecast(path, engine=engine) == 4
        assert jobs.load_forecast(path, engine=engine) == 4
        assert _count(engine, WeatherForecast) == 4

    def test_extract_rejects_empty_forecast(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path))
        with patch.object(jobs, "fetch_openweather_forecast", return_value={"list": []}):
            with pytest.raises(ValueError):
                jobs.extract_forecast()
