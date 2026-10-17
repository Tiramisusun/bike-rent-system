import pytest

from src.agent.agent import AgentResult, Attempt


@pytest.fixture
def client(monkeypatch):
    from app import app as flask_app
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    flask_app.extensions["agent_engine"] = object()       # never touched: ask() is faked
    with flask_app.test_client() as c:
        yield c
    flask_app.extensions.pop("agent_engine", None)


@pytest.fixture
def fake_ask(monkeypatch):
    calls = []

    def _ask(question, engine, **kw):
        calls.append(question)
        return AgentResult(question=question, answer="GOLDEN LANE, at 70.6%.",
                           sql="SELECT station_name FROM marts.mart_station_kpis LIMIT 1",
                           columns=["station_name"], rows=[["GOLDEN LANE"]] * 60,
                           attempts=[Attempt(sql="...", ok=True, row_count=60)], latency_s=1.2)

    monkeypatch.setattr("src.agent.agent.ask", _ask)
    return calls


def test_returns_answer_sql_and_capped_rows(client, fake_ask):
    res = client.post("/api/agent/ask", json={"question": "Which station is short of bikes most at peak?"})
    body = res.get_json()
    assert res.status_code == 200
    assert body["answer"].startswith("GOLDEN LANE") and body["sql"].startswith("SELECT")
    assert len(body["rows"]) == 50 and body["row_count"] == 60
    assert body["queries_tried"] == 1


@pytest.mark.parametrize("payload, status", [
    ({}, 400), ({"question": "   "}, 400), ({"question": "x" * 301}, 400),
])
def test_rejects_bad_input_without_calling_the_llm(client, fake_ask, payload, status):
    assert client.post("/api/agent/ask", json=payload).status_code == status
    assert fake_ask == []


def test_not_configured_without_api_key(client, fake_ask, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY")
    assert client.post("/api/agent/ask", json={"question": "q"}).status_code == 503


def test_provider_failure_hides_details(client, monkeypatch):
    monkeypatch.setattr("src.agent.agent.ask", lambda q, e, **kw: AgentResult(
        question=q, answer="x", error="AuthenticationError: invalid key tp-secret123"))
    res = client.post("/api/agent/ask", json={"question": "q"})
    assert res.status_code == 502 and "tp-secret123" not in res.get_data(as_text=True)


@pytest.fixture
def limits_on():
    from src.extensions import limiter
    limiter.enabled = True
    limiter.reset()
    yield
    limiter.reset()


def test_per_client_rate_limit(client, fake_ask, limits_on):
    codes = [client.post("/api/agent/ask", json={"question": f"q{i}"}).status_code for i in range(6)]
    assert codes == [200] * 5 + [429]


def test_daily_budget_is_shared_across_clients(client, fake_ask, limits_on, monkeypatch):
    monkeypatch.setenv("AGENT_DAILY_BUDGET", "2 per day")
    # A different client IP each time: per-client limits never trigger, the shared budget does.
    statuses = [client.post("/api/agent/ask", json={"question": "q"},
                            environ_base={"REMOTE_ADDR": f"10.0.0.{i}"}).status_code for i in range(3)]
    assert statuses == [200, 200, 429]


# ── Conversation history ──────────────────────────────────────────────────────

@pytest.fixture
def capture_ask(monkeypatch):
    seen = {}

    def _ask(question, engine, **kw):
        seen["history"] = kw.get("history")
        return AgentResult(question=question, answer="ok")

    monkeypatch.setattr("src.agent.agent.ask", _ask)
    return seen


def test_history_is_passed_to_the_agent(client, capture_ask):
    history = [{"question": "Which station was empty longest?", "answer": "GOLDEN LANE.",
                "sql": "SELECT 1", "columns": ["station_name"], "rows": [["GOLDEN LANE"]]}]
    res = client.post("/api/agent/ask", json={"question": "And at peak hours?", "history": history})
    assert res.status_code == 200
    turn = capture_ask["history"][0]
    assert turn.question == "Which station was empty longest?" and turn.rows == [["GOLDEN LANE"]]


def test_only_last_six_turns_accepted(client, capture_ask):
    history = [{"question": f"q{i}", "answer": f"a{i}"} for i in range(9)]
    client.post("/api/agent/ask", json={"question": "q", "history": history})
    assert [t.question for t in capture_ask["history"]] == [f"q{i}" for i in range(3, 9)]


@pytest.mark.parametrize("history", [
    "not a list",
    ["not an object"],
    [{"question": "q"}],                                   # no answer
    [{"question": "q", "answer": "a", "sql": 42}],
    [{"question": "q", "answer": "a", "columns": "x"}],
    [{"question": "q", "answer": "a", "rows": ["not a row"]}],
])
def test_malformed_history_is_rejected_without_calling_the_llm(client, capture_ask, history):
    res = client.post("/api/agent/ask", json={"question": "q", "history": history})
    assert res.status_code == 400 and "history" in res.get_json()["error"]
    assert "history" not in capture_ask
