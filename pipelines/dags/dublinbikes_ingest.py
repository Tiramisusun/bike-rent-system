"""JCDecaux + OpenWeather -> raw JSON archive -> idempotent MySQL load.

dublinbikes_ingest    every 5 min : station availability + current weather
dublinbikes_forecast  hourly      : 5-day / 3-hourly forecast (OpenWeather refreshes it every 3 h)

Replaces the old sleep-loop scripts in src/tasks/. Each source is two tasks so a
failed load can be retried (or replayed later) from the archived file without
calling the API again.
"""

from datetime import datetime, timedelta

from airflow.sdk import dag, task

from src.monitoring.alerts import notify_failure

default_args = {
    "owner": "dublinbikes",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "execution_timeout": timedelta(minutes=3),
    "on_failure_callback": notify_failure,   # e-mail once retries are exhausted
}


@dag( #告诉airflow，下面的函数不是普通函数而是一条流水线定义
    dag_id="dublinbikes_ingest",
    schedule="*/5 * * * *", #这是crontab的写法，5个位置分别是分钟小时日月星期几
    start_date=datetime(2026, 10, 1),
    catchup=False,           # live APIs can't be backfilled; replay from raw/ instead
    max_active_runs=1,
    default_args=default_args,
    tags=["ingest", "bikes", "weather"],
)
def dublinbikes_ingest(): #airflow有一个进程会每隔几十秒就把这个文件读一遍，看看流水线有没有变化。如果把
    #from src.ingest import jobs写在文件开头，每读一次就要加载一次数据库相关的代码，数据库连不上时还会导致整个文件解析失败。
    #所以真正干活的代码都放到任务内部再导入
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
