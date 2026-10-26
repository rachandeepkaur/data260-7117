# HW7: JWT + RBAC, a hand-written agent loop, Reflexion, a ReAct/MRKL public-data agent, prompt-injection defenses, and file tools

Repository: https://github.com/rachandeepkaur/data260-7117 · tag `hw7`

| Value | |
|---|---|
| SID4 | 7117 |
| PORT_BASE | 8817 (8000 + 7117 mod 900) |
| PREFIX | s7117 |
| SEED / VERIFY_SEED | 7117 / 267117 |
| DOMAIN_ID | 5 (local restaurant inspections) |
| Hardware | Intel Core i9-9880H @ 2.3 GHz, 32 GB RAM, macOS (CPU inference) |
| Local model | `qwen3:8b` via Ollama (thinking off) |
| Tagged commit | `git rev-list -n 1 hw7` (also recorded in `verification.json`) |

## Where the code lives (shared root-level folders, no per-homework copy)

| Part | Code |
|---|---|
| 1. JWT + roles | `code/web_application/security.py` (hashing, JWT, `get_current_user`, `require_roles`), `routers/token_auth.py` (`POST /auth/login`, `GET /auth/me`), role rules on `routers/records.py` + `routers/inspectors.py`, migration `code/hw07/migration.sql` + `migrate.py`; React client switched to the bearer token |
| 1.V Lint | `pyproject.toml` (`[tool.ruff]`), `.pre-commit-config.yaml` |
| 2. Agent loop | `code/agent_loop/loop.py` (`run_agent`), `toolsets.py`; HW1 adapter extended with native tool calls (`src/model_client.py`, `ModelClient.chat`) |
| 3. Reflexion | `code/agent_loop/reflexion.py`, verifiers + oracle in `tasks.py`, unsupported-claim check in `grounding.py`; fixed cases `reports/hw07/cases/fixed_tasks.yaml` |
| 4. ReAct/MRKL | `code/bikeshare_agent/` (`tools.py`: csv_sql, policy_retriever, calculator + JSON schemas; `agent.py`: LangGraph ReAct agent; `pricing.py`: reference check); UI `GET /bikeshare` (`routers/bikeshare.py`, `templates/bikeshare.html`) |
| 5. Injection | threat model `THREAT_MODEL.md`, fixture `fixtures/hostile_pricing.html`, defenses = `label_untrusted` + `enforce_select` switches in `bikeshare_agent` |
| 6. File tools | `code/file_tools/tools.py` (six tools, sandboxed), `code/file_tools/safety.py` (`SAFE_PREFIXES`, `is_destructive`, `confirm_bash`) |
| Scripts | `code/hw07/*.py` (one per experiment), tests `code/tests/test_hw07.py`, self-check `code/hw07/verify.py` |

## Run order

```bash
# prerequisites: MySQL running with s7117_rel (HW4/HW5 setup), `ollama serve` with qwen3:8b
.venv/bin/pip install -r requirements.txt
make migrate-hw07            # users.username/role + s7117_reader / s7117_writer / s7117_moderator
make precommit-install       # Ruff hook (Part 1.V)
make test-hw07               # 32 offline tests

make run-api                 # terminal 1: FastAPI on :8817 (also serves /bikeshare)
make auth-demo-hw07          # Part 1 status codes            -> raw/part1_auth_calls.json
make agent-demo-hw07         # Part 2 tasks A, B, C + error recovery -> raw/agent_demo_runs.jsonl
make reliability-hw07        # Part 2.III 21 attempts         -> raw/toolcall_reliability.csv
make reflexion-hw07          # Part 3                         -> raw/reflexion_comparison.csv, raw/reflections.jsonl
make bikeshare-hw07          # Part 4 both scenarios          -> raw/bikeshare/runs/*, scenario_runs.csv
make injection-hw07          # Part 5                         -> raw/injection_attacks.{json,csv}
make file-tools-hw07         # Part 6                         -> raw/safety_gate_tests.csv
make metrics-hw07            # METRICS.md
make verify-hw07             # verification.json
```

Every `make ...-hw07` target appends a timestamped copy of its console output to `RUN_LOG.txt`.
Role-user password (dev only): `Role!7117` (override with `HW07_ROLE_PASSWORD`).

## Part 1.V lint demo (screenshot)

The two long comment lines in `code/web_application/app.py` (line 115) and `src/model_client.py`
(line 75) predate HW7 and were left unfixed on purpose. Both files are part of the HW7 change, so the hook
catches them on the first commit:

```bash
git add -A && git commit -m "Homework 7"   # ruff hook runs -> Failed: 2 x E501
# shorten the two comment lines (split each over two lines)
git add -A && git commit -m "Homework 7"   # ruff (lint)....Passed -> commit created
```

## Screenshot checklist (keep your name visible in terminal screenshots)

| Part | What to capture | Command / page |
|---|---|---|
| 1 | Login 200 + token and login 401 | `make auth-demo-hw07` (steps 1-2), or Swagger `/docs` |
| 1 | `/auth/me` no token 401, and a separate shot of an invalid/expired token 401 | steps 3 and 4-5 |
| 1 | Create: reader 403, writer 201 | steps 7-8 |
| 1 | Delete: writer 403, moderator 200 | steps 9-10 |
| 1 | List/read with a valid token 200 | steps 11-12 |
| 1 | Lint error, fix, successful commit | see the lint demo above |
| 2 | Tasks A, B, C completed without follow-up | `make agent-demo-hw07` |
| 2 | Nonexistent id handled | same run, task E |
| 3 | Stored reflection with its evidence | `raw/reflections.jsonl`, or the METRICS.md Part 3 excerpt |
| 4 | UI for each scenario: timeline, cost comparison, decision, citations, metrics strip | http://127.0.0.1:8817/bikeshare: upload `cases/bikeshare/membership_wins.csv`, then `ppu_wins.csv` |
| 6 | Combined test run (integration + 10 commands) | `make file-tools-hw07` |

## Part 4 data note

The trip CSVs are real rows from the public Bay Wheels monthly files (https://s3.amazonaws.com/baywheels-data/),
sampled by `code/hw07/build_bikeshare_scenarios.py` (sampling rule, source URLs and SHA-256 in
`raw/bikeshare/*_trip_summary.json`). The public data has no rider id, so each scenario treats its sample as
one hypothetical rider's history. The agent states this as an assumption. The pricing page is
https://www.lyft.com/bikes/bay-wheels/pricing (now branded "Lyft Bike"). Every run saves the exact text it
used, the raw HTML, the access time and the SHA-256 hash under `raw/bikeshare/runs/`.
