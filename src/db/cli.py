"""CLI commands for database management."""

import click
from sqlalchemy import inspect, text

from src.db.engine import load_engine, init_db


@click.command(name="init-db", short_help="Initialize db, create all required tables")
def init_db_click():
    engine = load_engine()
    init_db(engine)
    click.echo("DB successfully initialized.")


@click.command(name="migrate", short_help="Apply schema migrations to an existing MySQL db")
def migrate_click():
    """Idempotent version of the SQL files in sql/migrations/ (001, 002)."""
    engine = load_engine()
    init_db(engine)  # create any missing tables first (no-op for existing ones)
    insp = inspect(engine)
    with engine.begin() as conn:
        uniques = {u["name"] for u in insp.get_unique_constraints("station_status")}
        if "uq_station_status_station_time" not in uniques:
            removed = conn.execute(text(
                "DELETE s1 FROM station_status s1 JOIN station_status s2 "
                "ON s1.station_id = s2.station_id AND s1.update_time = s2.update_time "
                "AND s1.id > s2.id"
            )).rowcount
            click.echo(f"Removed {removed} duplicate station_status rows.")
            conn.execute(text(
                "ALTER TABLE station_status ADD CONSTRAINT uq_station_status_station_time "
                "UNIQUE (station_id, update_time)"
            ))
            click.echo("Added unique constraint (station_id, update_time).")

        columns = {c["name"] for c in insp.get_columns("station")}
        if "bike_stands" not in columns:
            conn.execute(text("ALTER TABLE station ADD COLUMN bike_stands INT NULL"))
            click.echo("Added station.bike_stands.")

        # 002: forecasts move out of weather_report into weather_forecast.
        if insp.has_table("forecast"):
            moved = conn.execute(text(
                # latest legacy row per forecast time; rows already written by the
                # new loader (fetched_at NOT NULL) are newer and win (no-op update)
                "INSERT INTO weather_forecast "
                "(forecast_time, fetched_at, temp, feels_like, humidity, wind_speed, visibility, weather_id) "
                "SELECT update_time, NULL, temp, feels_like, humidity, wind_speed, visibility, weather_id "
                "FROM (SELECT r.*, ROW_NUMBER() OVER (PARTITION BY r.update_time ORDER BY r.id DESC) rn "
                "      FROM forecast f JOIN weather_report r ON r.id = f.report) x "
                "WHERE rn = 1 "
                "ON DUPLICATE KEY UPDATE forecast_time = forecast_time"
            )).rowcount
            conn.execute(text(
                "CREATE TEMPORARY TABLE legacy_forecast_reports AS SELECT DISTINCT report AS id FROM forecast"
            ))
            conn.execute(text("DROP TABLE forecast"))
            removed = conn.execute(text(
                "DELETE FROM weather_report WHERE id IN (SELECT id FROM legacy_forecast_reports)"
            )).rowcount
            click.echo(f"Moved {moved} forecasts to weather_forecast; "
                       f"removed {removed} forecast rows from weather_report; dropped forecast.")

        uniques = {u["name"] for u in insp.get_unique_constraints("weather_report")}
        if "uq_weather_report_time" not in uniques:
            removed = conn.execute(text(
                "DELETE w1 FROM weather_report w1 JOIN weather_report w2 "
                "ON w1.update_time = w2.update_time AND w1.id > w2.id"
            )).rowcount
            click.echo(f"Removed {removed} duplicate weather_report rows.")
            conn.execute(text(
                "ALTER TABLE weather_report ADD CONSTRAINT uq_weather_report_time UNIQUE (update_time)"
            ))
            click.echo("Added unique constraint weather_report(update_time).")
    click.echo("Migrations up to date.")


@click.group(name="db", short_help="DB initialization tool")
def cli():
    pass


cli.add_command(init_db_click)
cli.add_command(migrate_click)


if __name__ == "__main__":
    cli()
