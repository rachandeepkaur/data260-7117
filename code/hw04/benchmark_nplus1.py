"""N+1 measurement: naive vs. fixed list endpoint at page sizes 10/50/200 (HW4 Part 3.4-3.7).

    python code/hw04/benchmark_nplus1.py                 # the 180 reported requests
    python code/hw04/benchmark_nplus1.py --tag with_index  # optional re-run after add_index.sql

Requires the API running on PORT_BASE (8817). Logs in as the demo user, sends
WARMUP unmeasured requests per (page size, version), then 30 measured
requests each. Naive and fixed requests are interleaved so any drift in
machine load affects both versions equally.

Per request it records: SQL statement count (X-SQL-Query-Count), client
round-trip latency (perf_counter around the HTTP call), server handler time
(X-Server-Time-Ms), records/violations returned, and a hash of the items so
the two versions can be checked to return identical data.

Writes raw/nplus1_requests[_<tag>].csv/.json and raw/nplus1_summary[_<tag>].csv.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from datetime import datetime, timezone

import numpy as np
import requests

from hw04_config import BASE_URL, DEMO_USER_EMAIL, DEMO_USER_PASSWORD, RAW_DIR, SEED

PAGE_SIZES = [10, 50, 200]
VERSIONS = ["naive", "fixed"]
N_REQUESTS = 30
WARMUP = 3


def login() -> requests.Session:
    session = requests.Session()
    resp = session.post(f"{BASE_URL}/api/auth/login",
                        json={"email": DEMO_USER_EMAIL, "password": DEMO_USER_PASSWORD}, timeout=10)
    resp.raise_for_status()
    return session


def one_request(session: requests.Session, version: str, page_size: int) -> tuple[dict, float]:
    url = f"{BASE_URL}/api/nplus1/{version}"
    start = time.perf_counter()
    resp = session.get(url, params={"page_size": page_size, "offset": 0}, timeout=30)
    elapsed_ms = (time.perf_counter() - start) * 1000
    resp.raise_for_status()
    return resp, elapsed_ms


def percentile(values: list[float], q: float) -> float:
    return float(np.percentile(values, q, method="linear"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="", help="suffix for output files (e.g. with_index)")
    args = parser.parse_args()
    suffix = f"_{args.tag}" if args.tag else ""

    session = login()
    print(f"[{datetime.now(timezone.utc).isoformat()}] logged in as {DEMO_USER_EMAIL}; base={BASE_URL}; seed={SEED}")

    rows: list[dict] = []
    for page_size in PAGE_SIZES:
        for _ in range(WARMUP):
            for version in VERSIONS:
                one_request(session, version, page_size)
        for i in range(1, N_REQUESTS + 1):
            for version in VERSIONS:
                resp, elapsed_ms = one_request(session, version, page_size)
                body = resp.json()
                rows.append({
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "page_size": page_size,
                    "version": version,
                    "request_index": i,
                    "status": resp.status_code,
                    "sql_queries": int(resp.headers["X-SQL-Query-Count"]),
                    "client_latency_ms": round(elapsed_ms, 3),
                    "server_time_ms": float(resp.headers["X-Server-Time-Ms"]),
                    "records_returned": body["record_count"],
                    "violations_returned": body["violation_count"],
                    "items_sha256": hashlib.sha256(
                        json.dumps(body["items"], sort_keys=True).encode()
                    ).hexdigest()[:16],
                })
        print(f"[{datetime.now(timezone.utc).isoformat()}] page_size={page_size}: "
              f"{N_REQUESTS} naive + {N_REQUESTS} fixed requests done")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    requests_csv = RAW_DIR / f"nplus1_requests{suffix}.csv"
    with requests_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (RAW_DIR / f"nplus1_requests{suffix}.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    summary = []
    for page_size in PAGE_SIZES:
        per_version = {}
        for version in VERSIONS:
            subset = [r for r in rows if r["page_size"] == page_size and r["version"] == version]
            lat = [r["client_latency_ms"] for r in subset]
            srv = [r["server_time_ms"] for r in subset]
            per_version[version] = {
                "page_size": page_size,
                "version": version,
                "n_requests": len(subset),
                "sql_stmts_per_req": sorted({r["sql_queries"] for r in subset}),
                "p50_ms": round(percentile(lat, 50), 2),
                "p95_ms": round(percentile(lat, 95), 2),
                "p99_ms": round(percentile(lat, 99), 2),
                "mean_ms": round(float(np.mean(lat)), 2),
                "server_p50_ms": round(percentile(srv, 50), 2),
                "records_returned": subset[0]["records_returned"],
                "violations_returned": subset[0]["violations_returned"],
                "items_sha256": sorted({r["items_sha256"] for r in subset}),
            }
        speedup = per_version["naive"]["p50_ms"] / per_version["fixed"]["p50_ms"]
        same_data = per_version["naive"]["items_sha256"] == per_version["fixed"]["items_sha256"]
        for version in VERSIONS:
            per_version[version]["p50_speedup_fixed_vs_naive"] = round(speedup, 2)
            per_version[version]["same_data_both_versions"] = same_data
            summary.append(per_version[version])

    summary_csv = RAW_DIR / f"nplus1_summary{suffix}.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(summary[0].keys()))
        writer.writeheader()
        for row in summary:
            writer.writerow({k: (";".join(map(str, v)) if isinstance(v, list) else v) for k, v in row.items()})

    print()
    print(f"{'page':>5} {'version':<6} {'sql/req':>8} {'p50':>9} {'p95':>9} {'p99':>9} {'srv p50':>9} {'speedup':>8} same_data")
    for row in summary:
        print(f"{row['page_size']:>5} {row['version']:<6} {'/'.join(map(str, row['sql_stmts_per_req'])):>8} "
              f"{row['p50_ms']:>9.2f} {row['p95_ms']:>9.2f} {row['p99_ms']:>9.2f} {row['server_p50_ms']:>9.2f} "
              f"{row['p50_speedup_fixed_vs_naive']:>7.2f}x {row['same_data_both_versions']}")
    print(f"\nWrote {len(rows)} measured requests to {requests_csv.relative_to(RAW_DIR.parent.parent.parent)}")


if __name__ == "__main__":
    main()
