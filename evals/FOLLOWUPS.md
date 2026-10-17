# Multi-turn evaluation

- Run: 2026-10-17 12:52 UTC · model `mimo-v2.6-pro` · 12 question + follow-up pairs (`followups.yaml`, held out)

| | Accuracy |
|---|---|
| First question | 75.0% |
| **Follow-up, with conversation history** | **91.7%** |
| Follow-up, with history, when the first answer was right | 88.9% |
| Follow-up asked alone (no history) | 16.7% |

Follow-ups backed by a query in their own turn: 100.0%. Median follow-up latency 17.49 s; prompt tokens 4281 with history vs 3518 without.
