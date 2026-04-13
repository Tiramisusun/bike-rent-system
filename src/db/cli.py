"""CLI commands for database management."""

import click

from src.db.engine import load_engine, init_db


@click.command(name="init-db", short_help="Initialize db, create all required tables")
def init_db_click():
    engine = load_engine()
    init_db(engine)
    click.echo("DB successfully initialized.")


@click.group(name="db", short_help="DB initialization tool")
def cli():
    pass


cli.add_command(init_db_click)


if __name__ == "__main__":
    cli()
