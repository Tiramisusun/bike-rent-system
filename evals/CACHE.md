# Prompt caching: timestamp before vs after the schema

Same questions, model and data; only the position of the per-minute timestamp in the system
prompt changes. Questions alternate A/B with a gap, so each variant sees sparse traffic like
real users (method in `run_cache_experiment.py`). Cost at list prices (`models.yaml`).

| Model | Variant | Gap per variant | Cache hits | Cost / 1,000 questions | Correct | Median latency |
|---|---|---|---|---|---|---|
| `deepseek-v4-pro` | A: time before schema (old) | 70 s | 56% | $3.547 | 10/12 | 3.58 s |
| `deepseek-v4-pro` | **B: time after schema (new)** | 70 s | 84% | $1.885 | 10/12 | 3.82 s |
| `gpt-6-luna` | A: time before schema (old) | 70 s | 48% | $0.251 | 12/12 | 3.56 s |
| `gpt-6-luna` | **B: time after schema (new)** | 70 s | 48% | $0.25 | 12/12 | 3.88 s |

## Accuracy with the new prompt

Full 50-question benchmark, `gpt-6-luna`, 3 runs: **95.3%** (94.0–96.0), against the old prompt's runs in `MODELS.md`.

## Reading

Cached tokens per question are logged per request (`results/cache/`). Where the variant
matters, B's extra hits are the schema reused from the previous question; hits shared by A
and B are the later calls within one question, which repeat its first call's prompt.
