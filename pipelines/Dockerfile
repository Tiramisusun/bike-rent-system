# Airflow image + the extra libs the project's src/ package needs.
# Airflow 3.3 already ships SQLAlchemy 2.x, requests and psycopg2, so src/ imports cleanly.
FROM apache/airflow:3.3.2

RUN PY=$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")') && \
    pip install --no-cache-dir \
      --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-${PY}.txt" \
      pymysql python-dotenv

# dbt lives in its own virtualenv: its dependency pins clash with Airflow's.
RUN python -m venv /home/airflow/dbt-venv && \
    /home/airflow/dbt-venv/bin/pip install --no-cache-dir dbt-core==1.12.5 dbt-postgres==1.11.0
ENV DBT_BIN=/home/airflow/dbt-venv/bin/dbt
