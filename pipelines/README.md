# Pipelines (Airflow)

Four DAGs. The two ingestion DAGs replace the sleep-loop scripts in `src/tasks/`;
`dublinbikes_transform` builds the analytics warehouse (see [warehouse/README.md](../warehouse/README.md));
`dublinbikes_monitor` checks that data is still arriving.

```
dublinbikes_ingest (every 5 min)
  extract_bikes    ──► load_bikes      JCDecaux    → data/raw/bikes/date=YYYY-MM-DD/*.json   → station, station_status
  extract_weather  ──► load_weather    OpenWeather → data/raw/weather_current/...            → weather_report

dublinbikes_forecast (hourly, :07)
  extract_forecast ──► load_forecast   OpenWeather → data/raw/weather_forecast/...           → weather_forecast

dublinbikes_transform (hourly, :15)
  sync_to_warehouse ──► dbt_build ──► dbt_source_freshness
                                       MySQL → Postgres warehouse.raw → staging → marts (+ tests)

dublinbikes_monitor (every 10 min)
  check_ingestion_health               MySQL: newest snapshot ≤ 15 min, weather ≤ 60 min, ≥ 100 stations reporting
```

## Design

- **Raw first.** Extract tasks only call the API and archive the JSON; load tasks read the archived file.
  A failed load retries without re-calling the API, and any archived day can be replayed.
- **Idempotent loads.** Every table is keyed on the source's own timestamp and written with upserts, so
  re-running a load or polling unchanged data adds no rows:

  | Table | Key | Source of the key |
  |---|---|---|
  | `station_status` | `(station_id, update_time)` | JCDecaux `last_update` |
  | `station` | `station_id` | JCDecaux `number` (also refreshes `bike_stands`) |
  | `weather_report` | `update_time` | OpenWeather `dt` (observation time) |
  | `weather_forecast` | `forecast_time` | OpenWeather forecast `dt`; keeps the latest forecast per time |

  Every forecast vintage is still in `data/raw/weather_forecast/`, so the table only keeps the latest.

## Data quality and alerts

| Layer | Check | When | On failure |
|---|---|---|---|
| Ingestion (MySQL) | newest snapshot ≤ 15 min old, newest weather ≤ 60 min, ≥ 100 stations reported in 30 min | every 10 min | e-mail |
| Warehouse sources | `dbt source freshness`: snapshots warn > 2 h / error > 6 h | hourly | e-mail |
| Warehouse models | `dbt build`: keys, relationships, accepted values, business rules | hourly | e-mail listing the failed tests; downstream marts are skipped, so bad rows never reach them |

Business rules (error): bikes and docks ≥ 0; bikes + docks ≤ capacity; capacity > 0; station inside Dublin;
weather within Dublin's plausible range. Warning only: more than a quarter of a station's docks unusable in the
last 24 h (broken or blocked docks — e.g. YORK STREET WEST had 20 of 40).

Every task in every DAG has `on_failure_callback=notify_failure` ([src/monitoring/alerts.py](../src/monitoring/alerts.py)),
sent once retries are exhausted. Configure with the `SMTP_*` / `ALERT_EMAIL_TO` variables in `.env`:

- **Local:** `docker compose --profile mail up -d` starts [Mailpit](https://mailpit.axllent.org/); alerts appear at http://localhost:8025.
- **Real e-mail (Gmail):** enable 2-step verification, create an *app password*, then set
  `SMTP_HOST=smtp.gmail.com SMTP_PORT=587 SMTP_STARTTLS=true SMTP_USER=<you>@gmail.com SMTP_PASSWORD=<app password> ALERT_EMAIL_TO=<you>@gmail.com`.

With `SMTP_HOST` unset, alerts are only written to the task log.

## Run locally

```bash
cd pipelines
cp .env.example .env        # fill in JCDECAUX_API_KEY and OPENWEATHER_API_KEY
docker compose up -d --build
```

Open http://localhost:8080 (airflow / airflow) and unpause the four `dublinbikes_*` DAGs (new DAGs start paused).

The stack includes a project MySQL (`bike_app`, host port **3307**, root / `bikes`) seeded from `dump.sql`
on first start, and Postgres (host port **5433**) holding both the Airflow metadata and the `warehouse`
database (user / password `warehouse`). Both ports are bound to 127.0.0.1 only.

On every start, `airflow-init` runs two idempotent setup steps (no-ops once applied):
`python -m src.warehouse.setup` creates the warehouse role, database and `raw` schema if missing, and
`python -m src.db.cli migrate` applies the MySQL migrations:

- **001** dedupes `station_status`, adds its unique key and `station.bike_stands`.
  On the seeded dump: 1,132 duplicate snapshots removed (1,840 → 708 rows, 61.5% duplicates).
- **002** moves forecasts out of `weather_report` into `weather_forecast`. Forecasts had been stored as
  `weather_report` rows with future timestamps, so `get_latest_weather()` — used by `/api/predict` and the
  route planner — returned a forecast ~5 days ahead (on the dump: 2026-04-18 18:00 while the newest
  observation was 2026-04-13 20:46). On the seeded dump: 96 → 9 `weather_report` rows (80 were forecasts,
  7 duplicate observations); 80 forecast rows → 63 distinct forecast times.

To use your own MySQL instead, set `DB_URL` to `...@host.docker.internal:3306/bike_app` — inside the
container `localhost` is the container itself. To point the Flask app at the compose database, use
`DB_URL=mysql+pymysql://root:bikes@localhost:3307/bike_app`.

## Replay a raw file by hand

```bash
python -c "from src.ingest import jobs; print(jobs.load_bikes('data/raw/bikes/date=2026-10-07/bikes_090500.json'))"
```
