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
