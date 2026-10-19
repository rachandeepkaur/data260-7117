"""HW6 Part 1: exercise every /api/doc/inspections endpoint and the
validation/error cases against the running API (make run-api).

    make doc-api-demo-hw06   -> reports/hw06/raw/part1_doc_api_calls.json

Successful CRUD: create -> get one -> list -> update -> delete -> get (404).
Validation: missing required fields, invalid enums, wrong types, bad date,
too-long title, unknown field, empty update, malformed JSON, wrong content
type, malformed ObjectId. One extra document is left in the collection so
MongoDB Compass / mongosh shows data created through the API.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime

import requests

from hw06_config import BASE_URL, RAW_DIR

URL = f"{BASE_URL}/api/doc/inspections"
calls: list[dict] = []


def call(label: str, method: str, url: str, expect: int, **kwargs) -> requests.Response:
    r = requests.request(method, url, timeout=15, **kwargs)
    try:
        body = r.json()
    except ValueError:
        body = r.text
    sent = kwargs.get("json", kwargs.get("data"))
    calls.append({"label": label, "request": {"method": method, "url": url, "body": sent},
                  "status": r.status_code, "expected": expect, "ok": r.status_code == expect, "response": body})
    mark = "PASS" if r.status_code == expect else "FAIL"
    print(f"[{mark}] {label:<44} {method:<6} {url.replace(BASE_URL, '')} -> {r.status_code} (expected {expect})")
    print("       " + json.dumps(body)[:400])
    return r


def main() -> None:
    user = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip()
    print(f"HW6 Part 1 - MongoDB document API demo - user: {user} - {datetime.now():%Y-%m-%d %H:%M:%S}\n")
    good = {"facility_name": "FA0148210 - GOLDEN DRAGON", "description": "Walk-in cooler at 47F; cold holding failed.",
            "status": "failed", "program_element": "ROUTINE HEALTH INSPECTION",
            "inspection_date": "2026-10-16T10:30:00-07:00"}

    print("--- CRUD ---")
    created = call("create (POST)", "POST", URL, 201, json=good).json()
    doc_id = created["id"]
    call("retrieve one (GET /:id)", "GET", f"{URL}/{doc_id}", 200)
    r = call("retrieve all (GET)", "GET", f"{URL}?limit=5", 200)
    print(f"       X-Total-Count: {r.headers.get('X-Total-Count')}")
    call("filter by status (GET ?status=failed)", "GET", f"{URL}?status=failed&limit=3", 200)
    call("update (PUT /:id)", "PUT", f"{URL}/{doc_id}", 200,
         json={"status": "follow_up_required", "description": "Follow-up moved to 2026-11-10."})
    call("delete (DELETE /:id)", "DELETE", f"{URL}/{doc_id}", 200)
    call("get deleted -> not found", "GET", f"{URL}/{doc_id}", 404)
    call("update missing -> not found", "PUT", f"{URL}/{doc_id}", 404, json={"status": "passed"})
    call("delete missing -> not found", "DELETE", f"{URL}/{doc_id}", 404)

    print("\n--- validation ---")
    call("missing required fields", "POST", URL, 422, json={"description": "no title, no category, no date"})
    call("invalid enum values", "POST", URL, 422, json={**good, "status": "closed", "program_element": "BAKERY"})
    call("incorrect data types", "POST", URL, 422, json={**good, "facility_name": 12345, "inspection_date": True})
    call("bad date format", "POST", URL, 422, json={**good, "inspection_date": "16/10/2026"})
    call("facility_name over 100 chars", "POST", URL, 422, json={**good, "facility_name": "X" * 101})
    call("blank facility_name", "POST", URL, 422, json={**good, "facility_name": "   "})
    call("unknown field (client-set created_at)", "POST", URL, 422, json={**good, "created_at": "2020-01-01"})
    call("empty update body", "PUT", f"{URL}/{'0' * 24}", 422, json={})
    call("malformed JSON", "POST", URL, 400, data="{bad json", headers={"Content-Type": "application/json"})
    call("wrong content type", "POST", URL, 415, data="facility_name=x", headers={"Content-Type": "text/plain"})
    call("malformed ObjectId", "GET", f"{URL}/not-an-id", 400)

    keep = call("create sample doc kept for Compass", "POST", URL, 201, json={
        **good, "facility_name": "FA0206933 - YUMMY KITCHEN", "status": "scheduled",
        "program_element": "FOLLOW-UP COMPLIANCE CHECK", "description": "Created by part1_doc_api_demo.py",
        "inspection_date": "2026-10-22T09:00:00-07:00"}).json()
    print(f"       kept document id {keep['id']}")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "part1_doc_api_calls.json").write_text(json.dumps(calls, indent=2))
    passed = sum(c["ok"] for c in calls)
    print(f"\n{passed}/{len(calls)} calls returned the expected status -> {RAW_DIR / 'part1_doc_api_calls.json'}")


if __name__ == "__main__":
    main()
