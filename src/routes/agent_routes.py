"""Ask questions about the bike data in plain English (Text-to-SQL agent)."""

import os

from flask import Blueprint, current_app, jsonify, request

from src.extensions import limiter

agent_bp = Blueprint("agent", __name__)

MAX_QUESTION_CHARS = 300
ROWS_RETURNED = 50

# Every question costs LLM tokens, so limits are tighter than the rest of the API:
# per client IP, plus a site-wide daily budget shared by everyone.
PER_CLIENT_LIMIT = "5 per minute;30 per hour;100 per day"


def daily_budget() -> str:
    return os.getenv("AGENT_DAILY_BUDGET", "500 per day")


class BadHistory(ValueError):
    pass


def parse_history(raw) -> list:
    """Validate the conversation the browser sends back (untrusted input).

    Shape: [{"question": str, "answer": str, "sql": str|null, "columns": [str], "rows": [[...]]}, ...]
    Wrong types are rejected; anything long is trimmed by the agent (MAX_HISTORY_TURNS, ...).
    """
    from src.agent.agent import MAX_HISTORY_TURNS, Turn
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise BadHistory("history must be a list")
    turns = []
    for item in raw[-MAX_HISTORY_TURNS:]:
        if not isinstance(item, dict):
            raise BadHistory("each history item must be an object")
        question, answer, sql = item.get("question"), item.get("answer"), item.get("sql")
        columns, rows = item.get("columns") or [], item.get("rows") or []
        if not isinstance(question, str) or not isinstance(answer, str):
            raise BadHistory("history items need a question and an answer")
        if sql is not None and not isinstance(sql, str):
            raise BadHistory("history sql must be a string")
        if not isinstance(columns, list) or not all(isinstance(c, str) for c in columns):
            raise BadHistory("history columns must be a list of strings")
        if not isinstance(rows, list) or not all(isinstance(r, list) for r in rows):
            raise BadHistory("history rows must be a list of lists")
        turns.append(Turn(question=question, answer=answer, sql=sql, columns=columns, rows=rows))
    return turns


def _agent_engine():
    engine = current_app.extensions.get("agent_engine")
    if engine is None:
        from src.warehouse.config import agent_engine
        engine = current_app.extensions["agent_engine"] = agent_engine()
    return engine


@agent_bp.route("/api/agent/ask", methods=["POST"])
@limiter.limit(PER_CLIENT_LIMIT)
@limiter.shared_limit(daily_budget, scope="agent-daily-budget", key_func=lambda: "all-clients")
def ask_agent():
    """
    Answer a question about the Dublin Bikes data with a read-only SQL query.
    ---
    tags:
      - Assistant
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            question:
              type: string
              example: Which station has spent the most minutes empty?
            history:
              type: array
              description: >
                Earlier turns of this conversation, oldest first (the server keeps no state).
                Each item - question, answer, sql, columns, rows - as returned by this endpoint.
                Only the last 6 are used.
              items:
                type: object
    responses:
      200:
        description: Answer, the SQL that produced it, and up to 50 result rows
      400:
        description: Missing or too long question
      429:
        description: Rate limit or daily budget reached
      502:
        description: The language-model provider failed
      503:
        description: Assistant not configured on this server
      504:
        description: No answer within the time budget (AGENT_TIME_BUDGET_S, default 60 s)
    """
    if not os.getenv("LLM_API_KEY"):
        return jsonify({"error": "The assistant is not configured on this server"}), 503

    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Please enter a question"}), 400
    if len(question) > MAX_QUESTION_CHARS:
        return jsonify({"error": f"Questions are limited to {MAX_QUESTION_CHARS} characters"}), 400

    try:
        history = parse_history(body.get("history"))
    except BadHistory as e:
        return jsonify({"error": f"Invalid conversation history: {e}"}), 400

    from src.agent.agent import ask
    result = ask(question, _agent_engine(), history=history)
    if result.timed_out:
        current_app.logger.warning(f"[/api/agent/ask] timed out after {result.latency_s}s: {result.error}")
        return jsonify({"error": "That took too long — please try again or ask a simpler question"}), 504
    if result.error:
        current_app.logger.error(f"[/api/agent/ask] agent failed: {result.error}")
        return jsonify({"error": "The assistant is unavailable right now"}), 502

    return jsonify({
        "question": question,
        "answer": result.answer,
        "sql": result.sql,
        "columns": result.columns,
        "rows": result.rows[:ROWS_RETURNED],
        "row_count": len(result.rows),
        "queries_tried": len(result.attempts),
        "grounded": result.grounded,
        "latency_s": result.latency_s,
    })
