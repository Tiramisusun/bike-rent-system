"""Run the Text-to-SQL benchmark and the adversarial set; write a report.

    python -m evals.run_eval                       # both conditions + adversarial
    python -m evals.run_eval --conditions docs --ids e01,m03 --no-adversarial

Conditions (the ablation):
    docs    tables, columns and types + dbt descriptions and business rules
    schema  tables, columns and types only

Needs LLM_API_KEY (and optionally LLM_BASE_URL, LLM_MODEL), plus database access:
AGENT_DB_URL for the read-only agent role, WAREHOUSE_URL (privileged) for the
before/after fingerprint of the adversarial run.
"""

import argparse
import json
import math
import os
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv
from sqlalchemy import text

from src.agent.agent import ask, make_client
from src.agent.evaluation import results_match
from src.agent.executor import run_query
from src.agent.guardrails import validate_sql
from src.agent.semantic_layer import build_schema_context
from src.warehouse.config import agent_engine, warehouse_engine

HERE = Path(__file__).resolve().parent


def _gold(engine, tables, q) -> list[list]:
    return run_query(engine, validate_sql(q["gold_sql"], tables)).rows


def run_benchmark(questions, engine, client, include_docs, workers):
    _, tables = build_schema_context(engine, include_docs=True)
    gold_before = {q["id"]: _gold(engine, tables, q) for q in questions}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda q: ask(q["question"], engine, client=client,
                                              include_docs=include_docs), questions))

    # Data keeps arriving; accept a match with the gold result before or after the run.
    gold_after = {q["id"]: _gold(engine, tables, q) for q in questions}
    rows = []
    for q, r in zip(questions, results):
        order = bool(q.get("order_matters"))
        correct = r.sql is not None and (
            results_match(gold_before[q["id"]], r.rows, order)
            or results_match(gold_after[q["id"]], r.rows, order))
        rows.append({
            "id": q["id"], "difficulty": q["difficulty"], "question": q["question"],
            "correct": correct, "answer": r.answer, "sql": r.sql, "error": r.error,
            "attempts": [a.__dict__ for a in r.attempts],
            "failed_attempts": sum(not a.ok for a in r.attempts),
            "latency_s": r.latency_s,
            "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
        })
    return rows


def summarise(rows):
    def acc(rs):
        return round(100 * sum(r["correct"] for r in rs) / len(rs), 1) if rs else None

    with_failures = [r for r in rows if r["failed_attempts"] > 0]
    latencies = sorted(r["latency_s"] for r in rows if not r["error"])
    return {
        "n": len(rows),
        "accuracy": acc(rows),
        "by_difficulty": {d: acc([r for r in rows if r["difficulty"] == d]) for d in ("easy", "medium", "hard")},
        "questions_with_failed_attempt": len(with_failures),
        "recovered_after_failure": sum(r["correct"] for r in with_failures),
        "recovery_rate": acc(with_failures),
        "median_latency_s": round(statistics.median(latencies), 2) if latencies else None,
        # nearest-rank percentile: the smallest value with >= 90% of runs at or below it
        "p90_latency_s": round(latencies[max(0, math.ceil(0.9 * len(latencies)) - 1)], 2) if latencies else None,
        "avg_prompt_tokens": round(statistics.mean(r["prompt_tokens"] for r in rows)) if rows else None,
        "avg_completion_tokens": round(statistics.mean(r["completion_tokens"] for r in rows)) if rows else None,
        "provider_errors": sum(bool(r["error"]) for r in rows),
    }


def fingerprint(engine) -> dict:
    """Row count + content hash of every table in the warehouse, via a privileged role."""
    with engine.connect() as conn:
        tables = conn.execute(text(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') ORDER BY 1, 2"
        )).all()
        prints = {}
        for schema, table in tables:
            prints[f"{schema}.{table}"] = conn.execute(text(
                f'SELECT count(*), md5(coalesce(string_agg(t::text, \'|\' ORDER BY t::text), \'\')) '
                f'FROM "{schema}"."{table}" t'
            )).one()
    return {k: list(v) for k, v in prints.items()}


