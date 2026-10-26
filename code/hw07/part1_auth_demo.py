"""HW7 Part 1: JWT login, /auth/me and role checks against the running API.

    make run-api            # terminal 1 (PORT_BASE 8817)
    make auth-demo-hw07     # terminal 2  (or: python code/hw07/part1_auth_demo.py)

Prints every request with its HTTP status and a short body, in the order the
report's screenshots need, and saves them to raw/part1_auth_calls.json:
    login valid (200 + token) / invalid (401)
    /auth/me: no token (401), malformed token (401), expired token (401), valid (200)
    create record: reader (403), writer (201)
    delete record: writer (403), moderator (200)
    list + read records with a reader token (200)
The expired token is signed with the server's JWT secret but an exp in the past.
The record created here is deleted again by the moderator call.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone

import jwt
import requests

from hw07_config import BASE_URL, RAW_DIR, ROLE_PASSWORD, ROLE_USERS, VERIFY_SEED, use_web_app_imports

use_web_app_imports()
from security import JWT_ALGORITHM, JWT_ISSUER, JWT_SECRET  # noqa: E402

calls: list[dict] = []


def show(label: str, method: str, path: str, token: str | None = None, body: dict | None = None,
         expect: int | None = None) -> requests.Response:
    """Send one request, print status + body excerpt, and record it."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = requests.request(method, f"{BASE_URL}{path}", headers=headers, json=body, timeout=15)
    try:
        payload = resp.json()
    except ValueError:
        payload = resp.text
    shown = json.dumps(payload)
    if isinstance(payload, dict) and "access_token" in payload:
        shown = json.dumps({**payload, "access_token": payload["access_token"][:32] + "..."})
    mark = "" if expect is None else ("  [as expected]" if resp.status_code == expect else f"  [EXPECTED {expect}]")
    auth = f"Bearer {token[:16]}..." if token else "(no Authorization header)"
    print(f"\n# {label}\n{method} {path}   {auth}" + (f"\n  body: {json.dumps(body)}" if body else "")
          + f"\n  -> {resp.status_code} {resp.reason}{mark}\n  {shown[:400]}")
    calls.append({"label": label, "method": method, "path": path, "auth": "bearer" if token else None,
                  "request_body": body, "status": resp.status_code, "expected": expect,
                  "response": payload if not isinstance(payload, dict) or "access_token" not in payload
                  else {**payload, "access_token": "<redacted>"}})
    return resp


def login(role: str) -> str:
    """Token for the role's demo user."""
    resp = requests.post(f"{BASE_URL}/auth/login", json={"username": ROLE_USERS[role], "password": ROLE_PASSWORD},
                         timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


def main() -> None:
    """Run the Part 1 request sequence."""
    print(f"HW7 Part 1 auth demo - Rachandeep Kaur - {datetime.now():%Y-%m-%d %H:%M:%S} - {BASE_URL}")
    code = f"INS-{random.Random(VERIFY_SEED).randint(900000, 999999)}"

    r = show("1. Login with valid credentials (writer) -> 200 + JWT", "POST", "/auth/login",
             body={"username": ROLE_USERS["writer"], "password": ROLE_PASSWORD}, expect=200)
    writer = r.json()["access_token"]
    show("2. Login with a wrong password -> 401", "POST", "/auth/login",
         body={"username": ROLE_USERS["writer"], "password": "wrong-password"}, expect=401)
    show("3. GET /auth/me without a token -> 401", "GET", "/auth/me", expect=401)
    show("4. GET /auth/me with a malformed/invalid token -> 401", "GET", "/auth/me",
         token="eyJhbGciOiJIUzI1NiJ9.not-a-real-token.signature", expect=401)
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    me = requests.get(f"{BASE_URL}/auth/me", headers={"Authorization": f"Bearer {writer}"}, timeout=15).json()
    expired = jwt.encode({"sub": me["username"], "uid": me["id"], "role": me["role"], "iss": JWT_ISSUER,
                          "iat": past, "exp": past + timedelta(minutes=30)}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    show("5. GET /auth/me with an EXPIRED token (signed, exp 90 min ago) -> 401", "GET", "/auth/me",
         token=expired, expect=401)
    show("6. GET /auth/me with a valid token -> 200 identity + role", "GET", "/auth/me", token=writer, expect=200)

    reader, moderator = login("reader"), login("moderator")
    record = {"inspection_code": code, "facility_name": "FA0717117 - HW7 JWT DEMO CAFE",
              "site_address": "1 WASHINGTON SQ, SAN JOSE, CA 95192", "score": 91, "inspector_id": 1}
    show("7. Create a record as READER -> 403", "POST", "/api/records", token=reader, body=record, expect=403)
    created = show("8. Create a record as WRITER -> 201", "POST", "/api/records", token=writer, body=record, expect=201)
    record_id = created.json().get("id") if created.status_code == 201 else None
    if record_id:
        show("9. Delete the record as WRITER -> 403", "DELETE", f"/api/records/{record_id}", token=writer, expect=403)
        show("10. Delete the record as MODERATOR -> 200", "DELETE", f"/api/records/{record_id}", token=moderator,
             expect=200)
    show("11. List records as READER -> 200", "GET", "/api/records?limit=3", token=reader, expect=200)
    show("12. Read one record as READER -> 200", "GET", "/api/records/1", token=reader, expect=200)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "part1_auth_calls.json").write_text(json.dumps(
        {"generated_at": datetime.now().isoformat(timespec="seconds"), "base_url": BASE_URL, "calls": calls},
        indent=2, default=str))
    ok = sum(c["status"] == c["expected"] for c in calls)
    print(f"\n{ok}/{len(calls)} responses had the expected status -> {RAW_DIR / 'part1_auth_calls.json'}")


if __name__ == "__main__":
    main()
