import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.db import Station, StationStatus, Weather, WeatherReport, init_db
from src.monitoring import alerts
from src.monitoring.checks import IngestionUnhealthy, assert_healthy, run_checks

NOW = datetime(2026, 10, 8, 9, 0)


def _engine(n_stations=110, snapshot_age=timedelta(minutes=3), weather_age=timedelta(minutes=10)):
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    with Session(engine) as s:
        s.add(Weather(id=800, main="Clear", description="clear sky", icon="01d"))
        for i in range(1, n_stations + 1):
            s.add(Station(station_id=i, contract="dublin", name=f"S{i}", latitude=53.35, longitude=-6.26))
            s.add(StationStatus(station_id=i, update_time=NOW - snapshot_age,
                                avail_bikes=5, avail_bike_stands=15, status="OPEN"))
        s.add(WeatherReport(update_time=NOW - weather_age, temp=11, feels_like=9, visibility=10000,
                            wind_speed=4, humidity=80, weather_id=800))
        s.commit()
    return engine


def _by_name(results):
    return {r.name: r for r in results}


# ── Ingestion checks ──────────────────────────────────────────────────────────

def test_healthy_ingestion_passes_all_checks():
    results = run_checks(_engine(), now=NOW)
    assert all(r.ok for r in results), [r.detail for r in results]


def test_stale_snapshots_fail_the_15_minute_sla():
    r = _by_name(run_checks(_engine(snapshot_age=timedelta(minutes=16)), now=NOW))
    assert not r["station_snapshots_fresh"].ok
    assert "16 min old" in r["station_snapshots_fresh"].detail


def test_partial_feed_fails_even_when_fresh():
    r = _by_name(run_checks(_engine(n_stations=40), now=NOW))
    assert r["station_snapshots_fresh"].ok
    assert not r["stations_reporting"].ok


def test_empty_database_fails_with_no_data():
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    r = _by_name(run_checks(engine, now=NOW))
    assert not r["station_snapshots_fresh"].ok and "no data" in r["station_snapshots_fresh"].detail
    assert not r["weather_fresh"].ok


def test_thresholds_are_configurable(monkeypatch):
    monkeypatch.setenv("MONITOR_MAX_SNAPSHOT_AGE_MIN", "30")
    r = _by_name(run_checks(_engine(snapshot_age=timedelta(minutes=20)), now=NOW))
    assert r["station_snapshots_fresh"].ok


def test_assert_healthy_raises_with_every_check_listed():
    with pytest.raises(IngestionUnhealthy) as exc:
        assert_healthy(_engine(snapshot_age=timedelta(hours=8)))
    msg = str(exc.value)
    assert "[FAIL] station_snapshots_fresh" in msg and "weather_fresh" in msg


# ── E-mail alerts ─────────────────────────────────────────────────────────────

class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout):
        self.host, self.port, self.calls = host, port, []

    def __enter__(self): return self
    def __exit__(self, *a): pass
    def starttls(self): self.calls.append("starttls")
    def login(self, user, pw): self.calls.append(("login", user))
    def send_message(self, msg): FakeSMTP.sent.append((self, msg))


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setattr(alerts.smtplib, "SMTP", FakeSMTP)
    for k, v in {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "587", "SMTP_USER": "bot@example.com",
                 "SMTP_PASSWORD": "pw", "ALERT_EMAIL_TO": "me@example.com"}.items():
        monkeypatch.setenv(k, v)
    return FakeSMTP


def test_unconfigured_alert_is_logged_not_sent(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("ALERT_EMAIL_TO", raising=False)
    assert alerts.send_email("s", "b") is False


def test_alert_sent_over_starttls_with_login(smtp):
    assert alerts.send_email("subject", "body") is True
    conn, msg = smtp.sent[0]
    assert conn.calls == ["starttls", ("login", "bot@example.com")]
    assert msg["To"] == "me@example.com" and msg["From"] == "bot@example.com"


def test_local_relay_without_tls_or_login(smtp, monkeypatch):
    monkeypatch.setenv("SMTP_STARTTLS", "false")
    monkeypatch.delenv("SMTP_USER")
    alerts.send_email("s", "b")
    assert smtp.sent[0][0].calls == []


def _ctx(task_id, exc="boom"):
    ti = SimpleNamespace(dag_id="dublinbikes_transform", task_id=task_id,
                         run_id="scheduled__2026-10-08T09:15:00+00:00", try_number=2)
    return {"ti": ti, "exception": exc}


def test_failure_message_lists_failed_dbt_tests(tmp_path, monkeypatch):
    (tmp_path / "run_results.json").write_text(json.dumps({"results": [
        {"unique_id": "test.dublinbikes.snapshot_within_capacity", "status": "fail", "failures": 3,
         "message": "Got 3 results, configured to fail if != 0"},
        {"unique_id": "model.dublinbikes.dim_station", "status": "success"},
    ]}))
    monkeypatch.setattr(alerts, "DBT_TARGET", tmp_path)
    subject, body = alerts.build_failure_message(_ctx("dbt_build"))
    assert subject == "[dublinbikes] dublinbikes_transform.dbt_build failed"
    assert "snapshot_within_capacity: fail (3 rows)" in body
    assert "dim_station" not in body
    assert "/dags/dublinbikes_transform/runs/" in body


def test_failure_message_for_stale_sources(tmp_path, monkeypatch):
    (tmp_path / "sources.json").write_text(json.dumps({"results": [
        {"unique_id": "source.dublinbikes.raw.station_status", "status": "error",
         "max_loaded_at_time_ago_in_s": 28000},
    ]}))
    monkeypatch.setattr(alerts, "DBT_TARGET", tmp_path)
    _, body = alerts.build_failure_message(_ctx("dbt_source_freshness"))
    assert "raw.station_status: error — last loaded 7.8 h ago" in body


def test_notify_failure_never_raises(monkeypatch):
    monkeypatch.setattr(alerts, "send_email", lambda *a: (_ for _ in ()).throw(OSError("smtp down")))
    alerts.notify_failure(_ctx("load_bikes"))   # must not raise
