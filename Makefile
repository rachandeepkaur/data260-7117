PY ?= .venv/bin/python
HW04 = code/hw04
PORT_BASE = 8817

.PHONY: setup-db seed run-api run-client benchmark explain benchmark-with-index rag metrics verify-hw04

setup-db:            ## create s7117_rel, tables (schema.sql) and the app user
	$(PY) $(HW04)/setup_db.py

seed:                ## 5,000 inspections + 200 violations, SEED=7117
	$(PY) $(HW04)/seed_data.py

run-api:             ## FastAPI backend on PORT_BASE
	cd code/web_application && ../../$(PY) -m uvicorn app:app --host 127.0.0.1 --port $(PORT_BASE)

run-client:          ## React dev server on :5173 (proxies /api to :8817)
	cd code/react_client && npm install && npm run dev

benchmark:           ## 180 measured N+1 requests (run before `make explain`)
	$(PY) $(HW04)/benchmark_nplus1.py

explain:             ## EXPLAIN before/after adding ix_violations_inspection_id
	$(PY) $(HW04)/explain_index.py

benchmark-with-index:
	$(PY) $(HW04)/benchmark_nplus1.py --tag with_index

rag:                 ## RAG: 6 questions x 3 configs + k-sweep + evaluation
	$(PY) $(HW04)/rag.py

metrics:             ## rebuild reports/hw04/METRICS.md from raw/
	$(PY) $(HW04)/compute_metrics.py

verify-hw04:         ## smoke test -> reports/hw04/verification.json
	$(PY) $(HW04)/verify.py

# ---------------------------------------------------------------------------
# HW5 - every target below appends a timestamped copy of its console output
# to reports/hw05/RUN_LOG.txt.
HW05 = code/hw05
LOG05 = reports/hw05/RUN_LOG.txt
SHELL := /bin/bash
define logged05
	@mkdir -p reports/hw05/raw
	@printf '\n===== [%s] make %s (user: %s) =====\n' "$$(date '+%Y-%m-%d %H:%M:%S %Z')" "$@" "$$(git config user.name)" | tee -a $(LOG05)
	@set -o pipefail; $(1) 2>&1 | tee -a $(LOG05)
endef

.PHONY: migrate-hw05 api-demo-hw05 mcp-meals mcp-domain inspector-meals inspector-domain mcp-calls retry-demo fault-injection test-hw05 safety-demo agent-hw05 metrics-hw05 verify-hw05

migrate-hw05:        ## HW5 Part 1: inspectors table + inspection_code/score/inspector_id FK (run after setup-db + seed)
	$(call logged05,$(PY) $(HW05)/migrate.py)

api-demo-hw05:       ## HW5 Part 1: every endpoint + error case against the running API -> raw/part1_api_calls.json
	$(call logged05,$(PY) $(HW05)/part1_api_demo.py)

# `mcp dev` runs the server via `uv run --with mcp`; pin mcp to 1.x (2.x renamed
# FastMCP) and add the domain server's DB driver packages. The pin is written
# ~=1.9 (= >=1.9,<2) because the classic Inspector splits args like a shell.
MCP_PIN = --with "mcp[cli]~=1.9"
DOMAIN_DEPS = --with sqlalchemy --with pymysql --with cryptography
# Classic Inspector UI (shows tool inputs and the result together - used for the
# screenshots); same `uv run ... mcp run <file>` command that `mcp dev` builds.
INSPECTOR_CLASSIC = npx -y @modelcontextprotocol/inspector@0.22.0 uv run $(MCP_PIN)

mcp-meals:           ## HW5 Part 2A: MCP Inspector for the TheMealDB server
	.venv/bin/mcp dev code/mcp_servers/meals_server.py $(MCP_PIN) --with httpx

mcp-domain:          ## HW5 Part 2B: MCP Inspector for the s7117_rel domain server
	.venv/bin/mcp dev code/mcp_servers/inspections_server.py $(MCP_PIN) $(DOMAIN_DEPS)

inspector-meals:     ## HW5 Part 2A: classic MCP Inspector (inputs + output on one screen) for meals_server.py
	$(INSPECTOR_CLASSIC) --with httpx mcp run code/mcp_servers/meals_server.py

inspector-domain:    ## HW5 Part 2B: classic MCP Inspector for inspections_server.py
	$(INSPECTOR_CLASSIC) $(DOMAIN_DEPS) mcp run code/mcp_servers/inspections_server.py

