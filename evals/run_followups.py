"""Multi-turn evaluation: does the agent answer follow-ups correctly?

    python -m evals.run_followups
    python -m evals.run_followups --model gpt-luna     # a model from evals/models.yaml

For each pair in followups.yaml the agent answers turn 1, then the follow-up is asked
twice: with the agent's own turn 1 as history (how the chat page works), and alone
(no context — the ablation). Writes FOLLOWUPS.md and results/followups-<timestamp>.json.
"""

import argparse
import json
import os
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.agent.agent import Turn, ask, make_client
from src.agent.evaluation import results_match
from src.agent.executor import run_query
from src.agent.guardrails import validate_sql
from src.agent.semantic_layer import build_schema_context
from src.warehouse.config import agent_engine

HERE = Path(__file__).resolve().parent


def _gold(engine, tables, q):
    return run_query(engine, validate_sql(q["gold_sql"], tables)).rows


def _correct(result, gold, order_matters):
    return result.sql is not None and results_match(gold, result.rows, order_matters)


def run_pair(item, engine, client, tables, **model_kw):
    t1, t2 = item["turn1"], item["turn2"]
    r1 = ask(t1["question"], engine, client=client, **model_kw)
    previous = Turn(question=r1.question, answer=r1.answer, sql=r1.sql, columns=r1.columns, rows=r1.rows)
    with_history = ask(t2["question"], engine, client=client, history=[previous], **model_kw)
    without_history = ask(t2["question"], engine, client=client, **model_kw)
    g1, g2 = _gold(engine, tables, t1), _gold(engine, tables, t2)
    row = lambda r, gold, spec: {
        "question": r.question, "correct": _correct(r, gold, bool(spec.get("order_matters"))),
        "grounded": r.grounded, "answer": r.answer, "sql": r.sql, "error": r.error,
        "latency_s": r.latency_s, "prompt_tokens": r.prompt_tokens,
    }
    return {
        "id": item["id"],
        "turn1": row(r1, g1, t1),
        "turn2_with_history": row(with_history, g2, t2),
        "turn2_without_history": row(without_history, g2, t2),
    }


def pct(xs):
    return round(100 * sum(xs) / len(xs), 1) if xs else None


def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--model", help="a name from evals/models.yaml (default: LLM_* from .env)")
    args = parser.parse_args()

    items = yaml.safe_load((HERE / "followups.yaml").read_text())
    engine = agent_engine()
    if args.model:
        from evals.run_eval import load_models, make_model_client
        cfg = load_models()[args.model]
        client, model_id = make_model_client(cfg), cfg["model"]
        model_kw = {"model": model_id, "request_options": cfg.get("request_options") or {}}
    else:
        client, model_id, model_kw = make_client(), os.getenv("LLM_MODEL", "mimo-v2.6-pro"), {}
    _, tables = build_schema_context(engine)
    print(f"Running {len(items)} follow-up pairs ...", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(lambda it: run_pair(it, engine, client, tables, **model_kw), items))

    t1_ok = [r["turn1"]["correct"] for r in rows]
    summary = {
        "pairs": len(rows),
        "turn1_accuracy": pct(t1_ok),
        "followup_accuracy_with_history": pct([r["turn2_with_history"]["correct"] for r in rows]),
        "followup_accuracy_without_history": pct([r["turn2_without_history"]["correct"] for r in rows]),
        "followup_accuracy_with_history_when_turn1_correct": pct(
            [r["turn2_with_history"]["correct"] for r in rows if r["turn1"]["correct"]]),
        "grounded_rate_followups_with_history": pct([r["turn2_with_history"]["grounded"] for r in rows]),
        "median_latency_s_followup_with_history": round(statistics.median(
            r["turn2_with_history"]["latency_s"] for r in rows), 2),
        "avg_prompt_tokens_followup_with_vs_without": [
            round(statistics.mean(r["turn2_with_history"]["prompt_tokens"] for r in rows)),
            round(statistics.mean(r["turn2_without_history"]["prompt_tokens"] for r in rows))],
        "provider_errors": sum(bool(r[k]["error"]) for r in rows
                               for k in ("turn1", "turn2_with_history", "turn2_without_history")),
    }
    print(json.dumps(summary, indent=2), flush=True)

    stamp = datetime.now(timezone.utc)
    result = json.dumps({"model": model_id, "summary": summary, "details": rows}, indent=2, default=str)
    if args.model:                  # a candidate model: keep FOLLOWUPS.md for the deployed one
        out = HERE / "results" / "compare" / f"followups-{args.model}-{stamp:%Y%m%d-%H%M}.json"
        out.write_text(result)
        print(f"Wrote {out.relative_to(HERE.parent)}")
        return
    out = HERE / "results" / f"followups-{stamp:%Y%m%d-%H%M}.json"
    out.write_text(result)
    s = summary
    (HERE / "FOLLOWUPS.md").write_text("\n".join([
        "# Multi-turn evaluation",
        "",
        f"- Run: {stamp:%Y-%m-%d %H:%M UTC} · model `{model_id}` · "
        f"{s['pairs']} question + follow-up pairs (`followups.yaml`, held out)",
        "",
        "| | Accuracy |",
        "|---|---|",
        f"| First question | {s['turn1_accuracy']}% |",
        f"| **Follow-up, with conversation history** | **{s['followup_accuracy_with_history']}%** |",
        f"| Follow-up, with history, when the first answer was right | {s['followup_accuracy_with_history_when_turn1_correct']}% |",
        f"| Follow-up asked alone (no history) | {s['followup_accuracy_without_history']}% |",
        "",
        f"Follow-ups backed by a query in their own turn: {s['grounded_rate_followups_with_history']}%. "
        f"Median follow-up latency {s['median_latency_s_followup_with_history']} s; prompt tokens "
        f"{s['avg_prompt_tokens_followup_with_vs_without'][0]} with history vs "
        f"{s['avg_prompt_tokens_followup_with_vs_without'][1]} without.",
        "",
    ]))
    print(f"Wrote {out.relative_to(HERE.parent)} and evals/FOLLOWUPS.md")


if __name__ == "__main__":
    main()
