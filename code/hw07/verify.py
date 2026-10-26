"""HW7 self-check (smoke test) -> reports/hw07/verification.json.

    make verify-hw07        (or: python code/hw07/verify.py)

Starts the FastAPI backend on PORT_BASE if nothing is listening there yet,
then checks behaviour (status codes, shapes, counts, decisions, hashes) -
never wording: config, offline tests, lint setup, the MySQL users table,
JWT login/me/expiry, role checks on the domain routes, one live run of the
hand-written agent loop on fixed task A plus the nonexistent-id recovery,
the MRKL tool guards, the saved Part 2-6 raw data and pricing snapshots, and
the 10-command safety gate. The record it creates is deleted again, and the
last check confirms `git status` of code/ is unchanged.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

from hw07_config import (
    AGENT_TEMPERATURE,
    BASE_URL,
    BIKESHARE_CASES_DIR,
    BIKESHARE_RAW_DIR,
    DB_NAME,
    DOMAIN_ID,
    FIXTURES_DIR,
    HW,
    LOCAL_MODEL,
    MYSQL_ADMIN_URL,
    PORT_BASE,
    PREFIX,
    PRICING_URL,
    RAW_DIR,
    REPO_ROOT,
    REPORT_DIR,
    ROLE_PASSWORD,
    ROLE_USERS,
    SEED,
    SID4,
    VERIFY_SEED,
    WEB_APP_DIR,
)

# hw07_config puts code/ on sys.path, so it must be imported before the project packages.
# isort: split
from agent_loop import OllamaChatModel, make_domain_toolset, run_agent  # noqa: E402
from agent_loop.tasks import chain_complete, load_tasks  # noqa: E402
from bikeshare_agent import SnapshotRegistry, TripStore, calculator, csv_sql, policy_retriever  # noqa: E402
from domain_tools import execute_tool  # noqa: E402
from file_tools import confirm_bash, is_destructive  # noqa: E402

checks: list[dict] = []


def check(name: str, description: str):
    """Decorator: run the check now, record PASS/FAIL with evidence."""
    def wrap(fn):
        try:
            passed, evidence = fn()
        except Exception as exc:  # noqa: BLE001
            passed, evidence = False, f"raised {type(exc).__name__}: {exc}"
        checks.append({"name": name, "description": description, "passed": bool(passed), "evidence": evidence})
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {evidence}")
    return wrap


def git(*args: str) -> str:
    """Run git in the repo and return stdout."""
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()


def port_open(port: int) -> bool:
    """True if something listens on 127.0.0.1:port."""
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def login(role: str) -> requests.Response:
    """POST /auth/login for the role's demo user."""
    return requests.post(f"{BASE_URL}/auth/login", json={"username": ROLE_USERS[role], "password": ROLE_PASSWORD},
                         timeout=15)


def auth(token: str) -> dict:
    """Bearer header."""
    return {"Authorization": f"Bearer {token}"}


def read_csv(path) -> list[dict]:
    """Rows of a raw CSV file."""
    with path.open() as fh:
        return list(csv.DictReader(fh))