mcp-calls:           ## HW5 Part 2: call every MCP tool over STDIO -> raw/mcp_inspector_outputs.json
	$(call logged05,$(PY) $(HW05)/mcp_tool_calls.py)

retry-demo:          ## HW5 Part 3 Q19: first-try success / retry success / retries exhausted
	$(call logged05,$(PY) $(HW05)/retry_demo.py)

fault-injection:     ## HW5 Part 3 Q20: 3 rates x 50 calls with VERIFY_SEED -> raw/fault_injection_*.csv
	$(call logged05,$(PY) $(HW05)/fault_injection.py)

test-hw05:           ## HW5 Part 4/5: offline test runner (no MySQL, Ollama or network)
	$(call logged05,$(PY) code/tests/test_hw05_tools.py)

safety-demo:         ## HW5 Part 5.I: one allowed + one blocked execute_tool call
	$(call logged05,$(PY) $(HW05)/safety_demo.py)

agent-hw05:          ## HW5 Part 5.IV: agent scenarios on local Ollama -> raw/agent_runs.jsonl
	$(call logged05,$(PY) $(HW05)/run_agent_scenarios.py)

metrics-hw05:        ## rebuild reports/hw05/METRICS.md from raw/
	$(call logged05,$(PY) $(HW05)/compute_metrics.py)

verify-hw05:         ## smoke test -> reports/hw05/verification.json
	$(call logged05,$(PY) $(HW05)/verify.py)

# ---------------------------------------------------------------------------
# HW6 - every logged target appends a timestamped copy of its console output
# to reports/hw06/RUN_LOG.txt.
HW06 = code/hw06
LOG06 = reports/hw06/RUN_LOG.txt
define logged06
	@mkdir -p reports/hw06/raw
	@printf '\n===== [%s] make %s (user: %s) =====\n' "$$(date '+%Y-%m-%d %H:%M:%S %Z')" "$@" "$$(git config user.name)" | tee -a $(LOG06)
	@set -o pipefail; $(1) 2>&1 | tee -a $(LOG06)
endef

.PHONY: file-memory-demo-hw06 mongo-up mongo-shell setup-mongo-hw06 doc-api-demo-hw06 chat-demo-hw06 memory-experiment-hw06 metrics-hw06 file-memory-chat consolidation-test-hw06 agent-md-check-hw06 test-hw06 verify-hw06

mongo-up:            ## HW6: MongoDB 7 in Docker on :27017 (data in the s7117_mongo_data volume)
	docker start s7117-mongo 2>/dev/null || docker run -d --name s7117-mongo -p 27017:27017 -v s7117_mongo_data:/data/db mongo:7.0

mongo-shell:         ## HW6: mongosh inside the container, on s7117_doc
	docker exec -it s7117-mongo mongosh s7117_doc

setup-mongo-hw06:    ## HW6 Part 1.I: s7117_doc collections + $$jsonSchema validators + indexes + sample docs
	$(call logged06,$(PY) $(HW06)/setup_mongo.py)

doc-api-demo-hw06:   ## HW6 Part 1: CRUD + validation cases against the running API -> raw/part1_doc_api_calls.json
	$(call logged06,$(PY) $(HW06)/part1_doc_api_demo.py)

chat-demo-hw06:      ## HW6 Part 2: 12 messages in one session + GET memory/aggregate -> raw/part2_*.json
	$(call logged06,$(PY) $(HW06)/part2_chat_demo.py)

memory-experiment-hw06: ## HW6 Part 3: 30 msgs + 5 probes x 4 settings (starts its own API; stop run-api first)
	$(call logged06,$(PY) $(HW06)/run_memory_experiment.py)

metrics-hw06:        ## HW6: rebuild reports/hw06/METRICS.md from raw/
	$(call logged06,$(PY) $(HW06)/compute_metrics.py)

file-memory-chat:    ## HW6 Part 4: interactive chat with AGENT.md + MEMORY.md (/memory /compact /dream /help)
	$(PY) $(HW06)/file_memory_chat.py

consolidation-test-hw06: ## HW6 Part 4.5: 55-line MEMORY.md -> consolidated (<40 lines) + contradiction audit
	$(call logged06,$(PY) $(HW06)/consolidation_test.py)

