"""Prometheus metrics: request timing, assistant counters, data freshness and dbt status."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from prometheus_client import CollectorRegistry, generate_latest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.agent.agent import AgentResult, Attempt
from src.db import Station, StationStatus, Weather, WeatherReport, init_db
from src.monitoring import metrics
from src.monitoring.metrics import DataCollector, record_agent_result


def _value(name, labels=None):
    from prometheus_client import REGISTRY
    return REGISTRY.get_sample_value(name, labels or {}) or 0


def _scrape(collector) -> str:
    registry = CollectorRegistry()
    registry.register(collector)
    return generate_latest(registry).decode()


# ── /metrics and request timing ───────────────────────────────────────────────

@pytest.fixture
def client():
    from app import app
    with app.test_client() as c:
        yield c


def test_requests_are_counted_by_route_template_not_path(client):
    status = str(client.get("/api/db/stations/1/history").status_code)
    labels = {"method": "GET", "route": "/api/db/stations/<int:station_id>/history", "status": status}
    before = _value("http_requests_total", labels)
    for station_id in (1, 2):
        client.get(f"/api/db/stations/{station_id}/history")
    assert _value("http_requests_total", labels) - before == 2
    assert 'route="/api/db/stations/1/history"' not in client.get("/metrics").get_data(as_text=True)


def test_metrics_endpoint_serves_prometheus_text_and_is_not_counted(client):
    res = client.get("/metrics")
    body = res.get_data(as_text=True)
    assert res.status_code == 200 and res.mimetype == "text/plain"
    assert "http_request_duration_seconds" in body and "agent_questions_total" in body
    assert 'route="/metrics"' not in body


# ── Assistant ─────────────────────────────────────────────────────────────────

def _result(**kw):
    base = dict(question="q", answer="a", latency_s=3.0, prompt_tokens=4000, cached_prompt_tokens=3000,
                completion_tokens=100, reasoning_tokens=0, attempts=[Attempt(sql="s", ok=True)], grounded=True)
    return AgentResult(**{**base, **kw})


@pytest.mark.parametrize("kw, outcome", [
    ({}, "grounded"),
    ({"grounded": False, "attempts": []}, "ungrounded"),
    ({"error": "APIConnectionError: x"}, "error"),
    ({"error": "AgentTimeout: x", "timed_out": True}, "timeout"),
])
def test_assistant_outcome_is_recorded(kw, outcome):
    before = _value("agent_questions_total", {"outcome": outcome})
    record_agent_result(_result(**kw))
    assert _value("agent_questions_total", {"outcome": outcome}) - before == 1


def test_assistant_tokens_and_cost_at_list_price(monkeypatch):
    monkeypatch.setenv("LLM_PRICE", '{"input": 1.0, "cached_input": 0.1, "output": 5.0}')
    cost, cached = _value("agent_cost_usd_total"), _value("agent_tokens_total", {"kind": "cached_prompt"})
    record_agent_result(_result())
    assert _value("agent_cost_usd_total") - cost == pytest.approx((1000 * 1.0 + 3000 * 0.1 + 100 * 5.0) / 1e6)
    assert _value("agent_tokens_total", {"kind": "cached_prompt"}) - cached == 3000


def test_no_price_means_no_cost(monkeypatch):
    monkeypatch.delenv("LLM_PRICE", raising=False)
    cost = _value("agent_cost_usd_total")
    record_agent_result(_result())
    assert _value("agent_cost_usd_total") == cost


# ── Data freshness and dbt ────────────────────────────────────────────────────

def _engine(snapshot_age_min=3, n_stations=110):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    with Session(engine) as s:
        s.add(Weather(id=800, main="Clear", description="clear sky", icon="01d"))
        for i in range(1, n_stations + 1):
            s.add(Station(station_id=i, contract="dublin", name=f"S{i}", latitude=53.35, longitude=-6.26))
            s.add(StationStatus(station_id=i, update_time=now - timedelta(minutes=snapshot_age_min),
                                avail_bikes=5, avail_bike_stands=15, status="OPEN"))
        s.add(WeatherReport(update_time=now - timedelta(minutes=10), temp=11, feels_like=9, visibility=10000,
                            wind_speed=4, humidity=80, weather_id=800))
        s.commit()
    return engine


def _sample(text, name):
    line = next(l for l in text.splitlines() if l.startswith(name + " ") or l.startswith(name + "{"))
    return float(line.rsplit(" ", 1)[1])


def test_freshness_gauges(tmp_path):
    text = _scrape(DataCollector(_engine(snapshot_age_min=20, n_stations=40), dbt_target=tmp_path))
    assert _sample(text, "dublinbikes_data_scrape_ok") == 1
    assert 19 * 60 < _sample(text, "dublinbikes_latest_snapshot_age_seconds") < 21 * 60
    assert _sample(text, "dublinbikes_stations_reporting") == 40


def test_database_down_reports_scrape_failure_instead_of_erroring(tmp_path):
    broken = create_engine("sqlite:///:memory:")                        # no tables
    text = _scrape(DataCollector(broken, dbt_target=tmp_path))
    assert _sample(text, "dublinbikes_data_scrape_ok") == 0
    assert "dublinbikes_latest_snapshot_age_seconds" not in text


def test_dbt_results_by_status(tmp_path):
    (tmp_path / "run_results.json").write_text(json.dumps({
        "metadata": {"generated_at": "2026-10-27T21:15:03.123456Z"},
        "results": [{"status": "success"}, {"status": "pass"}, {"status": "pass"}, {"status": "fail"}],
    }))
    text = _scrape(DataCollector(_engine(), dbt_target=tmp_path))
    assert _sample(text, 'dbt_nodes{status="pass"}') == 2
    assert _sample(text, 'dbt_nodes{status="fail"}') == 1
    assert _sample(text, "dbt_last_build_timestamp_seconds") == pytest.approx(
        datetime(2026, 10, 27, 21, 15, 3, 123456, tzinfo=timezone.utc).timestamp())
