"""Agent loop tests with a scripted fake LLM (no API key, no Postgres needed)."""

import json
from types import SimpleNamespace

import pytest
from openai.types.chat import ChatCompletion

from src.agent import agent as agent_mod
from src.agent.agent import MAX_TOOL_CALLS, ask
from src.agent.executor import QueryResult

TABLES = {"dim_station", "mart_station_kpis"}


def _completion(content=None, sql=None, reasoning=None, call_id="call_1"):
    message = {"role": "assistant", "content": content}
    if sql is not None:
        message["tool_calls"] = [{"id": call_id, "type": "function",
                                  "function": {"name": "run_sql", "arguments": json.dumps({"sql": sql})}}]
    if reasoning:
        message["reasoning_content"] = reasoning
    return ChatCompletion.model_validate({
        "id": "x", "object": "chat.completion", "created": 0, "model": "fake",
        "choices": [{"index": 0, "finish_reason": "tool_calls" if sql else "stop", "message": message}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    })


class FakeLLM:
    """Returns the scripted completions in order and records every request."""

    def __init__(self, *completions):
        self._script = list(completions)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(json.loads(json.dumps(kwargs["messages"], default=str)))
        if isinstance(self._script[0], Exception):
            raise self._script.pop(0)
        return self._script.pop(0)


@pytest.fixture(autouse=True)
def fake_warehouse(monkeypatch):
    monkeypatch.setattr(agent_mod, "build_schema_context", lambda engine, include_docs=True: ("schema", TABLES))
    executed = []

    def fake_run_query(engine, sql):
        executed.append(sql)
        if "boom" in sql:
            raise Exception('column "boom" does not exist')
        return QueryResult(columns=["station_name", "empty_minutes"], rows=[["SMITHFIELD", 120.0]])

    monkeypatch.setattr(agent_mod, "run_query", fake_run_query)
    return executed


def test_answers_from_a_single_query(fake_warehouse):
    llm = FakeLLM(
        _completion(sql="SELECT station_name, empty_minutes FROM marts.mart_station_kpis ORDER BY 2 DESC LIMIT 1"),
        _completion(content="SMITHFIELD was empty longest, for 120 minutes."),
    )
    r = ask("Which station was empty longest?", engine=None, client=llm)
    assert r.answer == "SMITHFIELD was empty longest, for 120 minutes."
    assert r.rows == [["SMITHFIELD", 120.0]] and r.columns == ["station_name", "empty_minutes"]
    assert [a.ok for a in r.attempts] == [True]
    assert r.prompt_tokens == 200 and r.completion_tokens == 40
    assert r.error is None


def test_rejected_query_is_fed_back_and_corrected(fake_warehouse):
    llm = FakeLLM(
        _completion(sql="SELECT * FROM raw.station_status", call_id="c1"),
        _completion(sql="SELECT station_name FROM marts.dim_station", call_id="c2"),
        _completion(content="Here they are."),
    )
    r = ask("List stations", engine=None, client=llm)
    assert [a.ok for a in r.attempts] == [False, True]
    assert r.attempts[0].error.startswith("rejected:")
    tool_reply = json.loads(llm.requests[1][-1]["content"])
    assert "Query rejected" in tool_reply["error"] and "marts.dim_station" in tool_reply["error"]
    assert fake_warehouse == ["SELECT station_name FROM marts.dim_station LIMIT 200"]   # rejected SQL never ran


def test_database_error_is_fed_back(fake_warehouse):
    llm = FakeLLM(
        _completion(sql="SELECT boom FROM marts.dim_station", call_id="c1"),
        _completion(sql="SELECT station_name FROM marts.dim_station", call_id="c2"),
        _completion(content="Done."),
    )
    r = ask("q", engine=None, client=llm)
    assert r.attempts[0].error == 'column "boom" does not exist'
    assert json.loads(llm.requests[1][-1]["content"]) == {"error": 'column "boom" does not exist'}
    assert r.attempts[1].ok


def test_gives_up_after_max_tool_calls(fake_warehouse):
    llm = FakeLLM(*[_completion(sql="SELECT boom FROM marts.dim_station", call_id=f"c{i}")
                    for i in range(MAX_TOOL_CALLS + 1)])
    r = ask("q", engine=None, client=llm)
    assert len(r.attempts) == MAX_TOOL_CALLS
    assert r.sql is None and "couldn't" in r.answer


def test_reasoning_content_is_sent_back_next_turn(fake_warehouse):
    llm = FakeLLM(
        _completion(sql="SELECT station_name FROM marts.dim_station", reasoning="I should list stations."),
        _completion(content="Done."),
    )
    ask("q", engine=None, client=llm)
    assistant_turn = llm.requests[1][2]
    assert assistant_turn["role"] == "assistant"
    assert assistant_turn["reasoning_content"] == "I should list stations."


def test_off_topic_question_is_answered_without_sql(fake_warehouse):
    llm = FakeLLM(_completion(content="I can only answer questions about Dublin Bikes data."))
    r = ask("Write me a poem", engine=None, client=llm)
    assert r.attempts == [] and r.sql is None and fake_warehouse == []


def test_provider_failure_is_reported_not_raised():
    llm = FakeLLM(TimeoutError("upstream timed out"))
    r = ask("q", engine=None, client=llm)
    assert r.error.startswith("TimeoutError") and r.answer == "The assistant is unavailable right now."


def test_ablation_flag_reaches_the_semantic_layer(monkeypatch):
    seen = []

    def fake_context(engine, include_docs=True):
        seen.append(include_docs)
        return "schema", TABLES

    monkeypatch.setattr(agent_mod, "build_schema_context", fake_context)
    ask("q", engine=None, client=FakeLLM(_completion(content="ok")), include_docs=False)
    assert seen == [False]
