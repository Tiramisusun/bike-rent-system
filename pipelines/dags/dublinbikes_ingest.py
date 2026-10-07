"""JCDecaux + OpenWeather -> raw JSON archive -> idempotent MySQL load.

dublinbikes_ingest    every 5 min : station availability + current weather
dublinbikes_forecast  hourly      : 5-day / 3-hourly forecast (OpenWeather refreshes it every 3 h)

Replaces the old sleep-loop scripts in src/tasks/. Each source is two tasks so a
failed load can be retried (or replayed later) from the archived file without
calling the API again.
"""

from datetime import datetime, timedelta

from airflow.sdk import dag, task

default_args = {
    "owner": "dublinbikes",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "execution_timeout": timedelta(minutes=3),
}


@dag(
    dag_id="dublinbikes_ingest",
    schedule="*/5 * * * *",
    start_date=datetime(2026, 10, 1),
    catchup=False,           # live APIs can't be backfilled; replay from raw/ instead
    max_active_runs=1,
    default_args=default_args,
    tags=["ingest", "bikes", "weather"],
)
def dublinbikes_ingest():
    # Imports stay inside tasks so DAG parsing doesn't need a DB connection.

    @task
    def extract_bikes() -> str:
        from src.ingest import jobs
        return jobs.extract_bikes()

    @task
    def load_bikes(path: str) -> dict:
        from src.ingest import jobs
        return jobs.load_bikes(path)

    @task
    def extract_weather() -> str:
        from src.ingest import jobs
        return jobs.extract_weather()

    @task
    def load_weather(path: str) -> None:
        from src.ingest import jobs
        jobs.load_weather(path)

    load_bikes(extract_bikes())
    load_weather(extract_weather())


dublinbikes_ingest()


@dag(
    dag_id="dublinbikes_forecast",
    schedule="7 * * * *",    # hourly, offset from the 5-minute runs
    start_date=datetime(2026, 10, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["ingest", "weather"],
)
def dublinbikes_forecast():

    @task
    def extract_forecast() -> str:
        from src.ingest import jobs
        return jobs.extract_forecast()

    @task
    def load_forecast(path: str) -> int:
        from src.ingest import jobs
        return jobs.load_forecast(path)

    load_forecast(extract_forecast())


dublinbikes_forecast()
