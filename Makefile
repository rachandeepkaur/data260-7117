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
