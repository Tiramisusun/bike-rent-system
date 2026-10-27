"""Summarise the model comparison runs into evals/MODELS.md.

    python -m evals.compare_models

Reads every results/compare/<model>-<lang>-<stamp>-r<run>.json written by
`run_eval --model ...` (smoke tests in results/compare/smoke/ are ignored).
One run of 50 questions moves by several points on its own, so each model is
reported as the mean and range over its runs, plus a per-question view: a
question counts as solved when the model got it right in most runs.
"""

import json
import statistics
from collections import defaultdict
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
LANG_NAMES = {"en": "English", "de": "German", "zh": "Chinese"}


def load_runs() -> dict:
    """{(model_name, lang): [run, ...]} for the docs condition."""
    runs = defaultdict(list)
    for path in sorted((HERE / "results" / "compare").glob("*.json")):
        data = json.loads(path.read_text())
        if "docs" in data["summaries"]:
            runs[(data["meta"]["model_name"], data["meta"]["lang"])].append(data)
    return runs


def _mean(xs, nd=1):
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), nd) if xs else None


def model_row(name, runs) -> dict:
    s = [r["summaries"]["docs"] for r in runs]
    acc = [x["accuracy"] for x in s]
    adversarial = next((r for r in runs if r.get("adversarial") is not None), None)
    return {
        "model": name,
        "model_id": runs[0]["meta"]["model"],
        "runs": len(runs),
        "acc_mean": _mean(acc), "acc_min": min(acc), "acc_max": max(acc),
        "easy": _mean(x["by_difficulty"]["easy"] for x in s),
        "medium": _mean(x["by_difficulty"]["medium"] for x in s),
        "hard": _mean(x["by_difficulty"]["hard"] for x in s),
        "p50": _mean((x["median_latency_s"] for x in s), 2),
        "p90": _mean((x["p90_latency_s"] for x in s), 2),
        "cost_q": _mean((x.get("cost_per_question_usd") for x in s), 5),
        "cost_1k": _mean((x.get("cost_per_1000_questions_usd") for x in s), 2),
        "cost_correct": _mean((x.get("cost_per_correct_answer_usd") for x in s), 5),
        "cache": _mean((x.get("cache_hit_share") for x in s), 3),
        "reasoning": round(_mean(x.get("avg_reasoning_tokens") for x in s) or 0),
        "timeouts": sum(x.get("timeouts", 0) for x in s),
        # a timeout also sets the error field; count the other failures separately
        "errors": sum(x["provider_errors"] - x.get("timeouts", 0) for x in s),
        "tables_changed": None if adversarial is None else len(adversarial["changed_tables"]),
        "adversarial_n": None if adversarial is None else len(adversarial["adversarial"]),
    }


def solved(runs) -> dict:
    """{question_id: fraction of runs answered correctly}"""
    hits = defaultdict(list)
    for r in runs:
        for row in r["details"]["docs"]:
            hits[row["id"]].append(row["correct"])
    return {q: sum(v) / len(v) for q, v in hits.items()}


def _fmt(v, prefix="", suffix=""):
    return "–" if v is None else f"{prefix}{v}{suffix}"


def _usd(v):
    if v is None:
        return "–"
    return f"${v:.5f}" if v < 0.01 else f"${v:.2f}"


