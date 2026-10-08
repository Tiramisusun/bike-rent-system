"""Every 10 minutes: is ingestion data still arriving? (15-minute freshness SLA)

Checks MySQL directly — the warehouse is only synced hourly, too slow for this.
A failing check fails the task, which e-mails an alert via notify_failure.
"""

from datetime import datetime, timedelta

from airflow.sdk import dag, task

from src.monitoring.alerts import notify_failure


@dag(
    dag_id="dublinbikes_monitor",
    schedule="*/10 * * * *",
    start_date=datetime(2026, 10, 1),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "dublinbikes",
        "retries": 0,                         # a failed check is the signal, not a flake
        "execution_timeout": timedelta(minutes=2),
        "on_failure_callback": notify_failure,
    },
    tags=["monitoring"],
)
def dublinbikes_monitor():

    @task
    def check_ingestion_health() -> list[str]:
        from src.monitoring.checks import assert_healthy
        return assert_healthy()

    check_ingestion_health()


dublinbikes_monitor()
