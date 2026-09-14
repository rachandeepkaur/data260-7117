"""Adversarial case: runs one deliberately hard input through the LangGraph
Supervisor/Planner/Reviewer agent 5 times and reports how often it hits the
turn-count ceiling (MAX_TURNS) without ever being approved.

The adversarial input (reports/hw02/cases/adversarial_input.json) pairs a
fact-dense inspection summary (nine distinct violations) with a `task` field
that explicitly demands exhaustive, un-compressed detail on every violation -
directly contradicting the hard "<=25 words" / "exactly 3 tags" constraints
baked into PLANNER_SYSTEM, PlannerOutput's Pydantic validators, and
REVIEWER_SYSTEM_STRICT. See ADVERSARIAL_CASE.md for the full analysis.

This script does NOT claim or assume a fixed hit rate - it reports whatever
is actually observed across the 5 runs, honestly, even if that's below the
"ideally >=4/5" target.

Produces:
  - reports/hw02/raw/adversarial_runs.json
  - reports/hw02/raw/adversarial_runs.csv
  - Printed summary (also captured to RUN_LOG.txt via `tee -a` if desired)

Run with (from repo root, ollama serve running with qwen3:8b pulled) - each
run can take several minutes since a ceiling-hit run makes many LLM calls:

    source .venv/bin/activate
    python -u code/experiments/run_adversarial_case_experiment.py
"""
from __future__ import annotations

import csv
import json
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
INPUT_PATH = REPORT_DIR / "cases" / "adversarial_input.json"

TOTAL_RUNS = 5

CSV_FIELDS = [
    "run", "hit_ceiling", "final_approved", "final_turn_count",
    "planner_attempts", "planner_failures", "reviewer_attempts", "reviewer_rejections",
    "latency_ms", "started_at", "finished_at",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def load_fixed_input() -> tuple[InspectionSubmission, str]:
    payload = json.loads(INPUT_PATH.read_text())
    task = payload.pop("task")
    return InspectionSubmission(**payload), task


def run_one(app, client: ModelClient, submission: InspectionSubmission, task: str, run: int) -> Dict[str, Any]:
    t_start = time.time()
    initial_state = _initial_state(client, submission, strict=True, task=task)

    planner_attempts = 0
    planner_failures = 0
    reviewer_attempts = 0
    reviewer_rejections = 0
    final_update: Dict[str, Any] = {}

    print(f"[{now_iso()}] --- run {run}/{TOTAL_RUNS}: starting ---")
    for step in app.stream(initial_state):
        for node_name, update in step.items():
            if node_name == "planner":
                planner_attempts += 1
                ok = update.get("planner_proposal") is not None
                if not ok:
                    planner_failures += 1
                print(f"    turn={update.get('turn_count', final_update.get('turn_count'))} "
                      f"planner attempt #{planner_attempts}: {'schema-valid' if ok else 'FAILED VALIDATION'}")
            elif node_name == "reviewer":
                reviewer_attempts += 1
                approved = update["reviewer_feedback"]["approved"]
                if not approved:
                    reviewer_rejections += 1
                print(f"    reviewer attempt #{reviewer_attempts}: approved={approved}")
            final_update.update(update)

    latency_ms = int((time.time() - t_start) * 1000)
    final_approved = bool((final_update.get("reviewer_feedback") or {}).get("approved"))
    final_turn_count = final_update.get("turn_count")
    hit_ceiling = (not final_approved) and final_turn_count is not None and final_turn_count >= MAX_TURNS

    print(
        f"[{now_iso()}] --- run {run}/{TOTAL_RUNS} done ({latency_ms} ms): "
        f"{'HIT CEILING' if hit_ceiling else ('APPROVED' if final_approved else 'ENDED WITHOUT APPROVAL (not at ceiling)')} "
        f"(final_turn_count={final_turn_count}, planner_attempts={planner_attempts}, "
        f"planner_failures={planner_failures}, reviewer_rejections={reviewer_rejections}) ---\n"
    )

    return {
        "run": run,
        "hit_ceiling": hit_ceiling,
        "final_approved": final_approved,
        "final_turn_count": final_turn_count,
        "planner_attempts": planner_attempts,
        "planner_failures": planner_failures,
        "reviewer_attempts": reviewer_attempts,
        "reviewer_rejections": reviewer_rejections,
        "latency_ms": latency_ms,
    }


def run_all(submission: InspectionSubmission, task: str) -> List[Dict[str, Any]]:
    client = ModelClient()
    app = build_graph()
    results: List[Dict[str, Any]] = []

    for run in range(1, TOTAL_RUNS + 1):
        started_at = now_iso()
        record = run_one(app, client, submission, task, run)
        record["started_at"] = started_at
        record["finished_at"] = now_iso()
        results.append(record)

    return results


def write_raw(results: List[Dict[str, Any]]) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "adversarial_runs.json").write_text(json.dumps(results, indent=2))
    with (RAW_DIR / "adversarial_runs.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)


def main() -> None:
    submission, task = load_fixed_input()
    print(f"[{now_iso()}] Starting adversarial case study on {INPUT_PATH}, {TOTAL_RUNS} runs, MAX_TURNS={MAX_TURNS}")
    results = run_all(submission, task)
    write_raw(results)

    hits = sum(1 for r in results if r["hit_ceiling"])
    print(f"[{now_iso()}] Done. Ceiling hit in {hits}/{TOTAL_RUNS} runs. "
          f"Wrote raw/adversarial_runs.{{json,csv}} under {REPORT_DIR}")
    for r in results:
        print(f"  run {r['run']}: hit_ceiling={r['hit_ceiling']} final_approved={r['final_approved']} "
              f"final_turn_count={r['final_turn_count']} latency_ms={r['latency_ms']}")


if __name__ == "__main__":
    main()
