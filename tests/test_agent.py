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


# ── Conversation history (multi-turn) ─────────────────────────────────────────

from src.agent.agent import MAX_HISTORY_TURNS, Turn, history_messages


def test_history_comes_before_the_new_question(fake_warehouse):
    llm = FakeLLM(_completion(content="ok"))
    earlier = Turn(question="Which station was empty longest?", answer="GOLDEN LANE.",
                   sql="SELECT station_name FROM marts.mart_station_kpis LIMIT 1",
                   columns=["station_name"], rows=[["GOLDEN LANE"]])
    ask("And at peak hours?", engine=None, client=llm, history=[earlier])
    sent = llm.requests[0]
    assert [m["role"] for m in sent] == ["system", "system", "user", "assistant", "user"]
    note = sent[1]["content"]
    assert "SELECT station_name" in note and '"GOLDEN LANE"' in note   # rows let "it" be resolved
    assert sent[2]["content"] == "Which station was empty longest?"
    assert sent[3]["content"] == "GOLDEN LANE."                         # the answer only
    assert "SELECT" not in sent[3]["content"]                           # no SQL to imitate
    assert sent[4]["content"] == "And at peak hours?"


def test_only_the_last_turns_are_kept():
    turns = [Turn(question=f"q{i}", answer=f"a{i}") for i in range(10)]   # no SQL -> no note
    msgs = history_messages(turns)
    assert len(msgs) == 2 * MAX_HISTORY_TURNS
    assert msgs[0]["content"] == f"q{10 - MAX_HISTORY_TURNS}" and msgs[-1]["content"] == "a9"


def test_long_history_fields_are_truncated():
    msgs = history_messages([Turn(question="q" * 5000, answer="a" * 5000, sql="S" * 9000,
                                  columns=["c"], rows=[[i] for i in range(100)])])
    note, question, answer = msgs[0]["content"], msgs[1]["content"], msgs[2]["content"]
    sql = note.split("Turn 1 ran: ", 1)[1].split("\n", 1)[0]
    assert len(question) == 300 and len(answer) == 1000 and len(sql) == 2000
    assert '"rows": [[0], [1], [2], [3], [4]]' in note                  # only the first 5 rows


def test_no_history_means_single_turn(fake_warehouse):
    llm = FakeLLM(_completion(content="ok"))
    ask("q", engine=None, client=llm, history=None)
    assert [m["role"] for m in llm.requests[0]] == ["system", "user"]


# ── Grounding: numbers only from a query run in this turn ────────────────────

from src.agent.agent import UNGROUNDED_NUDGE


def test_numbers_without_a_query_get_one_nudge_then_a_real_query(fake_warehouse):
    # Replays the bug found in testing: a follow-up answered with an invented figure.
    llm = FakeLLM(
        _completion(content="GRANGEGORMAN LOWER was empty for 343 minutes at peak."),
        _completion(sql="SELECT station_name, empty_minutes FROM marts.mart_station_kpis LIMIT 1"),
        _completion(content="SMITHFIELD was empty for 120 minutes."),
    )
    r = ask("And at peak hours?", engine=None, client=llm,
            history=[Turn(question="Which station was empty longest?", answer="GRANGEGORMAN LOWER.")])
    assert llm.requests[1][-1] == {"role": "user", "content": UNGROUNDED_NUDGE}
    assert r.answer == "SMITHFIELD was empty for 120 minutes." and r.grounded


def test_only_one_nudge_and_answer_marked_ungrounded(fake_warehouse):
    llm = FakeLLM(_completion(content="About 12 bikes."), _completion(content="Still 12 bikes."))
    r = ask("q", engine=None, client=llm)
    assert len(llm.requests) == 2 and r.answer == "Still 12 bikes." and r.grounded is False


def test_decline_without_numbers_is_not_nudged(fake_warehouse):
    llm = FakeLLM(_completion(content="I can only answer questions about Dublin Bikes data."))
    r = ask("Write me a poem", engine=None, client=llm)
    assert len(llm.requests) == 1 and r.grounded is False


def test_copied_reference_lines_are_removed_from_answers(fake_warehouse):
    llm = FakeLLM(
        _completion(sql="SELECT station_name FROM marts.dim_station"),
        _completion(content="It has 40 docks.\n\n[SQL used: SELECT 1]\n[First rows: {}]"),
    )
    assert ask("q", engine=None, client=llm).answer == "It has 40 docks."



# ── Time budget: a slow provider can't hold a request for minutes ────────────

import openai

from src.agent.agent import RETRYABLE


class SlowLLM(FakeLLM):
    """Each call takes `seconds` on a fake clock; records the timeout it was given."""

    def __init__(self, clock, seconds, *completions):
        super().__init__(*completions)
        self.clock, self.seconds, self.timeouts = clock, seconds, []

    def _create(self, **kwargs):
        self.timeouts.append(kwargs["timeout"])
        self.clock[0] += self.seconds
        return super()._create(**kwargs)


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(agent_mod, "_clock", lambda: now[0])
    return now


