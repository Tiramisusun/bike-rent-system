# Text-to-SQL evaluation

```bash
python -m evals.run_eval                    # 50 questions x 2 conditions + 15 adversarial prompts
python -m evals.run_eval --conditions docs --ids e01,m03 --no-adversarial

# Model comparison: models in models.yaml (base URL, key variable, list prices)
python -m evals.run_eval --model gpt-luna --conditions docs --repeat 3 [--lang de|zh]
python -m evals.run_followups --model gpt-luna
python -m evals.compare_models            # -> MODELS.md
```

Writes `RESULTS.md` (summary, overwritten each run) and `results/<timestamp>.json` (every question:
SQL, rows, answer, attempts, latency, tokens).

## Method

- **Benchmark** (`benchmark.yaml`): 50 questions over the marts — 15 easy (lookups, counts),
  20 medium (grouping, aggregates), 15 hard (business metrics, multi-table joins, windows).
  Each has hand-written gold SQL, validated against the warehouse and checked for ties at
  ranking cut-offs.
- **Execution accuracy**: the agent's final result set is compared with the gold result set,
  computed at eval time (`src/agent/evaluation.py`). Extra columns, column order, row order
  (unless the question asks for a ranking), 1 % numeric differences and ratio-vs-percentage
  are tolerated; **a different number of rows is not**.
- **Ablation**: `docs` gives the model the dbt column descriptions, metric definitions and
  business rules; `schema` gives table and column names and types only.
- **Adversarial** (`adversarial.yaml`): 15 prompts asking the agent to write, escape the marts
  schema, read user data or tie up the database. A write is detected by fingerprinting every
  warehouse table (row count + content hash) before and after, over a separate privileged
  connection — independent of what the agent reports.

The scorer itself was checked with scripted fake models: an oracle that runs the gold SQL scores
100 %, a model that always returns a wrong query scores 0 %, and one that fails first and then
corrects itself is scored correct with 50/50 recoveries.

## Run of 2026-10-08 (mimo-v2.6-pro) — error analysis

Execution accuracy **80 %** with docs vs **68 %** schema-only; 0 of 15 adversarial prompts changed
any table. All 10 misses in the `docs` condition were read by hand:

| Cause | Questions | What happened |
|---|---|---|
| Correct answer plus context rows | m09, m19, h01, h02, h06, h09, e13, h15 | Asked for the top station/zone/hour, returned a ranked top-5 (or every group) whose first row is right; the written answer is correct. Strict row-count scoring counts these as wrong. |
| Ambiguous question | m18 | "The last hour of the data" read as the last clock hour (109 stations) instead of the last 60 minutes (113). The question should say which. |
| Over-broad filter | e05 | `ILIKE '%SMITHFIELD%'` also matched the separate SMITHFIELD station; the answer named the right zone. |

So 9 of the 10 strict misses came with a correct natural-language answer. The score is kept strict
on purpose: tuning the prompt against these same 50 questions and re-scoring would overstate
accuracy. A fair improvement needs a fresh, held-out question set.

No query in this run failed, so the error-feedback retry loop was not exercised by the benchmark;
it is covered by unit tests (`tests/test_agent.py`) and by the scorer check above.

## Model comparison (2026-10-27)

Full results in [MODELS.md](MODELS.md); every run's JSON is in `results/compare/`.

- **Models**: two per provider — Xiaomi `mimo-v2.6-pro` / `mimo-v2.6-flash`, DeepSeek `deepseek-v4-pro` /
  `deepseek-flash`, OpenAI `gpt-6.1-terra` / `gpt-6-luna`. Same agent, prompt, tools, guardrails and frozen
  data (the local Airflow scheduler was paused so the gold answers could not move between models).
- **Runs**: 3 per model, because one run of 50 questions moves by 2–6 points on its own; reported as mean
  and range, plus which questions each model solves in most runs. The adversarial set ran once per model.
- **Cost**: tokens per question from the API's usage field — including cache hits and reasoning tokens —
  times the list prices in `models.yaml` (sources and date recorded there). Also reported per correct answer.
- **Languages**: all 50 questions in German and Chinese (`benchmark_i18n.yaml`, same gold SQL) for each of the three
  providers' most accurate models in English. Chinese reviewed by a native speaker; German not.
- **Excluded runs**: four runs hit a provider rate limit (HTTP 429) or the laptop sleeping; they were re-run and
  the originals kept in `results/compare/excluded/` with the reason.

Result: `gpt-6-luna` — the cheapest model — was the most accurate (96.0% English, 97.3% German, 95.3%
Chinese) at $0.09 per 1,000 questions, against 80.0% and $1.77 for `mimo-v2.6-pro`, which the site used
before; it also answered 12/12 multi-turn follow-ups (`mimo-v2.6-pro`: 11/12). No model changed any table.

Caveats: the OpenAI models ran with reasoning off (their chat-completions endpoint rejects tools while
reasoning is on); prompt-cache hit rates are higher than in real traffic because questions ran back to back;
the scorer compares values, so equivalent answers with different labels (e.g. 'peak' vs `true`) count as wrong.
