"""Rebuild reports/hw05/METRICS.md from the raw/ files.

    make metrics-hw05                (or: python code/hw05/compute_metrics.py)

Sections whose raw file doesn't exist yet are left as "not run yet".
"""
from __future__ import annotations

import csv
import json
from datetime import datetime

from hw05_config import LOCAL_MODEL, RAW_DIR, REPORT_DIR, SID4, VERIFY_SEED


def read_csv(name: str) -> list[dict] | None:
    path = RAW_DIR / name
    if not path.exists():
        return None
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> None:
    lines = [
        "# HW5 Metrics",
        "",
        f"SID4 = {SID4} · VERIFY_SEED = {VERIFY_SEED} · local model = {LOCAL_MODEL} · "
        f"generated {datetime.now().astimezone():%Y-%m-%d %H:%M %Z} by `make metrics-hw05` from `raw/`.",
        "",
        "## Part 3 — Fault injection (search_inspections, 50 calls per rate)",
        "",
    ]
    summary = read_csv("fault_injection_summary.csv")
    if summary:
        lines += [
            "Retry policy: 3 attempts max, 2 s timeout per attempt, backoff 0.1 s → 0.2 s (×2, cap 1 s). "
            "Raw rows: `raw/fault_injection_calls.csv`.",
            "",
            "| Injected failure rate | Success rate | Mean latency (ms) | p99 latency (ms) | Attempts | Injected failures | Reproducible |",
            "|---|---|---|---|---|---|---|",
        ]
        for s in summary:
            lines.append(
                f"| {s['failure_rate']} | {float(s['success_rate']):.0%} ({s['successes']}/{s['calls']}) | "
                f"{s['mean_latency_ms']} | {s['p99_latency_ms']} | {s['total_attempts']} | "
                f"{s['injected_failures']} | {s['reproducible']} |"
            )
    else:
        lines.append("_not run yet — `make fault-injection`_")

    lines += ["", "## Part 3 — Retry demonstration", ""]
    demo = RAW_DIR / "retry_demo.json"
    if demo.exists():
        lines += ["| Case | Attempts | Outcome per attempt | Final ok | Elapsed (ms) |", "|---|---|---|---|---|"]
        for c in json.loads(demo.read_text()):
            outcomes = " → ".join(a["outcome"] for a in c["attempt_log"])
            lines.append(f"| {c['case']} | {c['attempts']} | {outcomes} | {c['envelope']['ok']} | {c['elapsed_ms']} |")
    else:
        lines.append("_not run yet — `make retry-demo`_")

    lines += ["", f"## Part 5 — Agent scenarios ({LOCAL_MODEL} via Ollama)", ""]
    runs = read_csv("agent_scenarios.csv")
    if runs:
        lines += ["| Scenario | max_steps | Steps | Tool calls | Stop reason | run_id |", "|---|---|---|---|---|---|"]
        for r in runs:
            lines.append(f"| {r['scenario']} | {r['max_steps']} | {r['steps']} | {r['tool_calls']} | "
                         f"{r['stop_reason']} | `{r['run_id']}` |")
        lines += ["", "Full step-by-step log: `raw/agent_runs.jsonl`."]
    else:
        lines.append("_not run yet — `make agent-hw05`_")

    (REPORT_DIR / "METRICS.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
