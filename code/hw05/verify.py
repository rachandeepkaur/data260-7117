"""HW5 self-check (smoke test) -> reports/hw05/verification.json.

    make verify-hw05        (or: python code/hw05/verify.py)

Starts the FastAPI backend on PORT_BASE if nothing is listening there yet,
then checks behavior (status codes, envelope shape, counts), not wording:
backend + both entities + relationship + delete restriction, both MCP servers
answering a tool call over STDIO, the offline test suite, seeded fault
injection reproducibility and the safety rule. Temporary records are named
from VERIFY_SEED and deleted again. It never writes application code: the
last check confirms `git status` of code/ is unchanged.
"""
from __future__ import annotations

import asyncio
import json
import random
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone

import requests

from hw05_config import (
    BASE_URL,
    DB_NAME,
    DEMO_USER_EMAIL,
    DEMO_USER_PASSWORD,
    DOMAIN_ID,
    HW,
    LOCAL_MODEL,
    MCP_SERVERS_DIR,
    PORT_BASE,
    PREFIX,
    REPO_ROOT,
    REPORT_DIR,
    SEED,
    SID4,
    VERIFY_SEED,
    WEB_APP_DIR,
)
from mcp_tool_calls import call_tools

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
    rng = random.Random(VERIFY_SEED)
    tag = f"{rng.randint(100000, 999999)}"

    @check("config_values", "Section 0 values derive from SID4 = 7117")
    def _():
        ok = (PORT_BASE == 8000 + SID4 % 900 and PREFIX == f"s{SID4}" and SEED == SID4
              and VERIFY_SEED == 260000 + SID4 and DOMAIN_ID == SID4 % 8)
        return ok, f"PORT_BASE={PORT_BASE} PREFIX={PREFIX} SEED={SEED} VERIFY_SEED={VERIFY_SEED} DOMAIN_ID={DOMAIN_ID}"

    @check("offline_test_suite", "Part 4/5 offline test runner passes every test")
    def _():
        proc = subprocess.run([sys.executable, str(REPO_ROOT / "code" / "tests" / "test_hw05_tools.py")],
                              capture_output=True, text=True, timeout=120)
        return proc.returncode == 0, proc.stdout.strip().splitlines()[-1]

    @check("fault_injection_reproducible", "Same VERIFY_SEED + rate -> identical failure sequence (0/20/50%)")
    def _():
        from domain_tools.resilience import FaultInjector

        def seq(rate):
            inj, out = FaultInjector(rate, VERIFY_SEED), []
            for _ in range(150):
                try:
                    inj.maybe_fail()
                    out.append(0)
                except Exception:  # noqa: BLE001
                    out.append(1)
            return out
        same = all(seq(r) == seq(r) for r in (0.0, 0.2, 0.5))
        return same and sum(seq(0.0)) == 0, f"failures per 150 draws: {[sum(seq(r)) for r in (0.0, 0.2, 0.5)]}"

    @check("safety_rule_blocks", "execute_tool returns {ok:false,data:null,error} for a <5-row aggregate")
    def _():
        from domain_tools import execute_tool
        from domain_tools.fixtures import make_fixture_repo

        blocked = json.loads(execute_tool("inspection_stats", {"facility_query": "YUMMY"}, repo=make_fixture_repo()))
        allowed = json.loads(execute_tool("inspection_stats", {"inspector_id": 1}, repo=make_fixture_repo()))
        return (blocked["ok"] is False and blocked["data"] is None and blocked["error"]
                and allowed["ok"] is True), f"blocked.ok={blocked['ok']} allowed.ok={allowed['ok']}"

    @check("meals_mcp_server", "meals MCP server starts over STDIO, lists 4 tools, answers search_meals_by_name")
    def _():
        res = asyncio.run(call_tools(str(MCP_SERVERS_DIR / "meals_server.py"),
                                     [("search_meals_by_name", {"query": "Arrabiata", "limit": 3})]))
        out = res["calls"][0]["output"]
        ok = len(res["tools"]) == 4 and not res["calls"][0]["is_error"] and out["count"] >= 1 \
            and {"id", "name", "area", "category", "thumb"} <= set(out["results"][0])
        return ok, f"tools={res['tools']} count={out.get('count')}"

    @check("domain_mcp_server", "s7117-inspections MCP server answers valid calls ok and invalid calls with an envelope error")
    def _():
        res = asyncio.run(call_tools(str(MCP_SERVERS_DIR / "inspections_server.py"), [
            ("search_inspections", {"query": "golden", "limit": 3}),
            ("search_inspections", {"query": "golden", "limit": 500}),
            ("inspection_stats", {"inspector_id": 1}),
        ]))
        outs = [c["output"] for c in res["calls"]]
        ok = (len(res["tools"]) == 3 and all(set(o) == {"ok", "data", "error"} for o in outs)
              and outs[0]["ok"] and not outs[1]["ok"] and outs[2]["ok"])
        return ok, f"tools={res['tools']} ok flags={[o['ok'] for o in outs]}"

    @check("mysql_schema", f"{DB_NAME}: inspectors exists; inspections has unique code + FK ON DELETE RESTRICT")
    def _():
        from sqlalchemy import text

        from domain_tools.repository import SqlRepository

        with SqlRepository().engine.connect() as conn:
            n_inspectors = conn.execute(text("SELECT COUNT(*) FROM inspectors")).scalar()
            rule = conn.execute(text(
                "SELECT DELETE_RULE FROM information_schema.referential_constraints "
                "WHERE constraint_schema = :db AND constraint_name = 'fk_inspections_inspector'"), {"db": DB_NAME}).scalar()
            uniq = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = :db "
                "AND table_name = 'inspections' AND index_name = 'uq_inspections_code' AND non_unique = 0"),
                {"db": DB_NAME}).scalar()
        return n_inspectors >= 1 and rule == "RESTRICT" and uniq == 1, \
            f"inspectors={n_inspectors} delete_rule={rule} unique_code_index={bool(uniq)}"

    server = None
    if not port_open(PORT_BASE):
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(PORT_BASE)],
            cwd=WEB_APP_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            if port_open(PORT_BASE):
                break
            time.sleep(0.5)
    try:
        s = requests.Session()

        @check("backend_on_port_base", f"FastAPI backend responds on PORT_BASE {PORT_BASE}")
        def _():
            r = requests.get(f"{BASE_URL}/openapi.json", timeout=10)
            paths = r.json()["paths"]
            return r.status_code == 200 and "/api/inspectors/{inspector_id}/inspections" in paths, \
                f"GET /openapi.json -> {r.status_code}, {len(paths)} paths"

        @check("login", "Demo user can log in (session cookie set)")
        def _():
            r = s.post(f"{BASE_URL}/api/auth/login", json={"email": DEMO_USER_EMAIL, "password": DEMO_USER_PASSWORD},
                       timeout=10)
            return r.status_code == 200 and bool(s.cookies), f"POST /api/auth/login -> {r.status_code}"

        @check("inspector_crud_and_relationship",
               "Inspector POST->GET->PUT->list; inspection POST linked to it; relationship query; cleanup")
        def _():
            codes = []
            r = s.post(f"{BASE_URL}/api/inspectors", json={"full_name": f"Verify {tag}", "district": "Test District",
                                                         "email": f"verify.{tag}@s7117.dev"}, timeout=10)
            codes.append(r.status_code)
            iid = r.json()["id"]
            codes.append(s.get(f"{BASE_URL}/api/inspectors/{iid}", timeout=10).status_code)
            codes.append(s.put(f"{BASE_URL}/api/inspectors/{iid}", json={"district": "Updated"}, timeout=10).status_code)
            codes.append(s.get(f"{BASE_URL}/api/inspectors?page=1&page_size=5", timeout=10).status_code)
            r = s.post(f"{BASE_URL}/api/records", json={
                "inspection_code": f"INS-9{tag[:5]}", "facility_name": f"FA{tag} - VERIFY CAFE",
                "site_address": "1 VERIFY WAY, SAN JOSE, CA 95112", "inspector_id": iid}, timeout=10)
            codes.append(r.status_code)
            rid = r.json()["id"]
            rel = s.get(f"{BASE_URL}/api/inspectors/{iid}/inspections", timeout=10)
            blocked = s.delete(f"{BASE_URL}/api/inspectors/{iid}", timeout=10).status_code  # still referenced
            codes.append(s.delete(f"{BASE_URL}/api/records/{rid}", timeout=10).status_code)
            codes.append(s.delete(f"{BASE_URL}/api/inspectors/{iid}", timeout=10).status_code)
            gone = s.get(f"{BASE_URL}/api/inspectors/{iid}", timeout=10).status_code
            ok = (codes == [201, 200, 200, 200, 201, 200, 200] and rel.status_code == 200
                  and [x["id"] for x in rel.json()] == [rid] and blocked == 409 and gone == 404)
            return ok, f"statuses={codes} relationship={rel.status_code} delete_while_referenced={blocked} after_delete={gone}"

        @check("validation_and_constraints", "Bad email/code -> 422, duplicate code/email -> 409, missing -> 404")
        def _():
            bad_email = s.post(f"{BASE_URL}/api/inspectors", json={"full_name": "X Y", "district": "Z Z",
                                                                  "email": "not-an-email"}, timeout=10).status_code
            bad_code = s.post(f"{BASE_URL}/api/records", json={"inspection_code": "12345", "facility_name": "A",
                                                               "site_address": "B", "inspector_id": 1},
                              timeout=10).status_code
            dup_code = s.post(f"{BASE_URL}/api/records", json={"inspection_code": "INS-000001", "facility_name": "A",
                                                               "site_address": "B", "inspector_id": 1},
                              timeout=10).status_code
            first = s.get(f"{BASE_URL}/api/inspectors/1", timeout=10).json()
            dup_email = s.post(f"{BASE_URL}/api/inspectors", json={"full_name": "X Y", "district": "Z Z",
                                                                  "email": first["email"]}, timeout=10).status_code
            missing = s.get(f"{BASE_URL}/api/inspectors/999999", timeout=10).status_code
            got = [bad_email, bad_code, dup_code, dup_email, missing]
            return got == [422, 422, 409, 409, 404], f"[bad_email, bad_code, dup_code, dup_email, missing]={got}"
    finally:
        if server is not None:
            server.terminate()

    @check("app_code_unchanged", "Self-check did not modify application code (git status of code/ unchanged)")
    def _():
        after = git("status", "--porcelain", "code")
        return after == code_status_before, "unchanged" if after == code_status_before else after

    result = {
        "homework": HW,
        "sid4": SID4,
        "commit": git("rev-parse", "HEAD"),
        "tag_hw5": git("rev-list", "-n", "1", "hw5") or None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "configuration": {
            "PORT_BASE": PORT_BASE, "PREFIX": PREFIX, "SEED": SEED, "VERIFY_SEED": VERIFY_SEED,
            "DOMAIN_ID": DOMAIN_ID, "database": DB_NAME, "local_model": LOCAL_MODEL,
            "retry_policy": "3 attempts, 2s timeout/attempt, backoff 0.1s x2 cap 1s",
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
