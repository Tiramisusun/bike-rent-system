"""Text-to-SQL agent: plain tool-calling loop over an OpenAI-compatible chat API.

No agent framework on purpose — the loop is ~60 lines, every step is visible,
and the eval can record exactly what happened on each attempt.

    question ─► LLM ─(run_sql)─► guardrails ─► read-only Postgres ─┐
                 ▲                                                  │
                 └────────── rows, or the error to fix ─────────────┘
                 ... until the LLM answers in plain text (max MAX_TOOL_CALLS queries)

Configured by LLM_BASE_URL, LLM_API_KEY, LLM_MODEL (defaults: Xiaomi MiMo).
"""

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.engine import Engine

from src.agent.executor import run_query
from src.agent.guardrails import UnsafeSQL, validate_sql
from src.agent.semantic_layer import build_schema_context

MAX_TOOL_CALLS = 4          # first try + up to 3 corrections
ROWS_SHOWN_TO_MODEL = 50

RUN_SQL_TOOL = {
    "type": "function",
    "function": {
        "name": "run_sql",
        "description": (
            "Run one read-only PostgreSQL SELECT query against the Dublin Bikes marts "
            "and return the rows. Only tables in the marts schema are available; "
            "results are capped at 200 rows."
        ),
        "parameters": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "A single SELECT statement."}},
            "required": ["sql"],
        },
    },
}

SYSTEM_PROMPT = """\
You answer questions about Dublin's public bike-share stations by querying a PostgreSQL
data warehouse with the run_sql tool.

Rules:
- Always call run_sql to get the data; never guess or invent numbers.
- Write one SELECT statement per call, using fully qualified names like marts.dim_station.
- If a query fails, read the error, fix the query and call run_sql again.
- Then answer in one to three plain-English sentences, using only the numbers returned.
  Mention station names rather than IDs where you can.
- If the data cannot answer the question, say so briefly. Questions unrelated to the
  bike-share data, and requests to change data, must be declined without calling run_sql.

Current time in Dublin: {now}

Warehouse:
{schema}
"""


@dataclass
class Attempt:
    sql: str
    ok: bool
    error: str | None = None
    row_count: int | None = None


@dataclass
class AgentResult:
    question: str
    answer: str
    sql: str | None = None                 # last query that ran successfully
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    attempts: list[Attempt] = field(default_factory=list)
    latency_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None               # set when the agent itself failed

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["attempts"] = [a.__dict__ for a in self.attempts]
        return d


def make_client():
    from openai import OpenAI
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY is not set")
    return OpenAI(
        api_key=api_key,
        base_url=os.getenv("LLM_BASE_URL", "https://token-plan-ams.xiaomimimo.com/v1"),
        timeout=60,
        max_retries=1,
    )


def ask(question: str, engine: Engine, client=None, include_docs: bool = True,
        model: str | None = None) -> AgentResult:
    started = time.monotonic()
    result = AgentResult(question=question, answer="")
    client = client or make_client()
    model = model or os.getenv("LLM_MODEL", "mimo-v2.6-pro")

    schema, allowed_tables = build_schema_context(engine, include_docs=include_docs)
    now = datetime.now(ZoneInfo("Europe/Dublin")).strftime("%A %Y-%m-%d %H:%M")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(now=now, schema=schema)},
        {"role": "user", "content": question},
    ]

    try:
        for _ in range(MAX_TOOL_CALLS + 1):
            response = client.chat.completions.create(
                model=model, messages=messages, tools=[RUN_SQL_TOOL],
                temperature=0, max_completion_tokens=2048,
            )
            if response.usage:
                result.prompt_tokens += response.usage.prompt_tokens or 0
                result.completion_tokens += response.usage.completion_tokens or 0
            message = response.choices[0].message
            # Keep the full message, including provider extras such as MiMo's
            # reasoning_content, which must be sent back on the next turn.
            messages.append(message.model_dump(exclude_none=True))

            if not message.tool_calls:
                result.answer = (message.content or "").strip()
                break
            if len(result.attempts) >= MAX_TOOL_CALLS:
                result.answer = "Sorry, I couldn't find a working query for that question."
                break

            for call in message.tool_calls:
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": _run_tool_call(call, engine, allowed_tables, result)})
        else:
            result.answer = result.answer or "Sorry, I couldn't answer that."
    except Exception as e:                      # network, auth, provider errors
        result.error = f"{type(e).__name__}: {e}"
        result.answer = "The assistant is unavailable right now."

    result.latency_s = round(time.monotonic() - started, 2)
    return result


def _run_tool_call(call, engine: Engine, allowed_tables: set[str], result: AgentResult) -> str:
    try:
        sql = json.loads(call.function.arguments or "{}").get("sql", "")
    except json.JSONDecodeError:
        sql = ""
    if call.function.name != "run_sql":
        return json.dumps({"error": f"Unknown tool {call.function.name}"})

    try:
        safe_sql = validate_sql(sql, allowed_tables)
        query = run_query(engine, safe_sql)
    except UnsafeSQL as e:
        result.attempts.append(Attempt(sql=sql, ok=False, error=f"rejected: {e}"))
        return json.dumps({"error": f"Query rejected: {e}"})
    except Exception as e:                      # database error: let the model fix it
        message = str(getattr(e, "orig", e)).strip().splitlines()[0]
        result.attempts.append(Attempt(sql=sql, ok=False, error=message))
        return json.dumps({"error": message})

    result.attempts.append(Attempt(sql=safe_sql, ok=True, row_count=len(query.rows)))
    result.sql, result.columns, result.rows = safe_sql, query.columns, query.rows
    return json.dumps({
        "columns": query.columns,
        "rows": query.rows[:ROWS_SHOWN_TO_MODEL],
        "row_count": len(query.rows),
        "truncated": len(query.rows) > ROWS_SHOWN_TO_MODEL,
    }, default=str)
