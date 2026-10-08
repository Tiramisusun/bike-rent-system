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
    responses:
      200:
        description: Answer, the SQL that produced it, and up to 50 result rows
      400:
        description: Missing or too long question
      429:
        description: Rate limit or daily budget reached
      503:
        description: Assistant not configured on this server
    """
    if not os.getenv("LLM_API_KEY"):
        return jsonify({"error": "The assistant is not configured on this server"}), 503

    question = ((request.get_json(silent=True) or {}).get("question") or "").strip()
    if not question:
        return jsonify({"error": "Please enter a question"}), 400
    if len(question) > MAX_QUESTION_CHARS:
        return jsonify({"error": f"Questions are limited to {MAX_QUESTION_CHARS} characters"}), 400

    from src.agent.agent import ask
    result = ask(question, _agent_engine())
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
        "latency_s": result.latency_s,
    })
