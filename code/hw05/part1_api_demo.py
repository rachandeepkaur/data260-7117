"""Part 1: exercise every inspector/inspection endpoint against the running API.

    make api-demo-hw05         (or: python code/hw05/part1_api_demo.py)

Needs `make run-api`. Same requests as reports/hw05/postman_collection.json:
CRUD for both entities, the relationship query, and the error cases (404,
422, 409). Temporary records are deleted again at the end. Saves every
request/response to reports/hw05/raw/part1_api_calls.json.
"""
from __future__ import annotations

import json

import requests

from hw05_config import BASE_URL, DEMO_USER_EMAIL, DEMO_USER_PASSWORD, RAW_DIR

s = requests.Session()
calls: list[dict] = []


def call(label: str, method: str, path: str, body: dict | None = None, expect: int | None = None):
    r = s.request(method, f"{BASE_URL}{path}", json=body, timeout=10)
    try:
        data = r.json()
    except ValueError:
        data = r.text
    ok = expect is None or r.status_code == expect
    calls.append({"label": label, "method": method, "path": path, "body": body, "status": r.status_code,
                  "expected": expect, "pass": ok, "total_count": r.headers.get("X-Total-Count"), "response": data})
    shown = json.dumps(data)
    print(f"[{'PASS' if ok else 'FAIL'}] {label}: {method} {path} -> {r.status_code}"
          f"{' (X-Total-Count ' + r.headers['X-Total-Count'] + ')' if 'X-Total-Count' in r.headers else ''}")
    print(f"       {shown[:260]}{'...' if len(shown) > 260 else ''}")
    return data


def main() -> None:
    call("login", "POST", "/api/auth/login", {"email": DEMO_USER_EMAIL, "password": DEMO_USER_PASSWORD}, 200)

    print("\n-- Inspectors (related entity)")
    ins = call("create inspector", "POST", "/api/inspectors",
               {"full_name": "Rachandeep Kaur", "district": "Downtown San Jose",
                "email": "rachandeep.kaur@sccgov-eh.org"}, 201)
    iid = ins["id"]
    call("list inspectors page 1", "GET", "/api/inspectors?page=1&page_size=5", expect=200)
    call("get inspector", "GET", f"/api/inspectors/{iid}", expect=200)
    call("update inspector", "PUT", f"/api/inspectors/{iid}", {"district": "Willow Glen"}, 200)

    print("\n-- Inspections (primary entity)")
    last = s.get(f"{BASE_URL}/api/records?limit=1", timeout=10).json()[0]
    code = f"INS-{last['id'] + 1:06d}"
    rec = call("create inspection", "POST", "/api/records",
               {"inspection_code": code, "facility_name": "FA0206933 - YUMMY KITCHEN",
                "site_address": "1711 BRANHAM LN A9, SAN JOSE, CA 95118", "score": 94, "inspector_id": iid}, 201)
    rid = rec["id"]
    call("list inspections", "GET", "/api/records?limit=3&offset=0", expect=200)
    call("get inspection", "GET", f"/api/records/{rid}", expect=200)
    call("update inspection", "PUT", f"/api/records/{rid}", {"score": 88}, 200)

    print("\n-- Relationship query")
    call("inspections of new inspector", "GET", f"/api/inspectors/{iid}/inspections", expect=200)
    call("inspections of inspector 1", "GET", "/api/inspectors/1/inspections?limit=3", expect=200)

    print("\n-- Error handling")
    call("delete inspector that has inspections", "DELETE", f"/api/inspectors/{iid}", expect=409)
    call("invalid email", "POST", "/api/inspectors",
         {"full_name": "Bad Email", "district": "Evergreen", "email": "not-an-email"}, 422)
    call("duplicate email", "POST", "/api/inspectors",
         {"full_name": "Duplicate", "district": "Evergreen", "email": "rachandeep.kaur@sccgov-eh.org"}, 409)
    call("inspector not found", "GET", "/api/inspectors/999999", expect=404)
    call("bad inspection_code format", "POST", "/api/records",
         {"inspection_code": "12345", "facility_name": "X", "site_address": "Y", "inspector_id": 1}, 422)
    call("duplicate inspection_code", "POST", "/api/records",
         {"inspection_code": "INS-000001", "facility_name": "X", "site_address": "Y", "inspector_id": 1}, 409)
    call("unknown inspector_id", "POST", "/api/records",
         {"inspection_code": "INS-999998", "facility_name": "X", "site_address": "Y", "inspector_id": 99999}, 422)
    call("score out of range", "PUT", f"/api/records/{rid}", {"score": 150}, 422)
    call("inspection not found", "GET", "/api/records/999999", expect=404)

    print("\n-- Delete (cleanup)")
    call("delete inspection", "DELETE", f"/api/records/{rid}", expect=200)
    call("delete inspector (now unreferenced)", "DELETE", f"/api/inspectors/{iid}", expect=200)
    call("inspector gone", "GET", f"/api/inspectors/{iid}", expect=404)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "part1_api_calls.json").write_text(json.dumps(calls, indent=2, default=str))
    passed = sum(c["pass"] for c in calls)
    print(f"\n{passed}/{len(calls)} requests returned the expected status -> {RAW_DIR / 'part1_api_calls.json'}")


if __name__ == "__main__":
    main()
