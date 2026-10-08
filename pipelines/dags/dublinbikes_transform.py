"""Hourly: copy MySQL into the warehouse, then rebuild and test the dbt models.

    sync_to_warehouse ──► dbt_build ──► dbt_source_freshness

`dbt build` runs seeds, models and tests in dependency order; a failing test
fails the task (and stops downstream models), so bad data never reaches marts silently.
"""

from datetime import datetime, timedelta

from airflow.sdk import dag, task

from src.monitoring.alerts import notify_failure

DBT_PROJECT = "/opt/airflow/project/warehouse"


@dag(
    dag_id="dublinbikes_transform",
    schedule="15 * * * *",   # hourly, after the :07 forecast load
    start_date=datetime(2026, 10, 1),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "dublinbikes",
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
        "execution_timeout": timedelta(minutes=15),
        "on_failure_callback": notify_failure,
    },
    tags=["warehouse", "dbt"],
)
def dublinbikes_transform():

    @task
    def sync_to_warehouse() -> dict:
        from src.warehouse.sync import run
        return run()

    @task.bash(cwd=DBT_PROJECT, env={"DBT_PROFILES_DIR": DBT_PROJECT}, append_env=True)
    def dbt_build() -> str:
        return "$DBT_BIN build --no-use-colors"

    # Runs even if the build failed: a stalled sync is often *why* it failed.
    # Sequential, not parallel — both commands write to the same target/ dir.
    @task.bash(cwd=DBT_PROJECT, env={"DBT_PROFILES_DIR": DBT_PROJECT}, append_env=True,
               trigger_rule="all_done")
    def dbt_source_freshness() -> str:
        return "$DBT_BIN source freshness --no-use-colors"

    sync_to_warehouse() >> dbt_build() >> dbt_source_freshness()


dublinbikes_transform()
