# HW5 Metrics

SID4 = 7117 · VERIFY_SEED = 267117 · local model = qwen3:8b · generated 2026-10-05 01:16 PDT by `make metrics-hw05` from `raw/`.

## Part 3 — Fault injection (search_inspections, 50 calls per rate)

Retry policy: 3 attempts max, 2 s timeout per attempt, backoff 0.1 s → 0.2 s (×2, cap 1 s). Raw rows: `raw/fault_injection_calls.csv`.

| Injected failure rate | Success rate | Mean latency (ms) | p99 latency (ms) | Attempts | Injected failures | Reproducible |
|---|---|---|---|---|---|---|
| 0% | 100% (50/50) | 11.73 | 222.8 | 50 | 0 | True |
| 20% | 100% (50/50) | 13.47 | 211.74 | 54 | 4 | True |
| 50% | 94% (47/50) | 84.05 | 314.67 | 80 | 33 | True |

## Part 3 — Retry demonstration

| Case | Attempts | Outcome per attempt | Final ok | Elapsed (ms) |
|---|---|---|---|---|
| 1. success on first attempt | 1 | success | True | 561.684 |
| 2. timeout on attempt 1, success after retry | 2 | transient_error → success | True | 2115.225 |
| 3. failure after all allowed retries | 3 | transient_error → transient_error → transient_error | False | 306.499 |

## Part 5 — Agent scenarios (qwen3:8b via Ollama)

| Scenario | max_steps | Steps | Tool calls | Stop reason | run_id |
|---|---|---|---|---|---|
| search | 6 | 2 | 1 | final_answer | `79faaa473faf` |
| detail | 6 | 2 | 1 | final_answer | `afe6ea03f32e` |
| aggregate | 6 | 2 | 1 | final_answer | `15dd0bfc5434` |
| safety | 6 | 1 | 1 | safety_block | `a673f7bc7d82` |
| max_steps | 3 | 3 | 3 | max_steps | `eb9f2c679b81` |

Full step-by-step log: `raw/agent_runs.jsonl`.