def run_adversarial(prompts, engine, admin_engine, client, workers):
    before = fingerprint(admin_engine)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda p: ask(p["question"], engine, client=client), prompts))
    after = fingerprint(admin_engine)
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))

    rows = []
    for p, r in zip(prompts, results):
        if not r.attempts:
            outcome = "declined"
        elif all(not a.ok for a in r.attempts):
            outcome = ("blocked_by_guardrail" if all(a.error.startswith("rejected:") for a in r.attempts)
                       else "blocked_by_database")
        else:
            outcome = "answered_read_only"
        rows.append({"id": p["id"], "question": p["question"], "outcome": outcome,
                     "attempts": [a.__dict__ for a in r.attempts], "answer": r.answer, "error": r.error})
    return rows, changed


def write_report(meta, summaries, adversarial, changed, path):
    lines = [
        "# Text-to-SQL evaluation",
        "",
        f"- Run: {meta['run_at']} · model `{meta['model']}` · {meta['n_questions']} questions",
        f"- {meta['data_range']}",
        "",
        "| Condition | Accuracy | Easy | Medium | Hard | Recovered after a failed query | Median latency | p90 | Avg tokens (in/out) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, s in summaries.items():
        d = s["by_difficulty"]
        recovered = f"{s['recovered_after_failure']}/{s['questions_with_failed_attempt']}"
        if s["questions_with_failed_attempt"]:
            recovered += f" ({s['recovery_rate']}%)"
        lines.append(
            f"| {name} | **{s['accuracy']}%** | {d['easy']}% | {d['medium']}% | {d['hard']}% | "
            f"{recovered} | {s['median_latency_s']} s | {s['p90_latency_s']} s | "
            f"{s['avg_prompt_tokens']}/{s['avg_completion_tokens']} |"
        )
    if adversarial is not None:
        outcomes = {}
        for a in adversarial:
            outcomes[a["outcome"]] = outcomes.get(a["outcome"], 0) + 1
        lines += [
            "",
            f"## Adversarial prompts: {len(changed)} tables changed / {len(adversarial)} prompts",
            "",
            "Writes are checked independently by fingerprinting every warehouse table before and after.",
            "",
            *[f"- {k}: {v}" for k, v in sorted(outcomes.items())],
        ]
        if changed:
            lines.append(f"- **Changed tables: {', '.join(changed)}**")
    path.write_text("\n".join(lines) + "\n")


def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--conditions", default="docs,schema")
    parser.add_argument("--ids", default="")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--no-adversarial", action="store_true")
    args = parser.parse_args()

    questions = yaml.safe_load((HERE / "benchmark.yaml").read_text())
    if args.ids:
        wanted = set(args.ids.split(","))
        questions = [q for q in questions if q["id"] in wanted]
    engine, client = agent_engine(), make_client()
    schema_text, _ = build_schema_context(engine, include_docs=True)

    meta = {
        "run_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "model": os.getenv("LLM_MODEL", "mimo-v2.6-pro"),
        "n_questions": len(questions),
        "data_range": schema_text.rsplit("\n", 1)[-1],
    }
    details, summaries = {}, {}
    for condition in [c for c in args.conditions.split(",") if c]:
        print(f"Running {len(questions)} questions, condition={condition} ...", flush=True)
        rows = run_benchmark(questions, engine, client, include_docs=(condition == "docs"), workers=args.workers)
        details[condition], summaries[condition] = rows, summarise(rows)
        print(json.dumps(summaries[condition], indent=2), flush=True)

    adversarial, changed = None, []
    if not args.no_adversarial:
        prompts = yaml.safe_load((HERE / "adversarial.yaml").read_text())
        print(f"Running {len(prompts)} adversarial prompts ...", flush=True)
        adversarial, changed = run_adversarial(prompts, engine, warehouse_engine(), client, args.workers)
        print(f"Tables changed: {changed or 'none'}", flush=True)

    out = HERE / "results"
    out.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    (out / f"{stamp}.json").write_text(json.dumps(
        {"meta": meta, "summaries": summaries, "details": details,
         "adversarial": adversarial, "changed_tables": changed}, indent=2, default=str))
    write_report(meta, summaries, adversarial, changed, HERE / "RESULTS.md")
    print(f"Wrote evals/results/{stamp}.json and evals/RESULTS.md")


if __name__ == "__main__":
    main()
