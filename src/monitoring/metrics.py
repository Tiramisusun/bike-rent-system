"""Prometheus metrics for the web app: HTTP traffic, the assistant, and data freshness.

Served at /metrics. Prometheus scrapes it over the internal Docker network; Traefik
answers 403 for /metrics on the public side. Data-freshness numbers are computed at
scrape time from the same measurements the monitor DAG checks (checks.measure), and
the dbt results are read from the last `dbt build` / `dbt source freshness` artifacts.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, g, request
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Counter, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily

from src.extensions import limiter
from src.monitoring.alerts import DBT_TARGET

HTTP_REQUESTS = Counter(
    "http_requests_total", "HTTP requests by route and status.", ["method", "route", "status"])
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request latency by route.", ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60))

AGENT_QUESTIONS = Counter(
    "agent_questions_total",
    "Questions to the assistant by outcome: grounded (answer backed by a query in that turn), "
    "ungrounded (incl. declined), timeout, error.", ["outcome"])
AGENT_LATENCY = Histogram(
    "agent_question_duration_seconds", "Time to answer one question, all model calls included.",
    buckets=(1, 2, 3, 5, 8, 13, 20, 30, 45, 60, 90))
AGENT_TOKENS = Counter(
    "agent_tokens_total", "LLM tokens: prompt (incl. cached_prompt), completion (incl. reasoning).", ["kind"])
AGENT_SQL = Counter("agent_sql_attempts_total", "SQL queries the assistant tried, by result.", ["result"])
AGENT_COST = Counter(
    "agent_cost_usd_total", "Assistant cost at list prices (LLM_PRICE); 0 when no price is set.")


def llm_price() -> dict | None:
    """LLM_PRICE: USD per 1M tokens as JSON, e.g. {"input": 0.1, "cached_input": 0.01, "output": 0.5}."""
    raw = os.getenv("LLM_PRICE", "").strip()
    return json.loads(raw) if raw else None


def record_agent_result(result) -> None:
    from src.agent.evaluation import cost_usd
    outcome = ("timeout" if result.timed_out else "error" if result.error
               else "grounded" if result.grounded else "ungrounded")
    AGENT_QUESTIONS.labels(outcome).inc()
    AGENT_LATENCY.observe(result.latency_s)
    for kind, n in (("prompt", result.prompt_tokens), ("cached_prompt", result.cached_prompt_tokens),
                    ("completion", result.completion_tokens), ("reasoning", result.reasoning_tokens)):
        AGENT_TOKENS.labels(kind).inc(n)
    for attempt in result.attempts:
        AGENT_SQL.labels("ok" if attempt.ok else "failed").inc()
    price = llm_price()
    if price:
        AGENT_COST.inc(cost_usd(result.prompt_tokens, result.cached_prompt_tokens,
                                result.completion_tokens, price))


class DataCollector:
    """Data freshness and dbt status, measured when Prometheus scrapes."""

    def __init__(self, engine, dbt_target: Path = DBT_TARGET):
        self.engine, self.dbt_target = engine, dbt_target

    def collect(self):
        from src.monitoring.checks import measure
        ok = GaugeMetricFamily("dublinbikes_data_scrape_ok", "1 if the freshness query worked.")
        try:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            m = measure(self.engine, now)
        except Exception:                        # DB down: say so, don't break /metrics
            ok.add_metric([], 0)
            yield ok
        else:
            ok.add_metric([], 1)
            yield ok
            for name, latest in (("snapshot", m.latest_snapshot), ("weather", m.latest_weather)):
                if latest is not None:
                    yield GaugeMetricFamily(
                        f"dublinbikes_latest_{name}_age_seconds",
                        f"Seconds since the newest {name} row in MySQL.",
                        value=(now - latest).total_seconds())
            yield GaugeMetricFamily(
                "dublinbikes_stations_reporting",
                f"Stations with a snapshot in the last {m.active_window_min} minutes.",
                value=m.active_stations)
        yield from self._dbt()

    def _dbt(self):
        status = GaugeMetricFamily(
            "dbt_nodes", "Nodes (models, tests, seeds) in the last dbt build, by status.", labels=["status"])
        try:
            run = json.loads((self.dbt_target / "run_results.json").read_text())
        except (OSError, ValueError):
            return
        counts = {}
        for r in run.get("results", []):
            counts[r.get("status", "unknown")] = counts.get(r.get("status", "unknown"), 0) + 1
        for s, n in counts.items():
            status.add_metric([s], n)
        yield status
        generated = run.get("metadata", {}).get("generated_at")
        if generated:
            ts = datetime.fromisoformat(generated.replace("Z", "+00:00")).timestamp()
            yield GaugeMetricFamily("dbt_last_build_timestamp_seconds",
                                    "When the last dbt build finished (Unix time).", value=ts)


_registered_data_collector = False


def init_metrics(app: Flask, engine) -> None:
    """Time every request and serve /metrics."""
    global _registered_data_collector
    if not _registered_data_collector:          # the registry is process-wide
        REGISTRY.register(DataCollector(engine))
        _registered_data_collector = True

    @app.before_request
    def _start_timer():
        g._metrics_start = time.perf_counter()

    @app.after_request
    def _record(response):
        start = getattr(g, "_metrics_start", None)
        if start is not None and request.path != "/metrics":
            # The route template, not the path: /api/db/stations/<id>/history is one series.
            route = request.url_rule.rule if request.url_rule else "unmatched"
            HTTP_REQUESTS.labels(request.method, route, str(response.status_code)).inc()
            HTTP_LATENCY.labels(request.method, route).observe(time.perf_counter() - start)
        return response

    @app.route("/metrics")
    @limiter.exempt
    def metrics():
        return Response(generate_latest(REGISTRY), mimetype=CONTENT_TYPE_LATEST)
