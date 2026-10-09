"""Validate LLM-generated SQL before it reaches the database.

This is one of three independent layers — none of them trusts the others:

1. Here: parse the SQL and accept only a single read-only query over the
   allowed marts tables, then cap the number of rows.
2. Database role (src/warehouse/setup.py): `agent_ro` can only SELECT from
   the marts schema, and every transaction is read-only.
3. Execution (src/agent/executor.py): statement timeout per query.

A text check like "starts with SELECT" is not enough: `SELECT ... INTO t`
creates a table, `SELECT pg_sleep(60)` ties up the database, and
`SELECT 1; DROP TABLE x` smuggles a second statement in.
"""

import sqlglot
from sqlglot import exp

MAX_ROWS = 200
ALLOWED_SCHEMA = "marts"

# Statements and clauses that write, lock or change session state, anywhere in the tree
# (a data-modifying CTE — WITH x AS (DELETE ... RETURNING *) — hides inside a SELECT).
_FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Into, exp.Create, exp.Drop,
    exp.Alter, exp.TruncateTable, exp.Copy, exp.Grant, exp.Set, exp.Command,
    exp.Transaction, exp.Commit, exp.Lock,
)

# Functions with side effects or access outside the marts schema.
_FORBIDDEN_FUNCTION_PREFIXES = ("pg_", "lo_", "dblink", "set_config", "current_setting",
                                "query_to_xml", "txid_", "version")


class UnsafeSQL(ValueError):
    """The query was rejected; the message is safe to show to the LLM and the user."""


def _function_name(node: exp.Expression) -> str:
    """Name as Postgres will see it. sqlglot normalises some functions into typed
    nodes (version() becomes CurrentVersion), so internal names can't be trusted."""
    return node.sql(dialect="postgres").split("(", 1)[0].strip().lower()


def validate_sql(sql: str, allowed_tables: set[str]) -> str:
    """Return a safe, row-capped version of `sql`, or raise UnsafeSQL.

    `allowed_tables` are bare table names in the marts schema, e.g. {"dim_station"}.
    """
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        raise UnsafeSQL("Empty query.")
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise UnsafeSQL(f"Could not parse SQL: {str(e).splitlines()[0]}") from None

    if len(statements) != 1:
        raise UnsafeSQL("Only a single statement is allowed.")
    tree = statements[0]
    if not isinstance(tree, exp.Query):
        raise UnsafeSQL(f"Only SELECT queries are allowed, got {type(tree).__name__.upper()}.")

    for node in tree.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise UnsafeSQL(f"{type(node).__name__.upper()} is not allowed in a read-only query.")
        if isinstance(node, exp.Func):
            name = _function_name(node)
            if name.startswith(_FORBIDDEN_FUNCTION_PREFIXES):
                raise UnsafeSQL(f"Function {name}() is not allowed.")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name, schema = table.name.lower(), (table.db or "").lower()
        if not schema and name in cte_names:
            continue
        if schema != ALLOWED_SCHEMA or name not in allowed_tables:
            qualified = f"{schema}.{name}" if schema else name
            raise UnsafeSQL(
                f"Table {qualified} is not available. Use one of: "
                + ", ".join(f"{ALLOWED_SCHEMA}.{t}" for t in sorted(allowed_tables))
            )

    return _cap_rows(tree).sql(dialect="postgres")


def _cap_rows(tree: exp.Query) -> exp.Query:
    limit = tree.args.get("limit")
    if isinstance(tree, exp.Select):
        current = _limit_value(limit)
        if current is None or current > MAX_ROWS:
            return tree.limit(MAX_ROWS)
        return tree
    # UNION / INTERSECT / EXCEPT: wrap rather than guess where the limit binds.
    return exp.select("*").from_(tree.subquery("q")).limit(MAX_ROWS)


def _limit_value(limit: exp.Expression | None) -> int | None:
    if limit is None:
        return None
    try:
        return int(limit.expression.this)
    except (AttributeError, TypeError, ValueError):
        return None   # non-literal limit (e.g. an expression): treat as uncapped
