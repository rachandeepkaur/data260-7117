"""Part 3 Q20: seeded fault injection at 0%, 20% and 50% - 50 calls each (150 total).

    make fault-injection             (or: python code/hw05/fault_injection.py [--offline])

Each call is search_inspections through execute_tool's code path with the
interactive retry policy. A FaultInjector seeded with VERIFY_SEED (267117)
decides, per attempt, whether storage "fails"; a fresh injector is created
for each rate, so the same seed always gives the same success/failure
sequence. The script proves that by replaying each rate's decision sequence
and comparing.

Writes to reports/hw05/raw/:
    fault_injection_calls.csv / .json   one row per call (150)
    fault_injection_summary.csv         success rate, mean and p99 latency per rate
"""
from __future__ import annotations

import argparse
import csv
import json
import math

from hw05_config import CALLS_PER_RATE, FAILURE_RATES, RAW_DIR, VERIFY_SEED

from domain_tools.executor import run_tool
from domain_tools.fixtures import make_fixture_repo
from domain_tools.repository import FaultyRepository, SqlRepository
from domain_tools.resilience import INTERACTIVE_POLICY, FaultInjector

QUERIES = ["golden", "kitchen", "taqueria", "pho", "story rd", "bakery", "grill", "95122", "sushi", "cafe"]


def percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile (same as numpy's default)."""
    xs = sorted(values)
    k = (len(xs) - 1) * pct / 100
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def run_rate(base, rate: float) -> tuple[list[dict], list[bool]]:
    injector = FaultInjector(rate, VERIFY_SEED)
    repo = FaultyRepository(base, injector)
    rows = []
    for i in range(CALLS_PER_RATE):
        before = len(injector.decisions)
        envelope, trace = run_tool("search_inspections", {"query": QUERIES[i % len(QUERIES)], "limit": 10},
                                   repo=repo)
        decisions = injector.decisions[before:]
        rows.append({
            "failure_rate": rate,
            "call_index": i + 1,
            "seed": VERIFY_SEED,
            "query": QUERIES[i % len(QUERIES)],
            "attempts": trace.attempts,
            "injected_failures": sum(decisions),
            "attempt_outcomes": "".join("F" if d else "S" for d in decisions),
            "ok": envelope["ok"],
            "latency_ms": trace.elapsed_ms,
            "result_count": envelope["data"]["count"] if envelope["ok"] else None,
            "error": envelope["error"],
        })
    return rows, injector.decisions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="use the in-memory fixture instead of MySQL")
    args = parser.parse_args()
    base = make_fixture_repo() if args.offline else SqlRepository()
    p = INTERACTIVE_POLICY

    print(f"VERIFY_SEED={VERIFY_SEED}  calls/rate={CALLS_PER_RATE}  backend="
          f"{'in-memory fixture' if args.offline else 'MySQL s7117_rel'}")
    print(f"policy: max_attempts={p.max_attempts} timeout={p.timeout_s}s backoff={p.base_delay_s}s x{p.multiplier:g}"
          f" cap {p.max_delay_s}s\n")

    all_rows, summary = [], []
    for rate in FAILURE_RATES:
        rows, decisions = run_rate(base, rate)
        # Reproducibility: a fresh injector with the same seed must replay the same sequence.
        replay = FaultInjector(rate, VERIFY_SEED)
        replayed = []
        for _ in decisions:
            try:
                replay.maybe_fail()
                replayed.append(False)
            except Exception:  # noqa: BLE001
                replayed.append(True)
        latencies = [r["latency_ms"] for r in rows]
        s = {
            "failure_rate": f"{rate:.0%}",
            "calls": len(rows),
            "successes": sum(r["ok"] for r in rows),
            "success_rate": round(sum(r["ok"] for r in rows) / len(rows), 4),
            "mean_latency_ms": round(sum(latencies) / len(latencies), 2),
            "p99_latency_ms": round(percentile(latencies, 99), 2),
            "total_attempts": sum(r["attempts"] for r in rows),
            "injected_failures": sum(decisions),
            "reproducible": replayed == decisions,
        }
        summary.append(s)
        all_rows.extend(rows)
        print(f"rate {s['failure_rate']:>4}: success {s['successes']}/{s['calls']} ({s['success_rate']:.0%}), "
              f"mean {s['mean_latency_ms']} ms, p99 {s['p99_latency_ms']} ms, attempts {s['total_attempts']}, "
              f"injected failures {s['injected_failures']}, reproducible={s['reproducible']}")
        print("          per-call outcomes: " + " ".join(r["attempt_outcomes"] for r in rows))

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with (RAW_DIR / "fault_injection_calls.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(all_rows[0]))
        w.writeheader()
        w.writerows(all_rows)
    (RAW_DIR / "fault_injection_calls.json").write_text(json.dumps(all_rows, indent=2))
    with (RAW_DIR / "fault_injection_summary.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)
    print(f"\nwrote {len(all_rows)} call records to {RAW_DIR}/fault_injection_calls.csv/.json "
          f"and fault_injection_summary.csv")


if __name__ == "__main__":
    main()