agent-md-check-hw06: ## HW6 Part 4.4: generate one function with AGENT.md as system prompt, check it follows AGENT.md
	$(call logged06,$(PY) $(HW06)/agent_md_check.py)

test-hw06:           ## HW6: offline tests (no MongoDB/Ollama needed)
	$(call logged06,$(PY) code/tests/test_hw06_memory.py)

verify-hw06:         ## HW6 smoke test -> reports/hw06/verification.json
	$(call logged06,$(PY) $(HW06)/verify.py)

file-memory-demo-hw06: ## HW6 Part 4.3: scripted run of /help /memory /dream /compact (evidence for RUN_LOG)
	$(call logged06,$(PY) $(HW06)/file_memory_chat.py --script reports/hw06/file_memory_demo_script.txt --no-auto-consolidate)

# ---------------------------------------------------------------------------
# HW7 - every logged target appends a timestamped copy of its console output
# to reports/hw07/RUN_LOG.txt.
HW07 = code/hw07
LOG07 = reports/hw07/RUN_LOG.txt
define logged07
	@mkdir -p reports/hw07/raw
	@printf '\n===== [%s] make %s (user: %s, commit %s) =====\n' "$$(date '+%Y-%m-%d %H:%M:%S %Z')" "$@" "$$(git config user.name)" "$$(git rev-parse --short HEAD)" | tee -a $(LOG07)
	@set -o pipefail; $(1) 2>&1 | tee -a $(LOG07)
endef

.PHONY: migrate-hw07 auth-demo-hw07 lint precommit-install test-hw07 agent-demo-hw07 reliability-hw07 reflexion-hw07 bikeshare-scenarios-hw07 bikeshare-hw07 injection-hw07 file-tools-hw07 metrics-hw07 verify-hw07

migrate-hw07:        ## HW7 Part 1: users.username/role + reader/writer/moderator users (run after migrate-hw05)
	$(call logged07,$(PY) $(HW07)/migrate.py)

auth-demo-hw07:      ## HW7 Part 1: login/me/RBAC status codes against the running API (make run-api first)
	$(call logged07,$(PY) $(HW07)/part1_auth_demo.py)

lint:                ## HW7 Part 1.V: Ruff over the repo (rules in pyproject.toml)
	.venv/bin/ruff check .

precommit-install:   ## HW7 Part 1.V: install the Ruff pre-commit hook into .git/hooks
	.venv/bin/pre-commit install

test-hw07:           ## HW7: offline tests (no MySQL/Ollama/network)
	$(call logged07,$(PY) code/tests/test_hw07.py)

agent-demo-hw07:     ## HW7 Part 2.I/II: tasks A, B, C + nonexistent-id recovery on qwen3:8b
	$(call logged07,$(PY) $(HW07)/run_agent_demo.py)

reliability-hw07:    ## HW7 Part 2.III: 21 tool-use attempts -> raw/toolcall_reliability.csv
	$(call logged07,$(PY) $(HW07)/run_reliability.py)

reflexion-hw07:      ## HW7 Part 3: original vs Reflexion loop -> raw/reflexion_comparison.csv, raw/reflections.jsonl
	$(call logged07,$(PY) $(HW07)/run_reflexion_comparison.py)

bikeshare-scenarios-hw07: ## HW7 Part 4: build the 2 scenario CSVs from public Bay Wheels trip data
	$(call logged07,cd $(HW07) && ../../$(PY) build_bikeshare_scenarios.py)

bikeshare-hw07:      ## HW7 Part 4: run the ReAct agent on both scenarios (headless; UI at /bikeshare)
	$(call logged07,cd $(HW07) && ../../$(PY) run_bikeshare_scenarios.py)

injection-hw07:      ## HW7 Part 5: 3 attacks x 3 defense configs on the local hostile fixture
	$(call logged07,$(PY) $(HW07)/run_injection_attacks.py)

file-tools-hw07:     ## HW7 Part 6: glob->search->read integration test + 10-command safety-gate test
	$(call logged07,$(PY) $(HW07)/file_tools_demo.py)

metrics-hw07:        ## HW7: rebuild reports/hw07/METRICS.md from raw/
	$(call logged07,$(PY) $(HW07)/compute_metrics.py)

verify-hw07:         ## HW7 smoke test -> reports/hw07/verification.json
	$(call logged07,$(PY) $(HW07)/verify.py)