def write_report(runs, path):
    en = {m: rs for (m, lang), rs in runs.items() if lang == "en"}
    rows = sorted((model_row(m, rs) for m, rs in en.items()), key=lambda r: -r["acc_mean"])
    first = next(iter(en.values()))[0]["meta"]
    models_cfg = yaml.safe_load((HERE / "models.yaml").read_text())["models"]

    lines = [
        "# Model comparison",
        "",
        f"Same agent, prompt, tools and guardrails; only the model changes. {first['n_questions']} benchmark "
        f"questions (`benchmark.yaml`), scored by execution accuracy. {first['data_range']}",
        "",
        "## Accuracy, latency and cost (English)",
        "",
        "| Model | Runs | Accuracy, mean (range) | Easy | Medium | Hard | Median latency | p90 | "
        "Cost / question | Cost / 1,000 | Cost / correct answer | Cache hits | Reasoning tokens / q |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['model_id']}` | {r['runs']} | **{r['acc_mean']}%** ({r['acc_min']}–{r['acc_max']}) | "
            f"{r['easy']}% | {r['medium']}% | {r['hard']}% | {r['p50']} s | {r['p90']} s | "
            f"{_usd(r['cost_q'])} | {_usd(r['cost_1k'])} | {_usd(r['cost_correct'])} | "
            f"{_fmt(None if r['cache'] is None else round(100 * r['cache']), suffix='%')} | {r['reasoning']} |")

    lines += ["", "Timeouts (60 s budget) and provider errors count as wrong answers.", ""]
    lines += [f"- `{r['model_id']}`: {r['timeouts']} timed out, {r['errors']} other provider "
              f"errors, over {r['runs']} runs of {first['n_questions']}" for r in rows if r["timeouts"] or r["errors"]]

    lines += ["", "## Safety: adversarial prompts", "",
              "Every warehouse table is fingerprinted before and after the 15 prompts (drop tables, "
              "read the user table, change data, prompt injection).", "",
              "| Model | Tables changed |", "|---|---|"]
    lines += [f"| `{r['model_id']}` | {_fmt(r['tables_changed'])} / {_fmt(r['adversarial_n'])} prompts |"
              for r in rows]

    # Per-question agreement: which questions separate the models?
    per_q = {r["model"]: solved(en[r["model"]]) for r in rows}
    ids = sorted(next(iter(per_q.values())))
    by_all = [q for q in ids if all(per_q[m].get(q, 0) > 0.5 for m in per_q)]
    by_none = [q for q in ids if all(per_q[m].get(q, 0) <= 0.5 for m in per_q)]
    flaky = {m: sum(0 < v < 1 for v in per_q[m].values()) for m in per_q}
    lines += ["", "## Per question", "",
              f"- Solved by every model (right in most runs): {len(by_all)} / {len(ids)}",
              f"- Solved by no model: {len(by_none)} — {', '.join(by_none) or 'none'}",
              "- Questions a model got right in some runs but not others: "
              + ", ".join(f"`{models_cfg[m]['model']}` {n}" for m, n in flaky.items()),
              ""]

    multi = sorted({m for (m, lang) in runs if lang != "en"})
    if multi:
        lines += ["## Multilingual", "",
                  "Same questions and gold SQL; only the question text is translated "
                  "(`benchmark_i18n.yaml`).", "",
                  "| Model | " + " | ".join(LANG_NAMES[l] for l in LANG_NAMES) + " |",
                  "|---|" + "---|" * len(LANG_NAMES)]
        for m in multi:
            cells = []
            for lang in LANG_NAMES:
                rs = runs.get((m, lang))
                if not rs:
                    cells.append("–")
                    continue
                acc = [r["summaries"]["docs"]["accuracy"] for r in rs]
                cells.append(f"{_mean(acc)}% ({min(acc)}–{max(acc)}, {len(rs)} runs)")
            lines.append(f"| `{models_cfg[m]['model']}` | " + " | ".join(cells) + " |")
        lines.append("")

    lines += [
        "## Notes",
        "",
        "- Costs are list prices (USD per 1M tokens, checked 2026-10-27, sources in `models.yaml`), "
        "not what was billed. MiMo publishes no cache-hit price, so its cached tokens are charged at "
        "the full input price (an upper bound). DeepSeek is priced at peak hours; off-peak is half.",
        "- The OpenAI models run with `reasoning_effort: none`: on `/v1/chat/completions` they reject "
        "function tools while reasoning is on. The MiMo and DeepSeek models reason.",
        "- Questions run three at a time, close together, so prompt-cache hit rates here are higher "
        "than for real traffic, where questions arrive minutes apart.",
        "- German translations are not reviewed by a native speaker.",
        "- Runs hit by a provider rate limit or by the laptop sleeping were re-run; the originals "
        "are in `results/compare/excluded/` with the reason.",
        "- The scorer compares values, so an equivalent answer with different labels counts as wrong "
        "(e.g. groups named 'peak' / 'outside_peak' where the gold result has true / false). This "
        "rule is the same for every model, but one that relabels more often is penalised more.",
    ]
    path.write_text("\n".join(lines) + "\n")


def main():
    runs = load_runs()
    if not runs:
        raise SystemExit("No results in evals/results/compare/ — run evals.run_eval --model ... first")
    write_report(runs, HERE / "MODELS.md")
    print("Wrote evals/MODELS.md")


if __name__ == "__main__":
    main()
