"""Frozen-input run (30x): runs the LangGraph Supervisor/Planner/Reviewer
agent on one fixed domain input 30 times and classifies each run by how many
times the Planner's raw output failed Pydantic schema validation (exactly 3
tags, 3-30 chars each, <=25-word summary) before it finally produced valid
JSON - or whether it never did before the graph's turn-count safety cap.

Each classification bucket, in terms of planner_node invocations before the
first schema-valid planner_proposal:
  - valid_first_attempt:    0 failed invocations before success
  - valid_after_1_retry:    exactly 1 failed invocation before success
  - valid_after_2plus_retries: 2+ failed invocations before success
  - abandoned_at_ceiling:   never produced valid JSON before the graph ended

This is a *different* thing than the Reviewer approving/rejecting the
content - it isolates the schema-validation retry path added to
planner_node (see langgraph_agent.py's `except ModelClientError` block).

Fixed input: reports/hw02/cases/schema_input.json (InspectionSubmission
fields, saved once and read unchanged here).

Produces:
  - reports/hw02/RUN_LOG.txt        (via `tee` on this script's stdout)
  - reports/hw02/raw/schema_validation_runs.json
  - reports/hw02/raw/schema_validation_runs.csv
  - reports/hw02/METRICS.md         (overwritten with this study's table)

Run with (from repo root, ollama serve running with qwen3:8b pulled):

    source .venv/bin/activate
    python code/experiments/run_schema_validation_experiment.py 2>&1 | tee reports/hw02/RUN_LOG.txt
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "code"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from agents_demo import InspectionSubmission  # noqa: E402
from langgraph_agent import MAX_TURNS, _initial_state, build_graph  # noqa: E402
from model_client import ModelClient  # noqa: E402

REPORT_DIR = REPO_ROOT / "reports" / "hw02"
RAW_DIR = REPORT_DIR / "raw"
INPUT_PATH = REPORT_DIR / "cases" / "schema_input.json"

TOTAL_RUNS = 30
BUCKETS = ["valid_first_attempt", "valid_after_1_retry", "valid_after_2plus_retries", "abandoned_at_ceiling"]

CSV_FIELDS = [
    "run", "classification", "planner_attempts", "planner_failures_before_success",
    "final_approved", "final_turn_count", "latency_ms", "started_at", "finished_at",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def load_fixed_input() -> InspectionSubmission:
    return InspectionSubmission(**json.loads(INPUT_PATH.read_text()))


def classify(planner_failures_before_success: int, succeeded: bool) -> str:
    if not succeeded:
        return "abandoned_at_ceiling"
    if planner_failures_before_success == 0:
        return "valid_first_attempt"
    if planner_failures_before_success == 1:
        return "valid_after_1_retry"
    return "valid_after_2plus_retries"


def run_one(app, client: ModelClient, submission: InspectionSubmission, run: int) -> Dict[str, Any]:
    t_start = time.time()
    initial_state = _initial_state(client, submission, strict=True, task="Summarize the inspection findings and extract 3 topical tags.")

    planner_attempts = 0
    planner_failures_before_success = 0
    succeeded = False
    final_update: Dict[str, Any] = {}

    for step in app.stream(initial_state):
        for node_name, update in step.items():
            if node_name == "planner":
                planner_attempts += 1
                if update.get("planner_proposal") is not None:
                    succeeded = True
                elif not succeeded:
                    planner_failures_before_success += 1
            final_update.update(update)

    latency_ms = int((time.time() - t_start) * 1000)
    classification = classify(planner_failures_before_success, succeeded)
    final_approved = bool((final_update.get("reviewer_feedback") or {}).get("approved"))

    print(
        f"[{now_iso()}] run {run}/{TOTAL_RUNS} ({latency_ms} ms): "
        f"{classification} (planner_attempts={planner_attempts}, "
        f"failures_before_success={planner_failures_before_success}, "
        f"final_turn_count={final_update.get('turn_count')}, approved={final_approved})"
    )

    return {
        "run": run,
        "classification": classification,
        "planner_attempts": planner_attempts,
        "planner_failures_before_success": planner_failures_before_success,
        "final_approved": final_approved,
        "final_turn_count": final_update.get("turn_count"),
        "latency_ms": latency_ms,
    }


def run_all(submission: InspectionSubmission) -> List[Dict[str, Any]]:
    client = ModelClient()
    app = build_graph()
    results: List[Dict[str, Any]] = []

    for run in range(1, TOTAL_RUNS + 1):
        started_at = now_iso()
        record = run_one(app, client, submission, run)
        record["started_at"] = started_at
        record["finished_at"] = now_iso()
        results.append(record)

    return results


def write_raw(results: List[Dict[str, Any]]) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "schema_validation_runs.json").write_text(json.dumps(results, indent=2))
    with (RAW_DIR / "schema_validation_runs.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)


def write_metrics(results: List[Dict[str, Any]]) -> None:
    lines: List[str] = []
    lines.append("# HW02 Metrics — Planner Schema-Validation Retry Study")
    lines.append("")
    lines.append(
        f'Fixed input (`reports/hw02/cases/schema_input.json`, facility: "FA0206933 - YUMMY KITCHEN"), '
        f"run through the real Supervisor/Planner/Reviewer LangGraph agent (`code/langgraph_agent.py`, "
        f"`qwen3:8b` via Ollama) {TOTAL_RUNS} times. Each run classified by how many times the Planner's "
        f"raw output failed `PlannerOutput` Pydantic validation (exactly 3 tags, 3-30 chars each, "
        f"<=25-word summary) before it produced schema-valid JSON, bounded by `MAX_TURNS={MAX_TURNS}`. "
        f"Source data: [raw/schema_validation_runs.json](raw/schema_validation_runs.json), "
        f"[raw/schema_validation_runs.csv](raw/schema_validation_runs.csv). Full console transcript: "
        f"[RUN_LOG.txt](RUN_LOG.txt)."
    )
    lines.append("")
    lines.append("## Outcome table")
    lines.append("")
    lines.append("| Bucket | Count | Mean latency (ms) |")
    lines.append("|---|---|---|")

    for bucket in BUCKETS:
        bucket_runs = [r for r in results if r["classification"] == bucket]
        count = len(bucket_runs)
        mean_latency = round(statistics.mean(r["latency_ms"] for r in bucket_runs), 1) if bucket_runs else "-"
        label = bucket.replace("_", " ")
        lines.append(f"| {label} | {count} | {mean_latency} |")

    lines.append("")
    lines.append(f"- Total runs: {TOTAL_RUNS}")
    lines.append(f"- Runs where the Planner's first attempt was already schema-valid: "
                  f"{sum(1 for r in results if r['classification'] == 'valid_first_attempt')}/{TOTAL_RUNS}")
    lines.append(f"- Runs abandoned at the turn ceiling (Planner never produced valid JSON): "
                  f"{sum(1 for r in results if r['classification'] == 'abandoned_at_ceiling')}/{TOTAL_RUNS}")
    lines.append("")

    (REPORT_DIR / "METRICS.md").write_text("\n".join(lines))


def main() -> None:
    submission = load_fixed_input()
    print(f"[{now_iso()}] Starting schema-validation retry study on fixed input "
          f"(facility: {submission.facility_name!r}), {TOTAL_RUNS} runs")
    results = run_all(submission)
    write_raw(results)
    write_metrics(results)
    print(f"[{now_iso()}] Done. Wrote raw/schema_validation_runs.{{json,csv}} and METRICS.md under {REPORT_DIR}")


if __name__ == "__main__":
    main()
