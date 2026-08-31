# HW01 Metrics — Planner/Reviewer Non-Determinism Study

Fixed input (`reports/hw01/cases/nondeterminism_input.json`, title: "Routine Health Inspection - FA0206933 - YUMMY KITCHEN"), run through the real Planner -> Reviewer -> Publish pipeline (`qwen3:8b` via Ollama) 20 times at each of temperature=0.7 and temperature=0.0 (40 runs total). Source data: [raw/nondeterminism_runs.json](raw/nondeterminism_runs.json), [raw/nondeterminism_runs.csv](raw/nondeterminism_runs.csv). Full console transcript: [RUN_LOG.txt](RUN_LOG.txt).

## Temperature = 0.7

- Runs completed: 20/20 (0 failed)
- Distinct tag sets produced: **3**
- Tags that appeared in all 20 runs: `health inspection`
- Tags that appeared in exactly one run: `handwashing signage`

| Latency (n=19) | p50 | p95 | p99 |
|---|---|---|---|
| ms | 24656.0 | 28790.1 | 29374.0 |

> Excluded from the latency stats above: run 19 (23,302,721 ms) — latency this many multiples (5x+) above the group median indicates the host machine slept mid-call (wall-clock time includes sleep time), not real model latency. Still included in the tag-set analysis above and present in the raw data.

## Temperature = 0.0

- Runs completed: 20/20 (0 failed)
- Distinct tag sets produced: **1**
- Tags that appeared in all 20 runs: `facility compliance`, `food safety`, `health inspection`
- Tags that appeared in exactly one run: *(none)*

| Latency (n=20) | p50 | p95 | p99 |
|---|---|---|---|
| ms | 23167.5 | 25365.1 | 25913.8 |
