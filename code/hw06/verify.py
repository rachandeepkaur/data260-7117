"""HW6 self-check (smoke test) -> reports/hw06/verification.json.

    make verify-hw06        (or: python code/hw06/verify.py)

Starts the FastAPI backend on PORT_BASE if nothing is listening there yet,
then checks behaviour (status codes, response shape, counts), never wording:
config, offline tests, MongoDB collections + $jsonSchema validators, the
document CRUD lifecycle and its validation errors, one POST /api/chat with
GET /api/memory + /api/aggregate, the Part 3 raw data, the probes file,
AGENT.md and the MEMORY.md consolidation pair. Temporary records are tagged
from VERIFY_SEED and deleted again; the last check confirms `git status` of
code/ is unchanged (no application code modified).
"""
from __future__ import annotations

import csv
import random
import re
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import json

import requests
import yaml

from hw06_config import (
    AGENT_MD,
    BASE_URL,
    DOMAIN_ID,
    EXPERIMENT_SETTINGS,
    HW,
    LOCAL_MODEL,
    MEMORY_TEST_DIR,
    MONGO_DB,
    PORT_BASE,
    PREFIX,
    PROBES_FILE,
    RAW_DIR,
    REPO_ROOT,
    REPORT_DIR,
    SEED,
    SID4,
    VERIFY_SEED,
    WEB_APP_DIR,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from file_memory import count_memory_lines, needs_consolidation  # noqa: E402

checks: list[dict] = []


def check(name: str, description: str):
    def wrap(fn):
        try:
            passed, evidence = fn()
        except Exception as exc:  # noqa: BLE001
            passed, evidence = False, f"raised {type(exc).__name__}: {exc}"
        checks.append({"name": name, "description": description, "passed": bool(passed), "evidence": evidence})
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {evidence}")
    return wrap


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> None:
    code_status_before = git("status", "--porcelain", "code")
    tag = f"{random.Random(VERIFY_SEED).randint(100000, 999999)}"
    user_id = f"{PREFIX}-verify-{tag}"
    print(f"HW6 verify - {git('config', 'user.name')} - {datetime.now():%Y-%m-%d %H:%M:%S} - tag {tag}\n")

    @check("config_values", "Section 0 values derive from SID4 = 7117")
    def _():
        ok = (PORT_BASE == 8000 + SID4 % 900 and PREFIX == f"s{SID4}" and SEED == SID4
              and VERIFY_SEED == 260000 + SID4 and DOMAIN_ID == SID4 % 8 and MONGO_DB == f"{PREFIX}_doc")
        return ok, f"PORT_BASE={PORT_BASE} PREFIX={PREFIX} SEED={SEED} VERIFY_SEED={VERIFY_SEED} DOMAIN_ID={DOMAIN_ID} db={MONGO_DB}"

    @check("offline_test_suite", "HW6 offline tests (schemas, memory logic, probes, file memory, consolidation) pass")
    def _():
        proc = subprocess.run([sys.executable, str(REPO_ROOT / "code" / "tests" / "test_hw06_memory.py")],
                              capture_output=True, text=True, timeout=180)
        return proc.returncode == 0, proc.stdout.strip().splitlines()[-1]

    @check("mongo_collections_validated", f"{MONGO_DB} has inspections/messages/summaries/episodes with $jsonSchema")
    def _():
        from mongo import get_db

        db = get_db()
        infos = {c["name"]: c for c in db.list_collections()}
        need = ["inspections", "messages", "summaries", "episodes"]
        have = {n: "$jsonSchema" in infos.get(n, {}).get("options", {}).get("validator", {}) for n in need}
        return all(have.values()), have

    @check("mongo_rejects_invalid_doc", "The database itself rejects a document that breaks the schema")
    def _():
        from pymongo.errors import WriteError

        from mongo import get_db

        try:
            get_db()["inspections"].insert_one({"facility_name": "x" * 150, "status": "closed"})
        except WriteError as exc:
            return exc.code == 121, f"WriteError code {exc.code} (DocumentValidationFailure)"
        return False, "invalid document was accepted"

    server = None
    if not port_open(PORT_BASE):
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(PORT_BASE)],
            cwd=WEB_APP_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(120):
            if port_open(PORT_BASE):
                break
            time.sleep(0.5)
    doc_url = f"{BASE_URL}/api/doc/inspections"
    try:
        @check("backend_on_port_base", f"FastAPI backend responds on PORT_BASE {PORT_BASE} with the HW6 routes")
        def _():
            r = requests.get(f"{BASE_URL}/openapi.json", timeout=10)
            paths = r.json()["paths"]
            need = ["/api/doc/inspections", "/api/doc/inspections/{doc_id}", "/api/chat",
                    "/api/memory/{user_id}", "/api/aggregate/{user_id}"]
            return r.status_code == 200 and all(p in paths for p in need), \
                f"GET /openapi.json -> {r.status_code}, HW6 routes present: {all(p in paths for p in need)}"

        @check("doc_crud_lifecycle", "POST 201 -> GET 200 -> PUT 200 (updated_at moves) -> list 200 -> DELETE 200 -> GET 404")
        def _():
            body = {"facility_name": f"FA{tag} - VERIFY CAFE", "program_element": "ROUTINE HEALTH INSPECTION",
                    "inspection_date": "2026-10-20T09:30:00Z"}
            r = requests.post(doc_url, json=body, timeout=10)
            created = r.json()
            codes = [r.status_code]
            did = created["id"]
            codes.append(requests.get(f"{doc_url}/{did}", timeout=10).status_code)
            time.sleep(0.01)
            u = requests.put(f"{doc_url}/{did}", json={"status": "passed"}, timeout=10)
            codes.append(u.status_code)
            codes.append(requests.get(f"{doc_url}?status=passed", timeout=10).status_code)
            codes.append(requests.delete(f"{doc_url}/{did}", timeout=10).status_code)
            gone = requests.get(f"{doc_url}/{did}", timeout=10).status_code
            ok = (codes == [201, 200, 200, 200, 200] and gone == 404 and created["status"] == "scheduled"
                  and u.json()["status"] == "passed" and u.json()["updated_at"] > created["updated_at"])
            return ok, f"statuses={codes} after_delete={gone} default_status={created['status']}"

        @check("doc_validation_errors", "missing/enum/type/date -> 422, bad ObjectId -> 400, malformed JSON -> 400, non-JSON -> 415")
        def _():
            good = {"facility_name": "A", "program_element": "ROUTINE HEALTH INSPECTION",
                    "inspection_date": "2026-10-20T09:30:00Z"}
            got = [
                requests.post(doc_url, json={"description": "x"}, timeout=10).status_code,
                requests.post(doc_url, json={**good, "status": "closed"}, timeout=10).status_code,
                requests.post(doc_url, json={**good, "facility_name": 5}, timeout=10).status_code,
                requests.post(doc_url, json={**good, "inspection_date": "16/10/2026"}, timeout=10).status_code,
                requests.get(f"{doc_url}/not-an-id", timeout=10).status_code,
                requests.post(doc_url, data="{bad", headers={"Content-Type": "application/json"}, timeout=10).status_code,
                requests.post(doc_url, data="x", headers={"Content-Type": "text/plain"}, timeout=10).status_code,
            ]
            r = requests.post(doc_url, json={"description": "x"}, timeout=10).json()
            clear = r.get("error") == "validation_error" and {"facility_name", "program_element", "inspection_date"} \
                <= {e["field"] for e in r["detail"]}
            return got == [422, 422, 422, 422, 400, 400, 415] and clear, f"statuses={got} field_level_messages={clear}"

        @check("chat_returns_reply_and_memory", "POST /api/chat -> 200, non-empty reply, memory_used + usage objects")
        def _():
            r = requests.post(f"{BASE_URL}/api/chat", timeout=900, json={
                "user_id": user_id, "session_id": f"{user_id}-s1",
                "message": "Hi, I am a verification user. My test facility code is FA0000001."})
            b = r.json()
            ok = (r.status_code == 200 and b["reply"].strip() and
                  {"short_term_count", "short_term", "session_summary", "lifetime_summary", "episodic_facts"}
                  <= set(b["memory_used"]) and b["usage"]["prompt_tokens"] > 0
                  and b["usage"]["components"]["system_primer"] > 0)
            return ok, f"status={r.status_code} reply_chars={len(b.get('reply', ''))} prompt_tokens={b['usage']['prompt_tokens']}"

        @check("memory_and_aggregate_endpoints", "GET /api/memory has the 2 messages; GET /api/aggregate counts them by date")
        def _():
            m = requests.get(f"{BASE_URL}/api/memory/{user_id}", timeout=10)
            a = requests.get(f"{BASE_URL}/api/aggregate/{user_id}", timeout=10)
            roles = [x["role"] for x in m.json()["messages"]]
            agg = a.json()
            ok = (m.status_code == 200 and roles == ["user", "assistant"] and a.status_code == 200
                  and agg["total_messages"] == 2 and len(agg["daily_message_counts"]) == 1)
            missing = requests.get(f"{BASE_URL}/api/memory/{PREFIX}-nobody-{tag}", timeout=10).status_code
            return ok and missing == 404, f"memory roles={roles} aggregate={agg.get('daily_message_counts')} unknown_user={missing}"
    finally:
        if server is not None:
            server.terminate()
        try:
            from mongo import get_db

            db = get_db()
            for coll in ("messages", "summaries", "episodes"):
                db[coll].delete_many({"user_id": user_id})
        except Exception:  # noqa: BLE001 - cleanup is best effort
            pass

    @check("part3_raw_data", "raw/memory_turns.csv has 35 turns (30 conversation + 5 probes) for each of the 4 settings")
    def _():
        with (RAW_DIR / "memory_turns.csv").open() as fh:
            rows = list(csv.DictReader(fh))
        per = {label: sum(r["setting"] == label for r in rows) for label, _ in EXPERIMENT_SETTINGS}
        scored = all(r["probe_score"] for r in rows if r["kind"] == "probe")
        return all(v == 35 for v in per.values()) and scored, per

    @check("memory_probes_file", "memory_probes.yaml: 5 probes with criteria and a 1-5 rubric")
    def _():
        p = yaml.safe_load(PROBES_FILE.read_text())
        ok = len(p["probes"]) == 5 and sorted(p["rubric"]) == [1, 2, 3, 4, 5] and all(x["criteria"] for x in p["probes"])
        return ok, f"{len(p['probes'])} probes, rubric levels {sorted(p['rubric'])}"

    @check("agent_md_instructions", "AGENT.md has >= 5 instructions across >= 3 required categories")
    def _():
        cats, current = {}, None
        wanted = ["project description", "technology stack", "coding conventions", "testing approach", "prohibited actions"]
        for line in AGENT_MD.read_text().splitlines():
            if line.startswith("## "):
                current = line[3:].strip().lower()
            elif line.startswith("- ") and current in wanted:
                cats[current] = cats.get(current, 0) + 1
        return sum(cats.values()) >= 5 and len(cats) >= 3, cats

    @check("memory_consolidation_pair", "MEMORY.original.md is 55 lines and needs consolidation; consolidated is < 40 lines")
    def _():
        orig = (MEMORY_TEST_DIR / "MEMORY.original.md").read_text()
        cons = (MEMORY_TEST_DIR / "MEMORY.consolidated.md").read_text()
        audit = json.loads((RAW_DIR / "consolidation_audit.json").read_text())
        ok = (len(orig.splitlines()) == 55 and needs_consolidation(orig)[0] and len(cons.splitlines()) < 40
              and audit["no_silent_deletion"])
        return ok, (f"original {len(orig.splitlines())} lines ({count_memory_lines(orig)} non-comment), consolidated "
                    f"{len(cons.splitlines())} lines; contradictions correct {audit['contradictions_correct']}/5")

    @check("app_code_unchanged", "Self-check did not modify application code (git status of code/ unchanged)")
    def _():
        after = git("status", "--porcelain", "code")
        return after == code_status_before, "unchanged" if after == code_status_before else after

    result = {
        "homework": HW,
        "sid4": SID4,
        "commit": git("rev-parse", "HEAD"),
        "tag_hw6": git("rev-list", "-n", "1", "hw6") or None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "configuration": {
            "PORT_BASE": PORT_BASE, "PREFIX": PREFIX, "SEED": SEED, "VERIFY_SEED": VERIFY_SEED,
            "DOMAIN_ID": DOMAIN_ID, "mongo_database": MONGO_DB, "local_model": LOCAL_MODEL,
            "embedding_model": "sentence-transformers/all-MiniLM-L6-v2 (fastembed)",
            "memory": {"SHORT_TERM_N_default": 12, "SUMMARIZE_EVERY_USER_MSGS": 5, "EPISODE_TOP_K": 3,
                       "experiment_settings": [label for label, _ in EXPERIMENT_SETTINGS]},
        },
        "checks": checks,
        "passed": sum(c["passed"] for c in checks),
        "total": len(checks),
        "all_passed": all(c["passed"] for c in checks),
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "verification.json").write_text(json.dumps(result, indent=2))
    print(f"\n{result['passed']}/{result['total']} checks passed -> {REPORT_DIR / 'verification.json'}")
    sys.exit(0 if result["all_passed"] else 1)


if __name__ == "__main__":
    main()
