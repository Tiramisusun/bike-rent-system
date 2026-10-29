# Dublin Bikes — Data Platform & Web App

[![CI](https://github.com/Tiramisusun/bike-rent-system/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Tiramisusun/bike-rent-system/actions/workflows/ci.yml)

Real-time availability, route planning and rentals for Dublin's 115 bike-share stations, backed by a data
platform that ingests the JCDecaux and OpenWeather APIs every 5 minutes, models the data in a dbt star
schema, and alerts when data goes stale or breaks a business rule. An LLM assistant answers questions about
the data in plain English with read-only SQL.

*Python · Airflow · dbt · PostgreSQL · MySQL · Flask · React · Docker · GitHub Actions · OpenAI-compatible LLM APIs*

## Highlights

Numbers are measured, not estimated — see the linked docs and commit messages for how.

- **Found and fixed a data bug feeding user-facing features.** Forecasts were stored alongside observations, so
  "current weather" — used by the availability predictor and the rain-aware route planner — was a forecast
  ~5 days ahead. Observations and forecasts are now separate; weather lag is ≤ 15 minutes.
- **Idempotent ingestion.** 61.5% of historical station snapshots were duplicates (1,840 → 708 rows). Every
  table is now keyed on the source's own timestamp; in live running about half of each poll is unchanged data
  that is skipped instead of stored.
- **12× faster station map.** `/api/bikes` served from the latest pipeline snapshot instead of calling JCDecaux
  per page load: p50 227 ms → 18 ms, p95 460 ms → 21 ms — and the map stays up if either source is down.
- **Analytics warehouse.** MySQL → Postgres incremental sync (safe against late-committing transactions), dbt
  staging → marts with shared KPIs (empty/full-station minutes, peak-hour shortage rate) in Dublin local time
  with Irish public holidays.
- **Data quality with alerts.** 48 dbt data tests incl. capacity reconciliation, a 15-minute ingestion freshness
  SLA and e-mail alerts that name the failed check. Already caught a station with 20 of 40 docks unusable, and an
  8-hour collection gap.
- **Text-to-SQL assistant, compared across six models.** "Ask the data" turns questions into read-only SQL on the
  marts, with follow-up questions. Six models from three providers were benchmarked on 50 questions (execution
  accuracy, 3 runs each): the cheapest scored highest — `gpt-6-luna` 96.0% vs 80.0% for the model it replaced,
  at $0.09 vs $1.77 per 1,000 questions (list prices) — with no drop in German (97.3%) or Chinese (95.3%).
  None of the 15 adversarial prompts changed any table, for any model.
- **CI** on every push: unit tests, Airflow DAG integrity, a full migrate → sync → `dbt build` run against fresh
  databases, and the frontend build.

## Architecture

```mermaid
flowchart LR
    subgraph sources[External APIs]
        J[JCDecaux<br/>stations]
        O[OpenWeather<br/>current + forecast]
    end
    subgraph airflow[Airflow]
        I[dublinbikes_ingest<br/>every 5 min]
        F[dublinbikes_forecast<br/>hourly]
        T[dublinbikes_transform<br/>hourly]
        M[dublinbikes_monitor<br/>every 10 min]
    end
    RAW[(data/raw/<br/>JSON archive)]
    MY[(MySQL<br/>bike_app)]
    PG[(Postgres<br/>warehouse)]
    APP[Flask API]
    UI[React + Leaflet]
    MAIL[E-mail alerts]

    J --> I
    O --> I
    O --> F
    I --> RAW --> MY
    F --> RAW
    MY --> T --> PG
    PG -. "dbt: staging → marts + tests" .- T
    MY --> M
    M --> MAIL
    T --> MAIL
    MY --> APP --> UI
```

| Part | What it does | Docs |
|---|---|---|
| **Ingestion** (`pipelines/`, `src/ingest/`) | Extract → archive raw JSON → idempotent load into MySQL | [pipelines/README.md](pipelines/README.md) |
| **Warehouse** (`warehouse/`, `src/warehouse/`) | Sync MySQL → Postgres, dbt star schema and metrics | [warehouse/README.md](warehouse/README.md) |
| **Monitoring** (`src/monitoring/`, `monitoring/`) | Freshness checks and e-mail alerts; Prometheus metrics and Grafana dashboards | [below](#metrics-and-dashboards) |
| **Web app** (`app.py`, `src/routes/`, `frontend/`) | Map, route planning, prediction, rentals | below |
| **Assistant** (`src/agent/`, `evals/`) | Text-to-SQL agent on the marts, its benchmark and the model comparison | [below](#text-to-sql-assistant) |

## Metrics and dashboards

Prometheus scrapes four sources every 30 s; Grafana shows them on two dashboards provisioned from files in
`monitoring/grafana/dashboards/` (no clicking together in the UI). Both UIs listen on localhost only.

| Source | Metrics |
|---|---|
| Flask `/metrics` (`src/monitoring/metrics.py`) | Requests and latency per route; assistant questions by outcome, answer time, tokens (incl. cached and reasoning), list-price cost, failed SQL; age of the newest snapshot and weather row and stations reporting (the monitor DAG's measurements, taken at scrape time); dbt nodes by status and time of the last build |
| Airflow → StatsD → statsd-exporter | Task runs by DAG, task and state; DAG run duration; scheduler heartbeat; import errors |
| node-exporter, cAdvisor (production) | VPS CPU, memory, disk, network; memory and CPU per container |

The data checks still decide pass/fail (monitor DAG, dbt tests); Prometheus adds the history — when data
stopped, whether the API slowed down, what the assistant costs per day. Alerting is not set up yet.

## Web app features

1. **Live station map** — Leaflet map coloured by availability, with per-station history charts.
2. **Route planning** — recommends pickup stations within 1.5 km with more than 2 bikes and dropoff stations
   near the destination with more than 2 predicted free docks; three-leg walk/cycle/walk route with a rain alert.
3. **Availability prediction** — a Random Forest model predicts bikes at a station for a chosen time and weather.
4. **Rentals & billing** — JWT-authenticated rent/return, history and cost; first 30 minutes free, then €0.50 per
   started 30 minutes.
5. **5-day forecast** and a **How To** page for new users.
6. **Ask the data** — chat with the warehouse in plain English; every answer shows the SQL that produced it.

## Text-to-SQL assistant

A tool-calling loop (no agent framework): the model writes one `SELECT`, it is checked (sqlglot AST guardrails:
marts schema only, no writes, row cap) and run as a read-only role with a 5 s statement timeout; errors go back to
the model to fix, up to 4 queries. Schema and metric definitions come from the dbt docs. Follow-up questions
("and at peak hours?") carry the earlier turns; an answer that quotes numbers without a query in its own turn is
sent back once. Each question has a 60 s budget across all model calls.

**Model comparison** — same agent, prompt, tools and data; only the model changes
([full report](evals/MODELS.md), method in [evals/README.md](evals/README.md)):

| Model | Accuracy (3 runs, range) | German / Chinese | Median latency | Cost per 1,000 questions |
|---|---|---|---|---|
| `gpt-6-luna` (deployed) | **96.0%** (94–98) | 97.3% / 95.3% | 2.9 s | **$0.09** |
| `deepseek-v4-pro` | 91.3% (90–92) | 89.3% / 89.3% | 3.9 s | $1.51 |
| `gpt-6.1-terra` | 89.3% (88–92) | – | 3.2 s | $0.81 |
| `mimo-v2.6-pro` (previously deployed) | 80.0% (76–82) | 75.3% / 78.0% | 7.4 s | $1.77 |
| `mimo-v2.6-flash` | 78.0% (76–82) | – | 3.0 s | $0.58 |
| `deepseek-flash` | 68.7% (66–70) | – | 2.5 s | $0.44 |

- Price did not predict accuracy: the cheapest model was the most accurate, and reasoning models did not beat it.
- Runs differ by 2–6 points, so models within that range (e.g. 91.3% vs 89.3%) are not distinguishable here.
- Follow-ups: `gpt-6-luna` answered 12/12 with the conversation history (25% when asked alone), median 3.0 s;
  `mimo-v2.6-pro` 11/12, median 17.5 s.
- Moving the per-minute timestamp after the schema let the prompt cache reuse it: for `deepseek-v4-pro`
  cost per question fell 47% at 70 s between questions, accuracy unchanged; no effect for `gpt-6-luna`
  ([CACHE.md](evals/CACHE.md)).
- Costs are list prices from the providers' pricing pages, not billed amounts. The OpenAI models run without
  reasoning (their chat-completions endpoint rejects tools while reasoning is on).

```bash
python -m evals.run_eval --model gpt-luna --conditions docs --repeat 3   # models in evals/models.yaml
python -m evals.compare_models                                          # writes evals/MODELS.md
```

## Quick start

**Data platform** (Docker; Airflow UI at http://127.0.0.1:8080, login `airflow` / `airflow`; Grafana at
http://127.0.0.1:3000, login `admin` / `admin`):

```bash
cd pipelines
cp .env.example .env          # add JCDECAUX_API_KEY and OPENWEATHER_API_KEY
docker compose up -d --build  # add --profile mail to catch alert e-mails at http://127.0.0.1:8025
```

This starts Airflow, MySQL (seeded from `dump.sql`, port 3307) and Postgres (port 5433); migrations and
warehouse setup run automatically. Unpause the four `dublinbikes_*` DAGs in the UI.

**Web app** (Python 3.11+, Node 20):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# .env: DB_URL=mysql+pymysql://root:bikes@localhost:3307/bike_app plus the API keys below
python app.py                        # Flask on :5001 (5000 is taken by macOS AirPlay)

cd frontend && npm install && npm run dev   # http://localhost:5173, /api proxied to :5001
```

## Project structure

```
.
├── app.py                     # Flask entry point; serves frontend/dist in production
├── pipelines/                 # Airflow: docker-compose.yml, Dockerfile, dags/ (4 DAGs)
├── warehouse/                 # dbt project: staging, intermediate, marts, tests, seeds
├── src/
│   ├── db/                    # ORM models, readers, idempotent writers, migrations CLI
│   ├── ingest/                # extract/load jobs and the raw JSON archive
│   ├── warehouse/             # warehouse setup and MySQL → Postgres sync
│   ├── monitoring/            # ingestion health checks and e-mail alerts
│   ├── agent/                 # Text-to-SQL agent: loop, guardrails, read-only executor, semantic layer
│   ├── routes/                # Flask blueprints (bikes, weather, plan, predict, auth, rental, geocode)
│   ├── services/              # JCDecaux, OpenWeather, routing, route planner
│   ├── ml/                    # model loading and predict()
│   └── tasks/                 # legacy sleep-loop collectors, superseded by the Airflow DAGs
├── frontend/                  # React + Vite (BikeMap, RoutePlanner, PredictionWidget, AskPage, ...)
├── evals/                     # agent benchmark, adversarial and multi-turn sets, model comparison
├── sql/migrations/            # SQL equivalents of `python -m src.db.cli migrate`
├── tests/                     # pytest suite (185 tests)
├── .github/workflows/ci.yml   # CI
└── dump.sql                   # seed data for the local MySQL
```

## Machine learning

A Random Forest regressor predicts available bikes from 11 features: station and location (`station_id`,
`lat`, `lon`), time (`hour`, `month`, `year`, `day_of_week`, `rush_hour` for 07–09 and 16–19) and weather
(temperature and humidity). It is trained in a notebook on historical Dublin Bikes + weather data; the model
file (`data/best_bike_model.pkl`, path overridable with `MODEL_PATH`) is not tracked in git, and `/api/predict`
returns 503 without it. It is used by `GET /api/predict` and by the route planner to rank dropoff stations.

## API

Interactive docs (Swagger) at `/apidocs` when Flask is running.

| Endpoint | Description |
|---|---|
| `GET /api/bikes` | Current availability for all stations, from the latest pipeline snapshot; calls JCDecaux only if the snapshot is > 15 min old. Response includes `source`, `as_of`, `stale`. |
| `GET /api/db/stations` | Station metadata |
| `GET /api/db/stations/<id>/history` | Latest continuous run of snapshots for one station |
| `GET /api/weather`, `GET /api/weather/forecast` | Current weather and 5-day forecast |
| `GET /api/predict?station_id=&datetime=` | Predicted available bikes |
| `GET /api/plan/candidates`, `GET /api/plan/route` | Two-step route planning (candidate stations, then three-leg route) |
| `GET /api/plan` | Legacy single-call route planner |
| `GET /api/geocode/eircode?q=` | Eircode → coordinates (OpenCage if configured, else Nominatim) |
| `POST /api/auth/register`, `POST /api/auth/login` | Register; log in for a JWT |
| `POST /api/rental/start`, `POST /api/rental/end` | Rent / return a bike (JWT) |
| `GET /api/rental/active`, `GET /api/rental/history` | Current rental and history (JWT) |

## Configuration

Web app (`.env` in the project root):

| Variable | Required | Description |
|---|---|---|
| `DB_URL` | yes | e.g. `mysql+pymysql://root:bikes@localhost:3307/bike_app` |
| `JWT_SECRET_KEY` | yes | Secret for signing JWTs |
| `JCDECAUX_API_KEY`, `JCDECAUX_CONTRACT_NAME` | yes | JCDecaux key and contract (`dublin`) |
| `OPENWEATHER_API_KEY` | yes | OpenWeather key |
| `CITY_NAME` | yes | `Dublin,IE` — plain `Dublin` resolves to Dublin, California |
| `OPENCAGE_API_KEY` | no | Eircode geocoding (falls back to Nominatim) |
| `FORCE_BIKE_IF_AVAILABLE` | no | Always recommend cycling when stations are available (default `true`) |
| `MODEL_PATH` | no | Path to the model file |
| `PORT` | no | Flask port (default 5001) |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | no | Any OpenAI-compatible endpoint for the assistant; without a key the Ask page answers 503 |
| `LLM_REQUEST_OPTIONS` | no | JSON merged into every model call, e.g. `{"reasoning_effort":"none"}` for `gpt-6-luna` |
| `AGENT_DB_URL`, `AGENT_DAILY_BUDGET` | no | Read-only warehouse role for the assistant; site-wide daily question cap |

Pipelines, warehouse and alert settings (`SMTP_*`, `ALERT_EMAIL_TO`, `WAREHOUSE_*`) are documented in
[pipelines/.env.example](pipelines/.env.example).

## Testing

```bash
python -m pytest            # 185 tests, in-memory SQLite and scripted fake LLMs — no database or API key needed
```

| File | Tests | Covers |
|---|---|---|
| `test_agent_guardrails.py` | 37 | Read-only queries on the marts pass; writes, other schemas and unsafe functions are rejected; row cap |
| `test_agent.py` | 26 | Tool loop, error feedback, follow-up history, grounding nudge, time budget, token accounting |
| `test_agent_api.py` | 17 | `/api/agent/ask` validation, rate limits, history parsing, timeouts |
| `test_agent_evaluation.py`, `test_eval_config.py` | 13, 2 | Execution-accuracy scorer, cost per question, model and translation configs |
| `test_security.py` | 13 | JWT secret, no debug mode, login rate limits, DB-first weather, no error details leaked |
| `test_ingest.py` | 15 | Idempotent writes, raw archive, extract/load jobs, weather vs forecast split |
| `test_monitoring.py` | 12 | Freshness checks, e-mail alerts, dbt failure reporting |
| `test_bike_api.py` | 10 | `/api/bikes` from snapshot, live fallback, stale data, no writes on read |
| `test_route_planner.py` | 9 | Haversine, scoring penalties, `/api/plan` |
| `test_auth.py`, `test_db.py`, `test_prediction.py`, `test_warehouse_sync.py` | 6 each | Auth, readers, prediction, incremental sync incl. late commits |
| `test_rental.py` | 4 | Rental lifecycle and pricing |
| `test_weather_api.py` | 3 | Weather service and endpoints |

dbt data tests run with `dbt build` (see [warehouse/README.md](warehouse/README.md#tests)); CI runs everything
on each push.

## Deployment

The full Docker Compose stack runs on a VPS behind Caddy: only port 80 is public, databases and the Airflow UI
are bound to localhost (UI through an SSH tunnel), SSH is key-only. See [deploy/README.md](deploy/README.md).

## About

Started as a UCD Software Engineering module group project (2026) and completed individually by
**Xiya Sun** after teammates withdrew; the data platform was added afterwards.
