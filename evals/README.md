# Text-to-SQL evaluation

```bash
python -m evals.run_eval                    # 50 questions x 2 conditions + 15 adversarial prompts
python -m evals.run_eval --conditions docs --ids e01,m03 --no-adversarial
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
