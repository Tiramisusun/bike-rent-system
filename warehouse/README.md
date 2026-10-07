# Warehouse (dbt + Postgres)

The analytics layer. `dublinbikes_transform` (hourly, :15) copies the MySQL tables into
Postgres and runs `dbt build`:

```
MySQL bike_app ──sync_to_warehouse──► warehouse.raw ──dbt──► staging ──► intermediate ──► marts
```

| Schema | Contents |
|---|---|
| `raw` | Copies of the operational tables (`src/warehouse/sync.py`). `user` is not copied — it holds e-mails and password hashes. |
| `staging` | One view per source table: renamed columns, UTC + Dublin local timestamps. |
| `intermediate` | `int_station_snapshot_enriched`: how long each snapshot lasted, plus the weather at the time. |
| `marts` | Star schema and shared metrics (below). |
| `reference` | Seeds: Irish public holidays 2026–2027. |

## Marts

| Model | Grain |
|---|---|
| `dim_station` | station — name, location, capacity, `zone` (distance to O'Connell Bridge) |
| `dim_time` | local hour — weekday, weekend, public holiday, peak hour |
| `dim_weather` | OpenWeather condition code — group, `is_precipitation` |
| `fct_station_snapshot` | station × snapshot (~5 min) — bikes, docks, empty/full, weather |
| `fct_rental` | rental |
| `agg_station_hourly` | station × local hour — empty/full minutes, averages |
| `mart_station_kpis` | station — the standard metrics |

### Metric definitions

Defined once in `agg_station_hourly` / `mart_station_kpis`; descriptions live in `models/marts/_marts.yml`.

| Metric | Definition |
|---|---|
| Empty minutes | Minutes the station was open with 0 bikes |
| Full minutes | Minutes the station was open with 0 free docks |
| Peak shortage rate | Share of peak-hour minutes (working days, 07–09 and 16–19 local) spent empty |
| Rain bike delta | Avg bikes in hours with precipitation − avg bikes in dry hours |

A snapshot counts for the time until the station's next snapshot, capped at 30 minutes
(`max_snapshot_minutes`) so collection outages aren't counted as empty/full time.

## Run locally

```bash
cd warehouse
export WAREHOUSE_HOST=localhost WAREHOUSE_PORT=5433 DBT_PROFILES_DIR=$PWD
dbt build                  # seeds, models and tests in dependency order
dbt docs generate && dbt docs serve   # browsable docs + lineage graph
```

Inside Docker: `docker compose exec airflow-scheduler bash -c 'cd /opt/airflow/project/warehouse && $DBT_BIN build'`.
