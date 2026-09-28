# HW04 — Reproducible Run Instructions

Personal configuration (Section 0): SID4 = 7117, PORT_BASE = 8817, PREFIX = s7117, SEED = 7117,
VERIFY_SEED = 267117, DOMAIN_ID = 5 (local restaurant inspections). Database: `s7117_rel`.

Run everything from the repo root.

## Setup

```bash
brew install mysql && brew services start mysql     # MySQL 9.x, root without password on localhost
pip install -r requirements.txt
ollama pull qwen3:8b                                # local LLM for Part 4
```

## Part 2 — MySQL + server-side sessions

```bash
make setup-db     # code/hw04/schema.sql -> s7117_rel (inspections, inspection_violations, users, sessions) + app user
make seed         # code/hw04/seed_data.py: 5,000 inspections + 200 violations (SEED=7117) + demo user
make run-api      # FastAPI on http://127.0.0.1:8817  (Swagger UI: /docs)
```

Demo login: `demo@s7117.dev` / `Inspect!7117` (dev only). New users: `POST /api/auth/register`.

| Operation | Method + path |
|---|---|
| Register / login / logout / current user | `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` |
| Add a record | `POST /api/records` `{"facility_name", "site_address"}` |
| View all records | `GET /api/records` (optional `?limit=&offset=`; total in `X-Total-Count`) |
| View a record by id | `GET /api/records/{id}` |
| Update a record | `PUT /api/records/{id}` |
| Delete a record | `DELETE /api/records/{id}` |

Every `/api/records` and `/api/nplus1` route returns `401 Login required` without a valid session
cookie. Login stores a row in `sessions` (random 43-char token, `created_at`, `expires_at`) and sets
`s7117_session=<token>; HttpOnly; SameSite=Lax` — the cookie holds only the opaque token.

Postman: import `reports/hw04/postman_collection.json` (login first; Postman keeps the cookie).

## Part 1 — React client

```bash
make run-client   # Vite dev server on http://localhost:5173, proxies /api -> :8817
```

Routes: `/` Home (record list), `/login`, `/create`, `/update?id=N`, `/delete?id=N`.

## Part 3 — N+1 measurement and index

```bash
make benchmark             # 180 measured requests -> raw/nplus1_requests.csv/.json, raw/nplus1_summary.csv
make explain               # drops/creates ix_violations_inspection_id, EXPLAIN before/after -> raw/explain_before_after.*
make benchmark-with-index  # optional supplementary re-run -> raw/nplus1_requests_with_index.csv
```

Endpoints: `GET /api/nplus1/naive?page_size=N` (1 + N queries) and `GET /api/nplus1/fixed?page_size=N`
(2 queries, SQLAlchemy `selectinload`). Each response reports `sql_queries` in its body and in the
`X-SQL-Query-Count` header.

## Part 4 — RAG

```bash
python code/hw04/rag.py --retrieval-only   # printed top-k retrievals only
make rag                                   # 6 questions x A/B/C + k-sweep + evaluation -> raw/rag_*
```

Corpus: `data/corpus/*.txt` (4 HW3 documents) + `data/corpus/hw04/*.txt` (2 Wikipedia articles);
see `SOURCES.md`. Questions: `reports/hw04/rag_questions.yaml`.

## Metrics and verification

```bash
make metrics       # rebuilds METRICS.md from raw/
make verify-hw04   # smoke test -> reports/hw04/verification.json (starts the API itself if needed)
```
