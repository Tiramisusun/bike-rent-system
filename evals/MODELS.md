# Model comparison

Same agent, prompt, tools and guardrails; only the model changes. 50 benchmark questions (`benchmark.yaml`), scored by execution accuracy. Station snapshots cover 2026-04-11 00:30 to 2026-10-08 14:09 (Dublin local time).

## Accuracy, latency and cost (English)

| Model | Runs | Accuracy, mean (range) | Easy | Medium | Hard | Median latency | p90 | Cost / question | Cost / 1,000 | Cost / correct answer | Cache hits | Reasoning tokens / q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `gpt-6-luna` | 3 | **96.0%** (94.0–98.0) | 100.0% | 96.7% | 91.1% | 2.91 s | 4.2 s | $0.00009 | $0.09 | $0.00009 | 95% | 0 |
| `deepseek-v4-pro` | 3 | **91.3%** (90.0–92.0) | 95.5% | 86.7% | 93.3% | 3.85 s | 5.86 s | $0.00151 | $1.51 | $0.00165 | 93% | 111 |
| `gpt-6.1-terra` | 3 | **89.3%** (88.0–92.0) | 97.8% | 95.0% | 73.3% | 3.15 s | 3.92 s | $0.00081 | $0.81 | $0.00091 | 94% | 0 |
| `mimo-v2.6-pro` | 3 | **80.0%** (76.0–82.0) | 88.9% | 80.0% | 71.1% | 7.4 s | 10.44 s | $0.00177 | $1.77 | $0.00222 | 80% | 41 |
| `mimo-v2.6-flash` | 3 | **78.0%** (76.0–82.0) | 86.7% | 78.3% | 68.9% | 2.99 s | 6.43 s | $0.00058 | $0.58 | $0.00075 | 91% | 41 |
| `deepseek-flash` | 3 | **68.7%** (66.0–70.0) | 73.3% | 71.7% | 60.0% | 2.45 s | 3.96 s | $0.00044 | $0.44 | $0.00064 | 88% | 64 |

Timeouts (60 s budget) and provider errors count as wrong answers.

- `gpt-6.1-terra`: 4 timed out, 0 other provider errors, over 3 runs of 50

## Safety: adversarial prompts

Every warehouse table is fingerprinted before and after the 15 prompts (drop tables, read the user table, change data, prompt injection).

| Model | Tables changed |
|---|---|
| `gpt-6-luna` | 0 / 15 prompts |
| `deepseek-v4-pro` | 0 / 15 prompts |
| `gpt-6.1-terra` | 0 / 15 prompts |
| `mimo-v2.6-pro` | 0 / 15 prompts |
| `mimo-v2.6-flash` | 0 / 15 prompts |
| `deepseek-flash` | 0 / 15 prompts |

## Per question

- Solved by every model (right in most runs): 32 / 50
- Solved by no model: 0 — none
- Questions a model got right in some runs but not others: `gpt-6-luna` 4, `deepseek-v4-pro` 5, `gpt-6.1-terra` 3, `mimo-v2.6-pro` 6, `mimo-v2.6-flash` 4, `deepseek-flash` 9

## Multilingual

Same questions and gold SQL; only the question text is translated (`benchmark_i18n.yaml`).

| Model | English | German | Chinese |
|---|---|---|---|
| `deepseek-v4-pro` | 91.3% (90.0–92.0, 3 runs) | 89.3% (88.0–90.0, 3 runs) | 89.3% (88.0–92.0, 3 runs) |
| `gpt-6-luna` | 96.0% (94.0–98.0, 3 runs) | 97.3% (96.0–98.0, 3 runs) | 95.3% (94.0–96.0, 3 runs) |
| `mimo-v2.6-pro` | 80.0% (76.0–82.0, 3 runs) | 75.3% (70.0–78.0, 3 runs) | 78.0% (74.0–80.0, 3 runs) |

## Multi-turn follow-ups

12 question + follow-up pairs (`followups.yaml`), one run each; the deployed model's run is in `FOLLOWUPS.md`.

| Model | First question | Follow-up with history | Follow-up alone | Median follow-up latency |
|---|---|---|---|---|
| `gpt-6-luna` | 100.0% | **100.0%** | 25.0% | 3.04 s |

## Notes

- Costs are list prices (USD per 1M tokens, checked 2026-10-27, sources in `models.yaml`), not what was billed. MiMo publishes no cache-hit price, so its cached tokens are charged at the full input price (an upper bound). DeepSeek is priced at peak hours; off-peak is half.
- The OpenAI models run with `reasoning_effort: none`: on `/v1/chat/completions` they reject function tools while reasoning is on. The MiMo and DeepSeek models reason.
- Questions run three at a time, close together, so prompt-cache hit rates here are higher than for real traffic, where questions arrive minutes apart.
- German translations are not reviewed by a native speaker.
- Runs hit by a provider rate limit or by the laptop sleeping were re-run; the originals are in `results/compare/excluded/` with the reason.
- The scorer compares values, so an equivalent answer with different labels counts as wrong (e.g. groups named 'peak' / 'outside_peak' where the gold result has true / false). This rule is the same for every model, but one that relabels more often is penalised more.
