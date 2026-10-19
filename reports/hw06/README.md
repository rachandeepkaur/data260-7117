# HW06 — Reproducible Run Instructions

Personal configuration (Section 0): SID4 = 7117, PORT_BASE = 8817, PREFIX = s7117, SEED = 7117,
VERIFY_SEED = 267117, DOMAIN_ID = 5 (local restaurant inspections). Document database: `s7117_doc`
(MongoDB 7). Local model: `qwen3:8b` (Ollama), embeddings `all-MiniLM-L6-v2` (fastembed, 384-d).
Hardware: MacBook Pro, 8-core Intel Core i9 2.3 GHz, 32 GB RAM (Ollama on CPU). Submission tag: `hw6`.

Run everything from the repo root. Every logged `make` target appends a timestamped copy of its
console output to `reports/hw06/RUN_LOG.txt`.

## Setup

```bash
pip install -r requirements.txt     # adds pymongo + tokenizers for HW6
ollama pull qwen3:8b
make mongo-up                       # MongoDB 7 in Docker (container s7117-mongo, port 27017)
make setup-mongo-hw06               # s7117_doc: 4 collections + $jsonSchema validators + indexes + 12 sample docs
```

## Where the code lives

| Part | Code |
|---|---|
| 1 Server config | `code/web_application/settings.py` (env-overridable), `app.py` (CORS + JSON-body middleware, error handlers) |
| 1 PyMongo connection | `code/web_application/mongo.py` (client, `$jsonSchema` validators, indexes) |
| 1 Pydantic schemas | `code/web_application/doc_schemas.py` |
| 1 Route handlers | `code/web_application/routers/doc_inspections.py` |
| 2 Endpoints | `code/web_application/routers/memory_chat.py` (`/api/chat`, `/api/memory/{user_id}`, `/api/aggregate/{user_id}`) |
| 2 Memory logic | `code/web_application/memory_service.py` (`extract_facts`, `store_episodes`, `should_summarize`/`maybe_summarize`, `embed`/`retrieve_episodes`, `build_prompt`, `apply_memory_policy`) |
| 2 Mini chat page | `code/web_application/chat.html` → http://127.0.0.1:8817/chat.html |
| 3 Token log | `memory_service.handle_chat` (`usage` object), `code/web_application/token_counter.py` |
| 3 Experiment | `code/hw06/run_memory_experiment.py`, `probe_scoring.py`, `compute_metrics.py` |
| 4 File memory | `code/file_memory/memory_files.py` (load, prompt, timestamp, rules), `consolidation.py`, `commands.py`; CLI `code/hw06/file_memory_chat.py` |
| 4 Tests / checks | `code/tests/test_hw06_memory.py`, `code/hw06/consolidation_test.py`, `code/hw06/agent_md_check.py` |
| Self-check | `code/hw06/verify.py` → `verification.json` |

## Part 1 — MongoDB document API

```bash
make run-api                 # FastAPI on http://127.0.0.1:8817 (Swagger: /docs)
make doc-api-demo-hw06       # CRUD + 11 validation/error cases -> raw/part1_doc_api_calls.json
make mongo-shell             # then: db.inspections.find().limit(3); db.getCollectionInfos({name:"inspections"})
```

Postman: import `reports/hw06/postman_collection.json` (Create stores `doc_id` automatically).

| Endpoint | Success | Errors |
|---|---|---|
| `POST /api/doc/inspections` | 201 | 422 validation, 400 malformed JSON, 415 not JSON |
| `GET /api/doc/inspections?status=&program_element=&limit=&skip=` | 200 + `X-Total-Count` | 422 bad filter |
| `GET/PUT/DELETE /api/doc/inspections/{id}` | 200 | 400 bad ObjectId, 404 not found, 422 validation |
| any, MongoDB down | — | 503 |

## Part 2 — Memory

```bash
make run-api
make chat-demo-hw06          # 12 messages in one session, then GET memory + aggregate -> raw/part2_*.json
open http://127.0.0.1:8817/chat.html
```

Defaults: `SHORT_TERM_N=12`, `SUMMARIZE_EVERY_USER_MSGS=5`, lifetime summary every 2 session
summaries, `EPISODE_TOP_K=3` (cosine ≥ 0.25), ≤ 3 facts per user message.

## Part 3 — What memory costs

```bash
# stop make run-api first: the runner restarts the API once per setting with its own env
make memory-experiment-hw06  # 4 settings x (30 messages + 5 probes) -> raw/turns_*.jsonl, memory_turns.csv, probe_scores.json
make metrics-hw06            # -> METRICS.md (+ raw/compression_comparison.json)
```

## Part 4 — File-based memory

```bash
make consolidation-test-hw06 # 55-line MEMORY.original.md -> MEMORY.md -> MEMORY.consolidated.md + audit
make file-memory-demo-hw06   # scripted /help /memory /dream /compact run
make agent-md-check-hw06     # generate parse_fact_line with AGENT.md, check it against AGENT.md
make file-memory-chat        # interactive
```

## Tests and self-check

```bash
make test-hw06               # offline (no MongoDB/Ollama)
make verify-hw06             # smoke test -> reports/hw06/verification.json
```
