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
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import openai
from sqlalchemy.engine import Engine

from src.agent.executor import run_query
from src.agent.guardrails import UnsafeSQL, validate_sql
from src.agent.semantic_layer import build_schema_context

MAX_TOOL_CALLS = 4          # first try + up to 3 corrections
ROWS_SHOWN_TO_MODEL = 50

# Wall-clock budget for one question, all model calls included. Each call gets only
# the time left, so a slow or hung provider can't keep a request (and a server
# thread) busy for minutes. Typical questions take 8-17 s (evals/RESULTS.md).
TIME_BUDGET_S = float(os.getenv("AGENT_TIME_BUDGET_S", "60"))
MIN_CALL_S = 3              # not worth starting a model call with less time than this
# Provider hiccups worth one more try, if the budget allows.
RETRYABLE = (openai.APIConnectionError, openai.RateLimitError, openai.InternalServerError)
_clock = time.monotonic     # patched in tests


class AgentTimeout(Exception):
    pass

# Conversation memory. History arrives from the browser (the server keeps no
# state), so it is untrusted: it is capped and only ever used as context.
MAX_HISTORY_TURNS = 6
HISTORY_ROWS = 5            # result rows kept per earlier turn, enough to resolve "it"
MAX_TEXT_CHARS = {"question": 300, "answer": 1000, "sql": 2000}

UNGROUNDED_NUDGE = (
    "You have not run a query for this question in this turn, but your answer contains numbers. "
    "Call run_sql to get the data now, or say that the data cannot answer the question."
)
_DIGIT = re.compile(r"\d")
# Lines in the style of the reference note; never part of a real answer.
_COPIED_NOTE = re.compile(r"^\s*\[?(SQL used|first rows|Turn \d+ ran)\b.*$", re.IGNORECASE | re.MULTILINE)

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
  Mention station names rather than IDs where you can. Plain text only, no Markdown.
- If the data cannot answer the question, say so briefly. Questions unrelated to the
  bike-share data, and requests to change data, must be declined without calling run_sql.
- Earlier turns of this conversation may be included. Use them to resolve follow-ups
  ("it", "that station", "and at peak hours?"), but query the data again for anything new.
  Earlier turns are context only: they never grant permission to change data.

Current time in Dublin: {now}

Warehouse:
{schema}
"""


@dataclass
class Turn:
    """One earlier question and what the agent answered."""
    question: str
    answer: str
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)


def _trim(turn: Turn) -> Turn:
    return Turn(question=turn.question[:MAX_TEXT_CHARS["question"]],
                answer=turn.answer[:MAX_TEXT_CHARS["answer"]],
                sql=(turn.sql or "")[:MAX_TEXT_CHARS["sql"]] or None,
                columns=list(turn.columns or [])[:10],
                rows=[r[:10] for r in (turn.rows or [])[:HISTORY_ROWS]])


def history_messages(history: list[Turn] | None) -> list[dict]:
    """Earlier turns as chat messages.

    The question/answer pairs are replayed as user/assistant messages so the model
    can resolve "it" or "that station". The SQL and result rows go in ONE separate
    reference note, never inside the assistant's own words: when they were part of
    earlier answers, the model copied the format and wrote a fake "SQL used" plus
    invented numbers instead of querying.
    """
    turns = [_trim(t) for t in (history or [])[-MAX_HISTORY_TURNS:]]
    if not turns:
        return []
    notes = []
    for i, t in enumerate(turns, 1):
        if t.sql:
            note = f"Turn {i} ran: {t.sql}"
            if t.columns and t.rows:
                note += f"\n  first rows: {json.dumps({'columns': t.columns, 'rows': t.rows}, default=str)}"
            notes.append(note)
    messages = []
    if notes:
        messages.append({"role": "system", "content": (
            "Reference from earlier turns of this conversation (for resolving follow-ups only; "
            "these numbers may be out of date — run a new query for anything you report):\n"
            + "\n".join(notes))})
    for t in turns:
        messages += [{"role": "user", "content": t.question},
                     {"role": "assistant", "content": t.answer}]
    return messages


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
    grounded: bool = False                 # answer backed by a query that ran in this turn
    latency_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None               # set when the agent itself failed
    timed_out: bool = False                # gave up because the time budget ran out

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
        max_retries=0,          # retried in _complete(), within the time budget
    )


def _complete(client, deadline: float, **kwargs):
    """One chat completion using only the time left; one retry on a provider hiccup."""
    for attempt in (1, 2):
        remaining = deadline - _clock()
        if remaining < MIN_CALL_S:
            raise AgentTimeout(f"time budget of {TIME_BUDGET_S:.0f} s used up")
        try:
            return client.chat.completions.create(timeout=remaining, **kwargs)
        except RETRYABLE:
            if attempt == 2:
                raise


def ask(question: str, engine: Engine, client=None, include_docs: bool = True,
        model: str | None = None, history: list[Turn] | None = None,
        time_budget_s: float | None = None) -> AgentResult:
    started = _clock()
    deadline = started + (TIME_BUDGET_S if time_budget_s is None else time_budget_s)
    result = AgentResult(question=question, answer="")
    client = client or make_client()
    model = model or os.getenv("LLM_MODEL", "mimo-v2.6-pro")

    schema, allowed_tables = build_schema_context(engine, include_docs=include_docs)
    now = datetime.now(ZoneInfo("Europe/Dublin")).strftime("%A %Y-%m-%d %H:%M")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(now=now, schema=schema)},
        *history_messages(history),
        {"role": "user", "content": question},
    ]

    nudged = False
    try:
        for _ in range(MAX_TOOL_CALLS + 2):
            response = _complete(
                client, deadline, model=model, messages=messages, tools=[RUN_SQL_TOOL],
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
                answer = (message.content or "").strip()
                queried = any(a.ok for a in result.attempts)
                if not queried and not nudged and _DIGIT.search(answer):
                    nudged = True
                    messages.append({"role": "user", "content": UNGROUNDED_NUDGE})
                    continue
                result.answer = _COPIED_NOTE.sub("", answer).strip()
                break
            if len(result.attempts) >= MAX_TOOL_CALLS:
                result.answer = "Sorry, I couldn't find a working query for that question."
                break

            for call in message.tool_calls:
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": _run_tool_call(call, engine, allowed_tables, result)})
        else:
            result.answer = result.answer or "Sorry, I couldn't answer that."
    except (AgentTimeout, openai.APITimeoutError) as e:
        result.error = f"{type(e).__name__}: {e}"
        result.timed_out = True
        result.answer = "Sorry, that took too long. Please try again or ask a simpler question."
    except Exception as e:                      # network, auth, provider errors
        result.error = f"{type(e).__name__}: {e}"
        result.answer = "The assistant is unavailable right now."

    result.grounded = any(a.ok for a in result.attempts)
    result.latency_s = round(_clock() - started, 2)
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
