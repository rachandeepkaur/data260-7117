# HW05 — Reproducible Run Instructions

Personal configuration (Section 0): SID4 = 7117, PORT_BASE = 8817, PREFIX = s7117, SEED = 7117,
VERIFY_SEED = 267117, DOMAIN_ID = 5 (local restaurant inspections). Database: `s7117_rel`.
Local model: `qwen3:8b` (Ollama). Submission tag: `hw5`.

Run everything from the repo root. Every `make` target below appends a timestamped copy of its
console output to `reports/hw05/RUN_LOG.txt`.

## Setup

```bash
pip install -r requirements.txt          # adds mcp[cli]<2 and httpx for HW5
ollama pull qwen3:8b
# MySQL must be running (HW4: Homebrew or the Docker container), then:
make setup-db && make seed               # HW4 base data (skip if s7117_rel already exists)
make migrate-hw05                        # HW5: inspectors table + new inspection columns + FK
```

> The migration makes `inspection_code` and `inspector_id` required, so run `make seed` (HW4) **before**
> `make migrate-hw05`, never after — the HW4 seed script does not know the new columns.



## Where the code lives


| Part                  | Code                                                                                                                              |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| 1.I Database          | `code/hw05/migration.sql`, `code/hw05/migrate.py`, `code/web_application/models.py`                                               |
| 1.II API              | `code/web_application/routers/inspectors.py` (new), `routers/records.py` (extended)                                               |
| 1.III Redux           | `code/react_client/src/store/` (`index.js`, `inspectionsSlice.js`, `inspectorsSlice.js`), `src/api.js` (axios), `src/components/` |
| 2A TheMealDB MCP      | `code/mcp_servers/meals_server.py`                                                                                                |
| 2B Domain MCP         | `code/mcp_servers/inspections_server.py` → `code/domain_tools/`                                                                   |
| Envelope              | `code/domain_tools/envelope.py`                                                                                                   |
| 3 Retries / faults    | `code/domain_tools/resilience.py`, `code/hw05/retry_demo.py`, `code/hw05/fault_injection.py`                                      |
| 4 execute_tool        | `code/domain_tools/executor.py`; tests `code/tests/test_hw05_tools.py`                                                            |
| 5 Safety rule + agent | `executor.py` (`check_safety_rule`), `code/domain_tools/agent.py`, `code/hw05/run_agent_scenarios.py`                             |
| Self-check            | `code/hw05/verify.py`                                                                                                             |




## Part 1 — API + Redux

```bash
make run-api          # FastAPI on http://127.0.0.1:8817 (Swagger: /docs)
make run-client       # React on http://localhost:5173 (installs Redux Toolkit, react-redux, axios)
```

Postman: import `reports/hw05/postman_collection.json` and run **Login** first. Requests that use ids
(`/api/inspectors/21`, `/api/records/5001`) assume the ids returned by the preceding *Create*
request — change them if yours differ.


| Entity               | Endpoints                                                                                             |
| -------------------- | ----------------------------------------------------------------------------------------------------- |
| Inspector (related)  | `POST /api/inspectors`, `GET /api/inspectors?page=&page_size=`, `GET/PUT/DELETE /api/inspectors/{id}` |
| Relationship         | `GET /api/inspectors/{id}/inspections`                                                                |
| Inspection (primary) | `POST /api/records`, `GET /api/records?limit=&offset=`, `GET/PUT/DELETE /api/records/{id}`            |


Errors: `404` not found · `422` validation (bad email, bad `INS-######` code, score outside 0–100,
unknown `inspector_id`) · `409` duplicate email/code, or deleting an inspector that still has
inspections (FK `ON DELETE RESTRICT`, no cascade).

## Part 2 — MCP servers

```bash
make mcp-meals         # `mcp dev code/mcp_servers/meals_server.py` (Inspector 2.x)
make mcp-domain        # `mcp dev code/mcp_servers/inspections_server.py`
make inspector-meals   # classic Inspector 0.22 - same server command, but shows inputs + result together (use for screenshots)
make inspector-domain
make mcp-calls         # calls every tool over STDIO -> raw/mcp_inspector_outputs.json
```

`mcp dev` runs the server in a separate `uv` environment; the targets pin `mcp[cli]~=1.9` (mcp 2.x
renamed FastMCP) and add the domain server's MySQL driver. In the Inspector: **Connect → Tools →
List Tools → pick a tool → fill the fields → Run Tool**. Inspector 2.x hides the input form once a
result is shown, so take the screenshots in the classic UI (`make inspector-*`).

Part 2A calls: `search_meals_by_name` query `Arrabiata`, `meals_by_ingredient` ingredient `chicken`,
`meal_details` id `52771`, `random_meal` (no input).

Part 2B calls (the invalid ones are reused in Part 3):


| Tool                 | Valid input                           | Invalid input             | Rejected because        |
| -------------------- | ------------------------------------- | ------------------------- | ----------------------- |
| `search_inspections` | `query=golden, limit=5, min_score=90` | `query=golden, limit=500` | limit must be 1–25      |
| `get_inspection`     | `inspection_code=INS-000038`          | `inspection_code=12345`   | must match `INS-######` |
| `inspection_stats`   | `inspector_id=3`                      | `zip_code=95A18`          | ZIP must be 5 digits    |


A rejected call still returns normally (`Tool Result: Success` in the Inspector) — the rejection is
the envelope `{"ok": false, "data": null, "error": "invalid input for …"}`.

## Part 3 — Contracts, retries, fault injection

```bash
make retry-demo        # 3 cases: first-try success / timeout then success / all retries fail
make fault-injection   # 3 rates x 50 calls with VERIFY_SEED -> raw/fault_injection_*.csv/json
```

Q18 write-up: `PART3_CONTRACTS.md`.

## Part 4 / 5

```bash
make test-hw05         # offline runner: PASS/FAIL per test + X/Y (screenshot this)
make safety-demo       # one allowed + one blocked execute_tool call
make agent-hw05        # 5 scenarios on qwen3:8b -> raw/agent_runs.jsonl, raw/agent_scenarios.csv
make metrics-hw05      # rebuild METRICS.md from raw/
```



## Submission

```bash
git add -A && git commit -m "Homework 5 submission"
git tag hw5 && git push origin main --tags
make verify-hw05       # writes verification.json (commit hash + tag); commit it, then move the tag:
git add reports/hw05/verification.json && git commit -m "HW5 verification" && git tag -f hw5 && git push -f origin hw5
```

