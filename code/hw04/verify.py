"""HW4 self-check (smoke test) -> reports/hw04/verification.json.

    make verify-hw04        (or: python code/hw04/verify.py)

Starts the FastAPI backend on PORT_BASE if nothing is listening there yet,
then checks behavior (status codes, counts, cookie flags) rather than exact
wording. Uses VERIFY_SEED to pick the records it spot-checks and to name the
temporary record it creates and deletes again. It never writes application
code: the last check confirms `git status` of code/ is unchanged.
"""
from __future__ import annotations

import csv
import json
import random
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

import requests
from sqlalchemy import text

from hw04_config import (
    BASE_URL,
    DB_NAME,
    DEMO_USER_EMAIL,
    DEMO_USER_PASSWORD,
    DOMAIN_ID,
    LOCAL_MODEL,
    PORT_BASE,
    PREFIX,
    RAW_DIR,
    REPO_ROOT,
    REPORT_DIR,
    SEED,
    SID4,
    VERIFY_SEED,
    WEB_APP_DIR,
    use_web_app_imports,
)

use_web_app_imports()

checks: list[dict] = []


def check(name: str, description: str):
    def wrap(fn):
        try:
            passed, evidence = fn()
        except Exception as exc:  # noqa: BLE001
            passed, evidence = False, f"raised {type(exc).__name__}: {exc}"
        checks.append({"name": name, "description": description, "passed": bool(passed), "evidence": evidence})
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {evidence}")
        return fn
    return wrap


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> None:
    code_status_before = git("status", "--porcelain", "--", "code")
    rng = random.Random(VERIFY_SEED)
    server = None
    server_log = tempfile.NamedTemporaryFile(prefix="hw04_verify_uvicorn_", suffix=".log", delete=False)

    @check("config_values", "Section 0 values derive from SID4 = 7117")
    def _():
        expected = (8817, "s7117", 7117, 267117, 5)
        actual = (PORT_BASE, PREFIX, SEED, VERIFY_SEED, DOMAIN_ID)
        return actual == expected, f"PORT_BASE={PORT_BASE} PREFIX={PREFIX} SEED={SEED} VERIFY_SEED={VERIFY_SEED} DOMAIN_ID={DOMAIN_ID}"

    @check("mysql_schema", f"MySQL database {DB_NAME} has inspections, inspection_violations, users, sessions")
    def _():
        from database import engine
        with engine.connect() as conn:
            db = conn.execute(text("SELECT DATABASE()")).scalar()
            tables = sorted(r[0] for r in conn.execute(text("SHOW TABLES")))
            version = conn.execute(text("SELECT VERSION()")).scalar()
        want = ["inspection_violations", "inspections", "sessions", "users"]
        return db == DB_NAME and all(t in tables for t in want), f"MySQL {version}, database={db}, tables={tables}"

    @check("seeded_rows", "At least 5,000 inspections and exactly 200 related violations are seeded")
    def _():
        from database import engine
        with engine.connect() as conn:
            n_insp = conn.execute(text("SELECT COUNT(*) FROM inspections WHERE id <= 5000")).scalar()
            n_viol = conn.execute(text("SELECT COUNT(*) FROM inspection_violations")).scalar()
            orphans = conn.execute(text(
                "SELECT COUNT(*) FROM inspection_violations v LEFT JOIN inspections i ON i.id = v.inspection_id WHERE i.id IS NULL"
            )).scalar()
        return n_insp >= 4990 and n_viol == 200 and orphans == 0, \
            f"inspections(id<=5000)={n_insp}, violations={n_viol}, orphan violations={orphans}"

    @check("index_present", "ix_violations_inspection_id exists on inspection_violations(inspection_id)")
    def _():
        from database import engine
        with engine.connect() as conn:
            rows = conn.execute(text("SHOW INDEX FROM inspection_violations WHERE Key_name = 'ix_violations_inspection_id'")).fetchall()
        return len(rows) == 1, f"{len(rows)} matching index row(s)"

    if not port_open(PORT_BASE):
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(PORT_BASE)],
            cwd=WEB_APP_DIR, stdout=server_log, stderr=subprocess.STDOUT,
        )
        for _i in range(60):
            if port_open(PORT_BASE):
                break
            time.sleep(0.5)
    started_here = server is not None

    try:
        @check("backend_on_port_base", f"FastAPI backend responds on PORT_BASE {PORT_BASE}")
        def _():
            r = requests.get(f"{BASE_URL}/openapi.json", timeout=10)
            paths = r.json().get("paths", {})
            need = ["/api/records", "/api/records/{record_id}", "/api/auth/login", "/api/nplus1/naive", "/api/nplus1/fixed"]
            return r.status_code == 200 and all(p in paths for p in need), \
                f"GET /openapi.json -> {r.status_code}; started_by_verify={started_here}; required paths present={all(p in paths for p in need)}"

        @check("unauthenticated_blocked", "Record list and N+1 endpoints return 401 without a session cookie")
        def _():
            codes = [requests.get(f"{BASE_URL}{p}", timeout=10).status_code
                     for p in ("/api/records?limit=1", "/api/nplus1/naive", "/api/nplus1/fixed")]
            return codes == [401, 401, 401], f"status codes={codes}"

        session = requests.Session()

        @check("login_sets_httponly_session_cookie",
               "Login sets an HttpOnly cookie whose value is an opaque token stored in the sessions table")
        def _():
            r = session.post(f"{BASE_URL}/api/auth/login",
                             json={"email": DEMO_USER_EMAIL, "password": DEMO_USER_PASSWORD}, timeout=10)
            set_cookie = r.headers.get("set-cookie", "")
            token = session.cookies.get("s7117_session", "")
            from database import engine
            with engine.connect() as conn:
                in_db = conn.execute(text("SELECT COUNT(*) FROM sessions WHERE id = :t AND expires_at > UTC_TIMESTAMP()"),
                                     {"t": token}).scalar()
            opaque = bool(token) and "@" not in token and DEMO_USER_EMAIL.split("@")[0] not in token
            bad = requests.post(f"{BASE_URL}/api/auth/login",
                                json={"email": DEMO_USER_EMAIL, "password": "wrong-password"}, timeout=10).status_code
            ok = r.status_code == 200 and "httponly" in set_cookie.lower() and opaque and in_db == 1 and bad == 401
            return ok, f"login={r.status_code}, HttpOnly={'httponly' in set_cookie.lower()}, opaque={opaque}, " \
                       f"token_len={len(token)}, row_in_sessions={in_db}, wrong_password={bad}"

        @check("crud_roundtrip", "POST -> GET by id -> PUT -> GET all -> DELETE -> GET 404 on /api/records")
        def _():
            name = f"FA{rng.randint(1000000, 9999999)} - VERIFY {VERIFY_SEED}"
            steps = []
            r = session.post(f"{BASE_URL}/api/records", json={"facility_name": name, "site_address": "1 VERIFY WAY, SAN JOSE, CA 95112"}, timeout=10)
            rid = r.json().get("id")
            steps.append(("POST", r.status_code))
            steps.append(("GET id", session.get(f"{BASE_URL}/api/records/{rid}", timeout=10).status_code))
            r = session.put(f"{BASE_URL}/api/records/{rid}", json={"facility_name": name + " UPDATED", "site_address": "2 VERIFY WAY"}, timeout=10)
            steps.append(("PUT", r.status_code))
            updated = r.json().get("facility_name", "").endswith("UPDATED")
            r = session.get(f"{BASE_URL}/api/records", params={"limit": 5}, timeout=10)
            steps.append(("GET all", r.status_code))
            listed = any(x["id"] == rid for x in r.json())
            steps.append(("DELETE", session.delete(f"{BASE_URL}/api/records/{rid}", timeout=10).status_code))
            steps.append(("GET after delete", session.get(f"{BASE_URL}/api/records/{rid}", timeout=10).status_code))
            ok = [c for _s, c in steps] == [201, 200, 200, 200, 200, 404] and updated and listed
            return ok, f"id={rid}, steps={steps}, update_applied={updated}, new_record_listed={listed}"

        @check("verify_seed_spot_check", "5 record ids drawn with VERIFY_SEED are readable via GET /api/records/{id}")
        def _():
            ids = rng.sample(range(1, 5001), 5)
            codes = {i: session.get(f"{BASE_URL}/api/records/{i}", timeout=10).status_code for i in ids}
            return all(c == 200 for c in codes.values()), f"ids={ids}, status={list(codes.values())}"

        @check("nplus1_naive_and_fixed", "Both list versions return the same data; naive issues N+1 statements, fixed issues 2")
        def _():
            details = []
            ok = True
            for size in (10, 50, 200):
                n = session.get(f"{BASE_URL}/api/nplus1/naive", params={"page_size": size}, timeout=30)
                f = session.get(f"{BASE_URL}/api/nplus1/fixed", params={"page_size": size}, timeout=30)
                nb, fb = n.json(), f.json()
                same = nb["items"] == fb["items"]
                has_related = fb["violation_count"] > 0
                good = (n.status_code == f.status_code == 200 and nb["record_count"] == size and same and has_related
                        and nb["sql_queries"] == size + 1 and fb["sql_queries"] == 2)
                ok &= good
                details.append(f"size={size}: naive_sql={nb['sql_queries']} fixed_sql={fb['sql_queries']} "
                               f"records={nb['record_count']} violations={fb['violation_count']} same_items={same}")
            return ok, "; ".join(details)

        @check("logout_revokes_session", "After logout the old cookie value is rejected (session row deleted)")
        def _():
            token = session.cookies.get("s7117_session")
            r = session.post(f"{BASE_URL}/api/auth/logout", timeout=10)
            replay = requests.get(f"{BASE_URL}/api/auth/me", cookies={"s7117_session": token}, timeout=10)
            return r.status_code == 204 and replay.status_code == 401, \
                f"logout={r.status_code}, replayed old cookie on /api/auth/me -> {replay.status_code}"
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=10)

    @check("raw_nplus1_180_requests", "raw/nplus1_requests.csv holds 180 requests: 3 page sizes x 2 versions x 30")
    def _():
        with (RAW_DIR / "nplus1_requests.csv").open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        combos: dict = {}
        for r in rows:
            combos[(r["page_size"], r["version"])] = combos.get((r["page_size"], r["version"]), 0) + 1
        return len(rows) == 180 and len(combos) == 6 and set(combos.values()) == {30}, \
            f"{len(rows)} rows, per combo={ {f'{k[0]}/{k[1]}': v for k, v in sorted(combos.items())} }"

    @check("rag_outputs_and_refusals", "RAG raw outputs exist; config C refuses Q5 and Q6 and answers Q1-Q3")
    def _():
        needed = ["rag_retrievals.txt", "rag_three_config_comparison.csv", "rag_k_sweep.csv",
                  "rag_evaluation_table.csv", "rag_evaluation_summary.csv"]
        missing = [n for n in needed if not (RAW_DIR / n).exists()]
        if missing:
            return False, f"missing: {missing}"
        with (RAW_DIR / "rag_three_config_comparison.csv").open(encoding="utf-8") as fh:
            rows = {(r["question_id"], r["config"]): r for r in csv.DictReader(fh)}
        refused = {q: rows[(q, "C")]["refused"] == "True" for q in ("Q5", "Q6")}
        answered = {q: rows[(q, "C")]["refused"] == "False" for q in ("Q1", "Q2", "Q3")}
        corpus = len(list((REPO_ROOT / "data" / "corpus").glob("*.txt")) + list((REPO_ROOT / "data" / "corpus" / "hw04").glob("*.txt")))
        return all(refused.values()) and all(answered.values()) and corpus >= 5, \
            f"corpus_docs={corpus}, C refused={refused}, C answered={answered}"

    @check("react_client_components", "React client has Login/Home/Create/Update/Delete components and routes")
    def _():
        src = REPO_ROOT / "code" / "react_client" / "src"
        comps = ["Login", "Home", "CreateRecord", "UpdateRecord", "DeleteRecord"]
        present = {c: (src / "components" / f"{c}.jsx").exists() for c in comps}
        app = (src / "App.jsx").read_text(encoding="utf-8")
        routes = {r: f'path="{r}"' in app for r in ("/", "/login", "/create", "/update", "/delete")}
        uses_router = "react-router-dom" in app
        return all(present.values()) and all(routes.values()) and uses_router, f"components={present}, routes={routes}"

    @check("app_code_unmodified", "Running verify did not modify tracked or untracked files under code/")
    def _():
        after = git("status", "--porcelain", "--", "code")
        return after == code_status_before, "git status of code/ identical before and after" if after == code_status_before else "code/ changed during verify"

    try:
        commit = git("rev-parse", "HEAD")
        tag_commit = subprocess.run(["git", "rev-list", "-n", "1", "hw4"], cwd=REPO_ROOT, text=True,
                                    capture_output=True).stdout.strip()
        dirty = bool(git("status", "--porcelain"))
    except Exception:  # noqa: BLE001
        commit, tag_commit, dirty = "", "", True

    result = {
        "homework": "HW4",
        "SID4": str(SID4),
        "commit_hash": commit,
        "tag_hw4_commit": tag_commit or None,
        "head_is_tag_hw4": commit == tag_commit,
        "working_tree_dirty": dirty,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "configuration": {
            "PORT_BASE": PORT_BASE,
            "PREFIX": PREFIX,
            "DOMAIN_ID": DOMAIN_ID,
            "database": DB_NAME,
            "local_model": LOCAL_MODEL,
            "embedding_model": "BAAI/bge-small-en-v1.5",
            "rag": {"chunk_size": 500, "chunk_overlap": 50, "top_k": 3},
        },
        "SEED": SEED,
        "VERIFY_SEED": VERIFY_SEED,
        "checks": checks,
        "summary": {
            "total_checks": len(checks),
            "passed": sum(c["passed"] for c in checks),
            "failed": sum(not c["passed"] for c in checks),
        },
    }
    (REPORT_DIR / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"]))
    sys.exit(0 if result["summary"]["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