def test_each_call_gets_only_the_time_left_and_stops_at_the_budget(fake_warehouse, clock):
    llm = SlowLLM(clock, 40,
                  _completion(sql="SELECT station_name FROM marts.dim_station", call_id="c1"),
                  _completion(sql="SELECT station_name FROM marts.dim_station", call_id="c2"),
                  _completion(content="never reached"))
    r = ask("q", engine=None, client=llm, time_budget_s=60)
    assert llm.timeouts == [60, 20]                     # third call: 60 - 80 < 0, not started
    assert r.timed_out and r.error.startswith("AgentTimeout")
    assert "too long" in r.answer and r.latency_s == 80


def test_provider_timeout_uses_up_the_budget_and_is_not_retried(fake_warehouse, clock):
    # The call was given all the time left, so when it times out nothing is left to retry with.
    llm = SlowLLM(clock, 60, openai.APITimeoutError(request=None))
    r = ask("q", engine=None, client=llm, time_budget_s=60)
    assert r.timed_out and llm.timeouts == [60]


def test_provider_hiccup_is_retried_once(fake_warehouse):
    hiccup = openai.APIConnectionError(request=None)
    assert isinstance(hiccup, RETRYABLE)
    llm = FakeLLM(hiccup, _completion(content="I can only answer questions about Dublin Bikes data."))
    r = ask("q", engine=None, client=llm)
    assert r.error is None and len(llm.requests) == 2


def test_second_hiccup_is_reported(fake_warehouse):
    def hiccup():
        return openai.APIConnectionError(request=None)
    llm = FakeLLM(hiccup(), hiccup(), _completion(content="never reached"))
    r = ask("q", engine=None, client=llm)
    assert r.error.startswith("APIConnectionError") and not r.timed_out and len(llm.requests) == 2


# ── Token accounting and per-model request options ───────────────────────────

def _completion_with_usage(usage, content="I can only answer questions about Dublin Bikes data."):
    c = _completion(content=content).model_dump()
    c["usage"] = usage
    return ChatCompletion.model_validate(c)


def test_cached_and_reasoning_tokens_are_counted_openai_style(fake_warehouse):
    llm = FakeLLM(_completion_with_usage({
        "prompt_tokens": 4000, "completion_tokens": 300, "total_tokens": 4300,
        "prompt_tokens_details": {"cached_tokens": 3500},
        "completion_tokens_details": {"reasoning_tokens": 250}}))
    r = ask("q", engine=None, client=llm)
    assert (r.prompt_tokens, r.cached_prompt_tokens, r.completion_tokens, r.reasoning_tokens) == (4000, 3500, 300, 250)


def test_cached_tokens_are_counted_deepseek_style(fake_warehouse):
    llm = FakeLLM(_completion_with_usage({
        "prompt_tokens": 4000, "completion_tokens": 50, "total_tokens": 4050,
        "prompt_cache_hit_tokens": 3800, "prompt_cache_miss_tokens": 200}))
    assert ask("q", engine=None, client=llm).cached_prompt_tokens == 3800


class RecordingLLM(FakeLLM):
    def _create(self, **kwargs):
        self.kwargs = kwargs
        return super()._create(**kwargs)


def test_request_options_override_defaults_and_none_removes_one(fake_warehouse):
    llm = RecordingLLM(_completion(content="ok"))
    ask("q", engine=None, client=llm, request_options={"temperature": None, "max_completion_tokens": 8000})
    assert "temperature" not in llm.kwargs and llm.kwargs["max_completion_tokens"] == 8000


def test_default_request_options(fake_warehouse):
    llm = RecordingLLM(_completion(content="ok"))
    ask("q", engine=None, client=llm)
    assert llm.kwargs["temperature"] == 0 and llm.kwargs["max_completion_tokens"] == 2048


def test_production_request_options_come_from_the_environment(fake_warehouse, monkeypatch):
    monkeypatch.setenv("LLM_REQUEST_OPTIONS", '{"reasoning_effort": "none"}')
    llm = RecordingLLM(_completion(content="ok"))
    ask("q", engine=None, client=llm)
    assert llm.kwargs["reasoning_effort"] == "none" and llm.kwargs["temperature"] == 0


def test_explicit_request_options_ignore_the_environment(fake_warehouse, monkeypatch):
    monkeypatch.setenv("LLM_REQUEST_OPTIONS", '{"reasoning_effort": "none"}')
    llm = RecordingLLM(_completion(content="ok"))
    ask("q", engine=None, client=llm, request_options={})
    assert "reasoning_effort" not in llm.kwargs
