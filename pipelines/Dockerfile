# Airflow image + the extra libs the project's src/ package needs.
# Airflow 3.3 already ships SQLAlchemy 2.x and requests, so src/ imports cleanly.
FROM apache/airflow:3.3.2

RUN PY=$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")') && \
    pip install --no-cache-dir \
      --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-${PY}.txt" \
      pymysql python-dotenv