def main() -> None:
    """Run every check and write verification.json."""
    code_status_before = git("status", "--porcelain", "code")
    rng = random.Random(VERIFY_SEED)
    print(f"HW7 verify - {git('config', 'user.name')} - {datetime.now():%Y-%m-%d %H:%M:%S} - "
          f"commit {git('rev-parse', '--short', 'HEAD')}\n")

    @check("config_values", "Section 0 values derive from SID4 = 7117")
    def _():
        ok = (PORT_BASE == 8000 + SID4 % 900 and PREFIX == f"s{SID4}" and SEED == SID4
              and VERIFY_SEED == 260000 + SID4 and DOMAIN_ID == SID4 % 8)
        return ok, f"PORT_BASE={PORT_BASE} PREFIX={PREFIX} SEED={SEED} VERIFY_SEED={VERIFY_SEED} DOMAIN_ID={DOMAIN_ID}"

    @check("offline_test_suite", "HW7 offline tests (JWT/RBAC, loop, Reflexion, MRKL tools, file tools, gate) pass")
    def _():
        proc = subprocess.run([sys.executable, str(REPO_ROOT / "code" / "tests" / "test_hw07.py")],
                              capture_output=True, text=True, timeout=300)
        return proc.returncode == 0, proc.stdout.strip().splitlines()[-1]

    @check("lint_setup", "Ruff configured in pyproject.toml, Ruff hook in .pre-commit-config.yaml, hook installed")
    def _():
        pyproject = (REPO_ROOT / "pyproject.toml").read_text()
        hook_cfg = (REPO_ROOT / ".pre-commit-config.yaml").read_text()
        installed = (REPO_ROOT / ".git" / "hooks" / "pre-commit").exists()
        ok = "[tool.ruff" in pyproject and "ruff-pre-commit" in hook_cfg and installed
        return ok, (f"ruff config={'[tool.ruff' in pyproject} hook config={'ruff-pre-commit' in hook_cfg} "
                    f"installed={installed}")

    @check("mysql_users_table", "users has id PK, unique username, password_hash, role CHECK; role users hashed")
    def _():
        from sqlalchemy import bindparam, create_engine, text

        engine = create_engine(f"{MYSQL_ADMIN_URL}{DB_NAME}")
        with engine.connect() as conn:
            cols = {r[0] for r in conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_schema=:d AND table_name='users'"),
                {"d": DB_NAME})}
            uniques = {r[0] for r in conn.execute(text(
                "SELECT constraint_name FROM information_schema.table_constraints "
                "WHERE table_schema=:d AND table_name='users'"), {"d": DB_NAME})}
            query = text("SELECT username, role, password_hash FROM users WHERE username IN :u")
            users = conn.execute(query.bindparams(bindparam("u", expanding=True)),
                                 {"u": list(ROLE_USERS.values())}).all()
        roles = {u.username: u.role for u in users}
        hashed = all(u.password_hash.startswith("pbkdf2_sha256$") and ROLE_PASSWORD not in u.password_hash
                     for u in users)
        ok = ({"id", "username", "password_hash", "role"} <= cols and "uq_users_username" in uniques
              and "ck_users_role" in uniques and roles == {v: k for k, v in ROLE_USERS.items()} and hashed)
        return ok, f"columns ok={ {'id', 'username', 'password_hash', 'role'} <= cols} roles={roles} hashed={hashed}"

    server = None
    if not port_open(PORT_BASE):
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(PORT_BASE)],
            cwd=WEB_APP_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(240):
            if port_open(PORT_BASE):
                break
            time.sleep(0.5)
    created_id = None
    try:
        @check("login_valid_and_invalid", "POST /auth/login: valid -> 200 + 3-part JWT; wrong password -> 401")
        def _():
            good = login("writer")
            bad = requests.post(f"{BASE_URL}/auth/login", json={"username": ROLE_USERS["writer"], "password": "x"},
                                timeout=15)
            tok = good.json().get("access_token", "")
            return (good.status_code == 200 and tok.count(".") == 2 and bad.status_code == 401,
                    f"valid={good.status_code} token_parts={tok.count('.') + 1} invalid={bad.status_code}")

        @check("auth_me_token_checks", "GET /auth/me: none 401, invalid 401, expired 401, valid 200 with role")
        def _():
            import jwt

            sys.path.insert(0, str(WEB_APP_DIR))
            from security import JWT_ALGORITHM, JWT_ISSUER, JWT_SECRET

            tok = login("reader").json()["access_token"]
            me = requests.get(f"{BASE_URL}/auth/me", headers=auth(tok), timeout=15)
            past = datetime.now(timezone.utc) - timedelta(hours=2)
            expired = jwt.encode({"sub": me.json()["username"], "uid": me.json()["id"], "role": "reader",
                                  "iss": JWT_ISSUER, "iat": past, "exp": past + timedelta(minutes=30)},
                                 JWT_SECRET, algorithm=JWT_ALGORITHM)
            got = [requests.get(f"{BASE_URL}/auth/me", timeout=15).status_code,
                   requests.get(f"{BASE_URL}/auth/me", headers=auth("a.b.c"), timeout=15).status_code,
                   requests.get(f"{BASE_URL}/auth/me", headers=auth(expired), timeout=15).status_code, me.status_code]
            return got == [401, 401, 401, 200] and me.json()["role"] == "reader", \
                f"statuses={got} role={me.json().get('role')}"

        @check("rbac_domain_routes", "records: create reader 403 / writer 201; delete writer 403 / moderator 200; "
                                     "list reader 200; no token 401")
        def _():
            nonlocal created_id
            tokens = {r: login(r).json()["access_token"] for r in ROLE_USERS}
            body = {"inspection_code": f"INS-{rng.randint(900000, 999999)}", "facility_name": "FA0717117 - VERIFY",
                    "site_address": "1 WASHINGTON SQ, SAN JOSE, CA 95192", "score": 90, "inspector_id": 1}
            url = f"{BASE_URL}/api/records"
            got = [requests.post(url, json=body, headers=auth(tokens["reader"]), timeout=15).status_code]
            created = requests.post(url, json=body, headers=auth(tokens["writer"]), timeout=15)
            got.append(created.status_code)
            created_id = created.json().get("id")
            got.append(requests.delete(f"{url}/{created_id}", headers=auth(tokens["writer"]), timeout=15).status_code)
            deleted = requests.delete(f"{url}/{created_id}", headers=auth(tokens["moderator"]), timeout=15)
            got.append(deleted.status_code)
            if got[-1] == 200:
                created_id = None
            got.append(requests.get(f"{url}?limit=2", headers=auth(tokens["reader"]), timeout=15).status_code)
            got.append(requests.get(f"{url}?limit=2", timeout=15).status_code)
            return got == [403, 201, 403, 200, 200, 401], f"statuses={got}"
    finally:
        if created_id:
            try:
                requests.delete(f"{BASE_URL}/api/records/{created_id}",
                                headers=auth(login("moderator").json()["access_token"]), timeout=15)
            except requests.RequestException:
                pass
        if server is not None:
            server.terminate()

    @check("agent_loop_task_A", "run_agent completes fixed task A (search -> detail) on qwen3:8b with >= 2 tool calls")
    def _():
        task = load_tasks()[0]
        result = run_agent(task.prompt, model=OllamaChatModel(temperature=0.0, seed=VERIFY_SEED),
                           toolset=make_domain_toolset(), log=None)
        ok = result["stop_reason"] == "final_answer" and result["tool_calls"] >= 2 and chain_complete(task, result)
        return ok, (f"stop={result['stop_reason']} tool_calls={result['tool_calls']} "
                    f"tools={[c['tool'] for c in result['trace']]} chain_complete={chain_complete(task, result)}")

    @check("error_recovery_message", "execute_tool on nonexistent INS-999999 returns ok=false with a 'not found' error")
    def _():
        env = json.loads(execute_tool("get_inspection", {"inspection_code": "INS-999999"}))
        return env["ok"] is False and "not found" in env["error"], env["error"]

    @check("mrkl_tool_guards", "csv_sql rejects non-SELECT/multi-statement; calculator rejects non-arithmetic; "
                               "policy_retriever returns passages with source+score")
    def _():
        store = TripStore((BIKESHARE_CASES_DIR / "ppu_wins.csv").read_text())
        sql = [csv_sql(q, store=store)["success"] for q in
               ("SELECT COUNT(*) AS n FROM trips", "DELETE FROM trips", "SELECT 1; DROP TABLE trips")]
        calc = [calculator(e)["success"] for e in ("(1+0.19*7)*8", "__import__('os')", "2**99")]
        ret = policy_retriever(f"file://{(FIXTURES_DIR / 'hostile_pricing.html').resolve()}", "month pass price", 2,
                               registry=SnapshotRegistry())
        ok = sql == [True, False, False] and calc == [True, False, False] and ret["success"] and \
            all({"text", "source", "score"} <= set(p) for p in ret["data"]["passages"]) and store.row_count() == 520
        return ok, f"csv_sql={sql} calculator={calc} retriever_passages={len(ret['data']['passages'])}"

    @check("raw_reliability", "raw/toolcall_reliability.csv has >= 20 attempts across tasks A, B, C")
    def _():
        rows = read_csv(RAW_DIR / "toolcall_reliability.csv")
        per = {t: sum(r["task_id"] == t for r in rows) for t in "ABC"}
        return len(rows) >= 20 and all(per.values()), f"{len(rows)} attempts {per}"

    @check("raw_reflexion", "raw/reflexion_comparison.csv has both loops on A, B, C; reflections.jsonl has evidence")
    def _():
        rows = read_csv(RAW_DIR / "reflexion_comparison.csv")
        pairs = {(r["loop"], r["task_id"]) for r in rows}
        refl = [json.loads(line) for line in (RAW_DIR / "reflections.jsonl").read_text().splitlines() if line]
        evidenced = all(r["user_id"] and r["run_id"] and r["evidence"].get("assertion") for r in refl)
        ok = pairs >= {(loop, t) for loop in ("original", "reflexion") for t in "ABC"} and bool(refl) and evidenced
        return ok, f"{len(rows)} rows, loops x tasks={len(pairs)}, reflections={len(refl)} with evidence={evidenced}"

    @check("bikeshare_scenarios", "membership_wins -> Buy Monthly Membership, ppu_wins -> Pay Per Ride/Minute; >= 500 "
                                  "rows each; saved snapshot text matches its SHA-256")
    def _():
        expected = {"membership_wins": "Buy Monthly Membership", "ppu_wins": "Pay Per Ride/Minute"}
        found = {}
        for name, decision in expected.items():
            summary = json.loads((BIKESHARE_RAW_DIR / f"{name}_trip_summary.json").read_text())
            runs = sorted((BIKESHARE_RAW_DIR / "runs").glob(f"*_{name}_*"))
            run = runs[-1]
            result = json.loads((run / "result.json").read_text())
            meta = json.loads((run / "snapshot_meta.json").read_text())[0]
            text_ok = hashlib.sha256((run / meta["text_file"]).read_bytes()).hexdigest() == meta["text_sha256"]
            found[name] = (result["decision"] == decision and summary["rows"] >= 500 and text_ok
                           and meta["url"] == PRICING_URL and result["stop_reason"] == "final_answer")
        return all(found.values()), found

    @check("raw_injection", "raw/injection_attacks.json: 3 configs x 3 attacks; no non-SELECT executed with the tool "
                            "defense on")
    def _():
        data = json.loads((RAW_DIR / "injection_attacks.json").read_text())
        configs = {r["config"] for r in data["runs"]}
        tool_on = [r for r in data["runs"] if r["defenses"]["enforce_select"]]
        sql_safe = all(r["outcome"]["sql_misuse"]["outcome"] != "SUCCEEDED" and r["rows_after"] == r["rows_before"]
                       for r in tool_on)
        boundary = data["tool_boundary_check"]["enforce_select"]["success"] is False
        ok = configs == {"before", "prompt", "prompt_tool"} and sql_safe and boundary and tool_on
        return ok, f"configs={sorted(configs)} runs={len(data['runs'])} tool-defended SQL safe={sql_safe}"

    @check("safety_gate_10_commands", "is_destructive -> bool; confirm_bash: 5 allowed, 5 blocked, destructive "
                                      "allowed only with confirmation")
    def _():
        rows = read_csv(RAW_DIR / "safety_gate_tests.csv")
        live = [(r["command"], confirm_bash(r["command"]).decision == r["expected"]) for r in rows]
        types_ok = all(isinstance(is_destructive(r["command"]), bool) for r in rows)
        confirm_ok = (confirm_bash("rm -rf build", auto_approve=True).allowed
                      and not confirm_bash("rm -rf build").allowed)
        ok = len(rows) == 10 and all(c for _, c in live) and types_ok and confirm_ok and \
            sum(r["expected"] == "allow" for r in rows) == 5
        return ok, f"{sum(c for _, c in live)}/10 correct, bool={types_ok}, confirmation path={confirm_ok}"

    @check("app_code_unchanged", "Self-check did not modify application code (git status of code/ unchanged)")
    def _():
        after = git("status", "--porcelain", "code")
        return after == code_status_before, "unchanged" if after == code_status_before else after

    result = {
        "homework": HW,
        "sid4": SID4,
        "commit": git("rev-parse", "HEAD"),
        "tag_hw7": git("rev-list", "-n", "1", "hw7") or None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "configuration": {
            "PORT_BASE": PORT_BASE, "PREFIX": PREFIX, "SEED": SEED, "VERIFY_SEED": VERIFY_SEED,
            "DOMAIN_ID": DOMAIN_ID, "mysql_database": DB_NAME, "local_model": LOCAL_MODEL,
            "agent_settings": {"temperature": AGENT_TEMPERATURE, "reasoning": False,
                               "verify_run": {"temperature": 0.0, "seed": VERIFY_SEED}},
            "auth": {"scheme": "JWT bearer (HS256)", "roles": list(ROLE_USERS)},
            "bikeshare": {"city": "Bay Wheels (SF Bay Area)", "pricing_url": PRICING_URL},
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
