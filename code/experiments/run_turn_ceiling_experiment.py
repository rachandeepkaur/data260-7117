"""Turn-ceiling comparison: runs the LangGraph Supervisor/Planner/Reviewer
agent on the same frozen input (reports/hw02/cases/schema_input.json) and
model settings 20 times at MAX_TURNS=2 and 20 times at MAX_TURNS=10, and
reports completion rate + mean latency for each ceiling.

"Completion" here means the Reviewer genuinely approved (graph reached END
via approval) before the ceiling was hit - not merely that the graph
terminated (it always terminates, either by approval or by MAX_TURNS).

MAX_TURNS is monkeypatched on the langgraph_agent module for the duration
of each block rather than edited in the file: router_logic reads the
module-level MAX_TURNS global at call time (not at graph-build time), so
setting langgraph_agent.MAX_TURNS before compiling/running the graph is
sufficient and needs no permanent code change.

Produces:
  - reports/hw02/raw/turn_ceiling_runs.json
  - reports/hw02/raw/turn_ceiling_runs.csv
  - reports/hw02/TURN_CEILING.md   (comparison table + a data-justified pick)

Run with (from repo root, ollama serve running with qwen3:8b pulled). -u
disables Python's stdout buffering so `tee` shows progress live instead of
dumping it all at once when the process exits:

    source .venv/bin/activate
    python -u code/experiments/run_turn_ceiling_experiment.py 2>&1 | tee -a reports/hw02/RUN_LOG.txt
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
import langgraph_agent as lg  # noqa: E402
from model_client import ModelClient  # noqa: E402

REPORT_DIR = REPO_ROOT / "reports" / "hw02"
RAW_DIR = REPORT_DIR / "raw"
INPUT_PATH = REPORT_DIR / "cases" / "schema_input.json"

CEILINGS = [2, 10]
RUNS_PER_CEILING = 20

CSV_FIELDS = [
    "ceiling", "run", "completed", "final_approved", "final_turn_count",
    "latency_ms", "started_at", "finished_at",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def load_fixed_input() -> InspectionSubmission:
    return InspectionSubmission(**json.loads(INPUT_PATH.read_text()))


def run_one(app, client: ModelClient, submission: InspectionSubmission, ceiling: int, run: int) -> Dict[str, Any]:
    t_start = time.time()
    initial_state = lg._initial_state(
        client, submission, strict=True,
        task="Summarize the inspection findings and extract 3 topical tags.",
    )
    final_state = app.invoke(initial_state)
    latency_ms = int((time.time() - t_start) * 1000)

    final_approved = bool((final_state.get("reviewer_feedback") or {}).get("approved"))
    completed = final_approved  # genuinely approved before the ceiling, not just "graph ended"

    print(
        f"[{now_iso()}] ceiling={ceiling} run {run}/{RUNS_PER_CEILING} ({latency_ms} ms): "
        f"{'COMPLETED' if completed else 'HIT CEILING'} "
        f"(final_turn_count={final_state.get('turn_count')}, approved={final_approved})"
    )

    return {
        "ceiling": ceiling,
        "run": run,
        "completed": completed,
        "final_approved": final_approved,
        "final_turn_count": final_state.get("turn_count"),
        "latency_ms": latency_ms,
    }


def run_all(submission: InspectionSubmission) -> List[Dict[str, Any]]:
    client = ModelClient()
    results: List[Dict[str, Any]] = []

    original_max_turns = lg.MAX_TURNS
    try:
        for ceiling in CEILINGS:
            lg.MAX_TURNS = ceiling
            app = lg.build_graph()
            print(f"[{now_iso()}] === MAX_TURNS={ceiling}: {RUNS_PER_CEILING} runs ===")

            for run in range(1, RUNS_PER_CEILING + 1):
                started_at = now_iso()
                record = run_one(app, client, submission, ceiling, run)
                record["started_at"] = started_at
                record["finished_at"] = now_iso()
                results.append(record)
    finally:
        lg.MAX_TURNS = original_max_turns  # restore, since this module stays imported

    return results


def write_raw(results: List[Dict[str, Any]]) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "turn_ceiling_runs.json").write_text(json.dumps(results, indent=2))
    with (RAW_DIR / "turn_ceiling_runs.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)


def summarize(results: List[Dict[str, Any]], ceiling: int) -> Dict[str, Any]:
    runs = [r for r in results if r["ceiling"] == ceiling]
    completed = [r for r in runs if r["completed"]]
    return {
        "ceiling": ceiling,
        "n": len(runs),
        "completed": len(completed),
        "completion_rate": round(100 * len(completed) / len(runs), 1) if runs else 0.0,
        "mean_latency_ms": round(statistics.mean(r["latency_ms"] for r in runs), 1) if runs else 0.0,
        "mean_latency_completed_ms": round(statistics.mean(r["latency_ms"] for r in completed), 1) if completed else None,
    }


def write_report(results: List[Dict[str, Any]]) -> None:
    summaries = {c: summarize(results, c) for c in CEILINGS}

    lines: List[str] = []
    lines.append("# HW02 Turn-Ceiling Comparison")
    lines.append("")
    lines.append(
        f'Fixed input (`reports/hw02/cases/schema_input.json`, facility: "FA0206933 - YUMMY KITCHEN"), '
        f"same model settings, run through the real Supervisor/Planner/Reviewer LangGraph agent "
        f"(`qwen3:8b` via Ollama) {RUNS_PER_CEILING} times at each of MAX_TURNS={CEILINGS[0]} and "
        f"MAX_TURNS={CEILINGS[1]} ({RUNS_PER_CEILING * len(CEILINGS)} runs total). "
        f'"Completed" means the Reviewer genuinely approved before the ceiling was reached. '
        f"Source data: [raw/turn_ceiling_runs.json](raw/turn_ceiling_runs.json), "
        f"[raw/turn_ceiling_runs.csv](raw/turn_ceiling_runs.csv)."
    )
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append("| MAX_TURNS | Runs | Completed | Completion rate | Mean latency (all runs) | Mean latency (completed only) |")
    lines.append("|---|---|---|---|---|---|")
    for ceiling in CEILINGS:
        s = summaries[ceiling]
        completed_latency = s["mean_latency_completed_ms"] if s["mean_latency_completed_ms"] is not None else "-"
        lines.append(
            f"| {ceiling} | {s['n']} | {s['completed']}/{s['n']} | {s['completion_rate']}% | "
            f"{s['mean_latency_ms']} ms | {completed_latency} ms |"
        )
    lines.append("")
    lines.append("## Recommendation")
    lines.append("")
    lines.append("*(fill in after the run: pick MAX_TURNS=2 or MAX_TURNS=10 for \"deployment\" and justify "
                  "with the completion-rate and latency numbers above - e.g. does the higher ceiling actually "
                  "buy a meaningfully higher completion rate, or does this input converge so reliably on the "
                  "first pass that the extra ceiling heaadroom never gets used and only risks longer worst-case "
                  "latency on a run that would otherwise fail fast?)*")
    lines.append("")

    (REPORT_DIR / "TURN_CEILING.md").write_text("\n".join(lines))


def main() -> None:
    submission = load_fixed_input()
    print(f"[{now_iso()}] Starting turn-ceiling comparison on fixed input "
          f"(facility: {submission.facility_name!r}), ceilings={CEILINGS}, {RUNS_PER_CEILING} runs each")
    results = run_all(submission)
    write_raw(results)
    write_report(results)
    print(f"[{now_iso()}] Done. Wrote raw/turn_ceiling_runs.{{json,csv}} and TURN_CEILING.md under {REPORT_DIR}")


if __name__ == "__main__":
    main()
