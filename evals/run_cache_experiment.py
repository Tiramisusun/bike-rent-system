"""Does moving the timestamp to the end of the system prompt raise prompt-cache hits?

    python -m evals.run_cache_experiment --model gpt-luna
    python -m evals.run_cache_experiment --report          # -> CACHE.md from results/cache/

Providers cache the longest prefix a prompt shares with recent requests. The old prompt
put "Current time in Dublin: <minute>" before the schema (most of the prompt), so
after a minute only the short rules block could match. Real users ask minutes apart, so the
benchmark (questions back to back) hides this. Here every question is asked once with
the old prompt (A) and once with the new one (B), alternating, `--gap` seconds apart:
each variant sees one request every 2 x gap seconds, like sparse real traffic, and both
variants share the same time of day.
"""

import argparse
import json
import statistics
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from evals.run_eval import _gold, load_models, make_model_client
from src.agent import agent
from src.agent.evaluation import cost_usd, results_match
from src.agent.semantic_layer import build_schema_context
from src.warehouse.config import agent_engine

HERE = Path(__file__).resolve().parent
OUT = HERE / "results" / "cache"
QUESTION_IDS = ["e01", "e04", "e10", "m01", "m03", "m05", "m09", "m15", "h02", "h04", "h07", "h15"]

# The system prompt before the change (variant A), kept verbatim for the comparison.
OLD_SYSTEM_PROMPT = agent.SYSTEM_PROMPT.replace(
    "Warehouse:\n{schema}\n\nCurrent time in Dublin: {now}\n",
    "Current time in Dublin: {now}\n\nWarehouse:\n{schema}\n",
)
assert OLD_SYSTEM_PROMPT != agent.SYSTEM_PROMPT, "prompt layout changed; update OLD_SYSTEM_PROMPT"


@contextmanager
def system_prompt(text):
    saved = agent.SYSTEM_PROMPT
    agent.SYSTEM_PROMPT = text
    try:
        yield
    finally:
        agent.SYSTEM_PROMPT = saved


def run(model_name: str, gap: float) -> Path:
    cfg = load_models()[model_name]
    client = make_model_client(cfg)
    engine = agent_engine()
    _, tables = build_schema_context(engine)
    questions = [q for q in yaml.safe_load((HERE / "benchmark.yaml").read_text()) if q["id"] in QUESTION_IDS]
    gold = {q["id"]: _gold(engine, tables, q) for q in questions}
    variants = {"A_time_first": OLD_SYSTEM_PROMPT, "B_time_last": agent.SYSTEM_PROMPT}

    rows = []
    for i, q in enumerate(questions, 1):
        for variant, prompt in variants.items():
            with system_prompt(prompt):
                r = agent.ask(q["question"], engine, client=client, model=cfg["model"],
                              request_options=cfg.get("request_options") or {})
            rows.append({
                "id": q["id"], "variant": variant, "asked_at": datetime.now(timezone.utc).isoformat(),
                "correct": r.sql is not None and results_match(gold[q["id"]], r.rows, bool(q.get("order_matters"))),
                "prompt_tokens": r.prompt_tokens, "cached_prompt_tokens": r.cached_prompt_tokens,
                "completion_tokens": r.completion_tokens, "latency_s": r.latency_s, "error": r.error,
                "cost_usd": cost_usd(r.prompt_tokens, r.cached_prompt_tokens, r.completion_tokens, cfg["price"]),
            })
            print(f"[{model_name} {i}/{len(questions)}] {variant}: cached "
                  f"{r.cached_prompt_tokens}/{r.prompt_tokens}, correct={rows[-1]['correct']}", flush=True)
            time.sleep(gap)

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{model_name}-{datetime.now(timezone.utc):%Y%m%d-%H%M}.json"
    path.write_text(json.dumps({"model": cfg["model"], "model_name": model_name, "gap_s": gap,
                                "price_per_1m_usd": cfg["price"], "rows": rows}, indent=2))
    print(f"Wrote {path.relative_to(HERE.parent)}")
    return path


def summarise(rows) -> dict:
    prompt = sum(r["prompt_tokens"] for r in rows)
    return {
        "questions": len(rows),
        "correct": sum(r["correct"] for r in rows),
        "errors": sum(bool(r["error"]) for r in rows),
        "cache_hit_share": round(sum(r["cached_prompt_tokens"] for r in rows) / max(1, prompt), 3),
        "avg_prompt_tokens": round(prompt / max(1, len(rows))),
        "cost_per_1000_usd": round(1000 * statistics.mean(r["cost_usd"] for r in rows), 3),
        "median_latency_s": round(statistics.median(r["latency_s"] for r in rows), 2),
    }


def write_report(path: Path):
    lines = [
        "# Prompt caching: timestamp before vs after the schema",
        "",
        "Same questions, model and data; only the position of the per-minute timestamp in the system",
        "prompt changes. Questions alternate A/B with a gap, so each variant sees sparse traffic like",
        "real users (method in `run_cache_experiment.py`). Cost at list prices (`models.yaml`).",
        "",
        "| Model | Variant | Gap per variant | Cache hits | Cost / 1,000 questions | Correct | Median latency |",
        "|---|---|---|---|---|---|---|",
    ]
    for f in sorted(OUT.glob("*.json")):
        d = json.loads(f.read_text())
        for variant in ("A_time_first", "B_time_last"):
            s = summarise([r for r in d["rows"] if r["variant"] == variant])
            label = "A: time before schema (old)" if variant.startswith("A") else "**B: time after schema (new)**"
            lines.append(f"| `{d['model']}` | {label} | {2 * d['gap_s']:.0f} s | {round(100 * s['cache_hit_share'])}% | "
                         f"${s['cost_per_1000_usd']} | {s['correct']}/{s['questions']} | {s['median_latency_s']} s |")

    # 12 questions can't show an accuracy change; the full benchmark with the new prompt can.
    accuracy = sorted((OUT / "accuracy-time-last").glob("*.json"))
    if accuracy:
        acc = [json.loads(f.read_text())["summaries"]["docs"]["accuracy"] for f in accuracy]
        model = json.loads(accuracy[0].read_text())["meta"]["model"]
        lines += ["", "## Accuracy with the new prompt", "",
                  f"Full 50-question benchmark, `{model}`, {len(acc)} runs: **{statistics.mean(acc):.1f}%** "
                  f"({min(acc)}–{max(acc)}), against the old prompt's runs in `MODELS.md`."]

    lines += ["", "## Reading", "",
              "Cached tokens per question are logged per request (`results/cache/`). Where the variant",
              "matters, B's extra hits are the schema reused from the previous question; hits shared by A",
              "and B are the later calls within one question, which repeat its first call's prompt."]
    path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {path.relative_to(HERE.parent)}")


def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="a name from evals/models.yaml")
    parser.add_argument("--gap", type=float, default=35, help="seconds between requests (A and B alternate)")
    parser.add_argument("--report", action="store_true", help="only rebuild CACHE.md from saved runs")
    args = parser.parse_args()
    if not args.report:
        if not args.model:
            raise SystemExit("--model is required unless --report")
        run(args.model, args.gap)
    write_report(HERE / "CACHE.md")


if __name__ == "__main__":
    main()
