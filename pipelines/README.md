# Pipelines (Airflow)

Three DAGs. The two ingestion DAGs replace the sleep-loop scripts in `src/tasks/`;
`dublinbikes_transform` builds the analytics warehouse (see [warehouse/README.md](../warehouse/README.md)).

```
dublinbikes_ingest (every 5 min)
  extract_bikes    ──► load_bikes      JCDecaux    → data/raw/bikes/date=YYYY-MM-DD/*.json   → station, station_status
  extract_weather  ──► load_weather    OpenWeather → data/raw/weather_current/...            → weather_report

dublinbikes_forecast (hourly, :07)
  extract_forecast ──► load_forecast   OpenWeather → data/raw/weather_forecast/...           → weather_forecast

dublinbikes_transform (hourly, :15)
  sync_to_warehouse ──► dbt_build      MySQL → Postgres warehouse.raw → staging → marts (+ tests)
```

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

## Run locally

```bash
cd pipelines
cp .env.example .env        # fill in JCDECAUX_API_KEY and OPENWEATHER_API_KEY
docker compose up -d --build
```

Open http://localhost:8080 (airflow / airflow), unpause `dublinbikes_ingest`.

The stack includes a project MySQL (`bike_app`, host port **3307**, root / `bikes`) seeded from `dump.sql`
on first start, and Postgres (host port **5433**) holding both the Airflow metadata and the `warehouse`
database (user / password `warehouse`). Both ports are bound to 127.0.0.1 only. `airflow-init` also runs
`python -m src.warehouse.setup`, which creates the warehouse role, database and `raw` schema if missing. `airflow-init` runs `python -m src.db.cli migrate` on every start (a no-op once applied):

- **001** dedupes `station_status`, adds its unique key and `station.bike_stands`.
  On the seeded dump: 1,132 duplicate snapshots removed (1,840 → 708 rows, 61.5% duplicates).
- **002** moves forecasts out of `weather_report` into `weather_forecast`. Forecasts had been stored as
  `weather_report` rows with future timestamps, so `get_latest_weather()` — used by `/api/predict` and the
  route planner — returned a forecast ~5 days ahead. On the seeded data: 221 → 14 `weather_report` rows
  (200 were forecasts, 7 duplicate observations); 200 forecast rows → 103 distinct forecast times.

To use your own MySQL instead, set `DB_URL` to `...@host.docker.internal:3306/bike_app` — inside the
container `localhost` is the container itself. To point the Flask app at the compose database, use
`DB_URL=mysql+pymysql://root:bikes@localhost:3307/bike_app`.

## Replay a raw file by hand

```bash
python -c "from src.ingest import jobs; print(jobs.load_bikes('data/raw/bikes/date=2026-10-07/bikes_090500.json'))"
```
