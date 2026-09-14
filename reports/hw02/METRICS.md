# HW02 Metrics — Planner Schema-Validation Retry Study

Fixed input (`reports/hw02/cases/schema_input.json`, facility: "FA0206933 - YUMMY KITCHEN"), run through the real Supervisor/Planner/Reviewer LangGraph agent (`code/langgraph_agent.py`, `qwen3:8b` via Ollama) 30 times. Each run classified by how many times the Planner's raw output failed `PlannerOutput` Pydantic validation (exactly 3 tags, 3-30 chars each, <=25-word summary) before it produced schema-valid JSON, bounded by `MAX_TURNS=8`. Source data: [raw/schema_validation_runs.json](raw/schema_validation_runs.json), [raw/schema_validation_runs.csv](raw/schema_validation_runs.csv). Full console transcript: [RUN_LOG.txt](RUN_LOG.txt).

## Outcome table

| Bucket | Count | Mean latency (ms) |
|---|---|---|
| valid first attempt | 30 | 26314.1 |
| valid after 1 retry | 0 | - |
| valid after 2plus retries | 0 | - |
| abandoned at ceiling | 0 | - |

- Total runs: 30
- Runs where the Planner's first attempt was already schema-valid: 30/30
- Runs abandoned at the turn ceiling (Planner never produced valid JSON): 0/30
