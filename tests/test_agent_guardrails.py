import pytest

from src.agent.guardrails import MAX_ROWS, UnsafeSQL, validate_sql

TABLES = {"dim_station", "fct_station_snapshot", "mart_station_kpis"}


def ok(sql):
    return validate_sql(sql, TABLES)


# ── Allowed ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sql", [
    "SELECT station_name FROM marts.dim_station",
    "select station_name, empty_minutes from marts.mart_station_kpis order by empty_minutes desc limit 5",
    "WITH busy AS (SELECT station_id FROM marts.fct_station_snapshot WHERE is_empty) "
    "SELECT d.station_name FROM busy JOIN marts.dim_station d USING (station_id)",
    "SELECT zone, count(*) FROM marts.dim_station GROUP BY zone HAVING count(*) > 3;",
    "SELECT station_id FROM marts.dim_station UNION SELECT station_id FROM marts.mart_station_kpis",
    "SELECT round(avg(empty_minutes)::numeric, 1) FROM marts.mart_station_kpis",
])
def test_read_only_queries_on_marts_pass(sql):
    assert ok(sql)


def test_missing_limit_is_added():
    assert ok("SELECT * FROM marts.dim_station").endswith(f"LIMIT {MAX_ROWS}")


def test_small_limit_is_kept():
    assert ok("SELECT * FROM marts.dim_station LIMIT 5").endswith("LIMIT 5")


def test_large_limit_is_capped():
    assert ok("SELECT * FROM marts.dim_station LIMIT 100000").endswith(f"LIMIT {MAX_ROWS}")


def test_union_is_wrapped_and_capped():
    out = ok("SELECT station_id FROM marts.dim_station UNION SELECT station_id FROM marts.mart_station_kpis")
    assert out.startswith("SELECT * FROM (") and out.endswith(f"LIMIT {MAX_ROWS}")


# ── Rejected ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sql, reason", [
    ("DROP TABLE marts.dim_station", "SELECT"),
    ("DELETE FROM marts.dim_station", "SELECT"),
    ("UPDATE marts.dim_station SET capacity = 0", "SELECT"),
    ("INSERT INTO marts.dim_station (station_id) VALUES (1)", "SELECT"),
    ("TRUNCATE marts.dim_station", "SELECT"),
    ("SELECT 1; DROP TABLE marts.dim_station", "single statement"),
    ("SELECT * INTO marts.copy FROM marts.dim_station", "INTO"),
    ("WITH gone AS (DELETE FROM marts.dim_station RETURNING *) SELECT * FROM gone", "DELETE"),
    ("SELECT * FROM marts.dim_station FOR UPDATE", "LOCK"),
    ("SELECT pg_sleep(30)", "pg_sleep"),
    ("SELECT pg_read_file('/etc/passwd')", "pg_read_file"),
    ("SELECT set_config('statement_timeout', '0', false)", "set_config"),
    ("SELECT version()", "version"),
    ("SET statement_timeout = 0", "SELECT"),
    ("COPY marts.dim_station TO '/tmp/x'", "SELECT"),
    ("GRANT SELECT ON marts.dim_station TO public", "SELECT"),
    ("EXPLAIN ANALYZE SELECT * FROM marts.dim_station", "SELECT"),
    ("SELECT * FROM raw.station_status", "not available"),
    ("SELECT * FROM staging.stg_station", "not available"),
    ("SELECT * FROM information_schema.tables", "not available"),
    ("SELECT * FROM pg_catalog.pg_user", "not available"),
    ("SELECT * FROM dim_station", "not available"),               # unqualified, not a CTE
    ("SELECT * FROM marts.secret_table", "not available"),
    ("SELECT email, password_hash FROM public.user", "not available"),
    ("", "Empty"),
    ("this is not sql", "SELECT"),
])
def test_unsafe_queries_are_rejected(sql, reason):
    with pytest.raises(UnsafeSQL) as e:
        ok(sql)
    assert reason.lower() in str(e.value).lower()


def test_rejection_lists_available_tables():
    with pytest.raises(UnsafeSQL) as e:
        ok("SELECT * FROM raw.station")
    assert "marts.dim_station" in str(e.value)
