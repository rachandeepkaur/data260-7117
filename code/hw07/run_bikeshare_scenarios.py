"""HW7 Part 4.IV: run the ReAct agent on both acceptance scenarios (headless).

    make bikeshare-hw07      (or: python code/hw07/run_bikeshare_scenarios.py [--scenario ppu_wins])

Uses the same run_bikeshare_agent() and evidence writer as the /bikeshare UI,
against the live pricing page. Per scenario it prints the timeline, the
decision with the cost numbers, stop reason and step count, and saves
raw/bikeshare/runs/<ts>_<scenario>_<sha8>/ (result.json, pricing snapshot text
+ HTML, snapshot_meta.json with URL / access time / SHA-256). A summary row
per scenario is appended to raw/bikeshare/scenario_runs.csv.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime

from hw07_config import BIKESHARE_CASES_DIR, BIKESHARE_RAW_DIR, PRICING_URL, WEB_APP_DIR

sys.path.insert(0, str(WEB_APP_DIR))
from bikeshare_agent import run_bikeshare_agent  # noqa: E402
from routers.bikeshare import save_run_evidence  # noqa: E402

SCENARIOS = ("membership_wins", "ppu_wins")


def print_event(e: dict) -> None:
    """One timeline line on the console (full traces go to RUN_LOG.txt via tee)."""
    if e["type"] == "tool_call":
        print(f"  +{e['t_ms'] / 1000:6.1f}s CALL {e['tool']} {json.dumps(e['input'])[:300]}", flush=True)
    elif e["type"] == "observation":
        print(f"  +{e['t_ms'] / 1000:6.1f}s OBS  {e['tool']}: {e['output'][:300]}", flush=True)
    else:
        print(f"  +{e['t_ms'] / 1000:6.1f}s {e['type'].upper()}: {e['text'][:300]}", flush=True)


def main() -> None:
    """Run the selected scenarios and record their evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=SCENARIOS, action="append")
    args = parser.parse_args()
    summary_path = BIKESHARE_RAW_DIR / "scenario_runs.csv"
    for name in args.scenario or SCENARIOS:
        csv_bytes = (BIKESHARE_CASES_DIR / f"{name}.csv").read_bytes()
        print(f"\n=== Scenario {name} ({datetime.now():%Y-%m-%d %H:%M:%S}) - pricing {PRICING_URL}", flush=True)
        result = run_bikeshare_agent(csv_bytes.decode("utf-8"), PRICING_URL, on_event=print_event)
        folder = save_run_evidence(result, csv_bytes, label=name)
        rep, ref = result["report"] or {}, result["reference"] or {}
        cb = rep.get("cost_breakdown", {})
        snap = result["snapshots"][0] if result["snapshots"] else {}
        print(f"\nDecision: {result['decision']} | reference: {ref.get('decision')} | "
              f"agrees: {result['reference_agrees']}")
        print(f"Agent costs: pay-per-use {cb.get('pay_per_use_total')} vs membership {cb.get('membership_total')} "
              f"(fees {cb.get('membership_fee_total')} + residual {cb.get('membership_residual_charges')}); "
              f"break-even {cb.get('break_even_rides_per_month')} rides/month vs actual "
              f"{cb.get('actual_rides_per_month')}")
        print(f"Reference:   pay-per-use {ref.get('pay_per_use_total')} vs membership {ref.get('membership_total')}; "
              f"break-even {ref.get('break_even_rides_per_month')} vs actual {ref.get('actual_rides_per_month')}")
        print(f"Stop reason: {result['stop_reason']} | steps (tool calls): {result['steps']} | "
              f"model turns: {result['model_turns']} | total time: {result['total_ms'] / 1000:.1f} s")
        print(f"Snapshot: {snap.get('url')} accessed {snap.get('accessed_at')} sha256 {snap.get('sha256')}")
        print(f"Evidence: {folder}")
        new = not summary_path.exists()
        with summary_path.open("a", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["ts", "scenario", "decision", "reference_decision", "agrees", "agent_ppu_total",
                            "agent_membership_total", "ref_ppu_total", "ref_membership_total", "steps",
                            "model_turns", "total_ms", "stop_reason", "tokens", "snapshot_sha256", "evidence_dir"])
            w.writerow([datetime.now().isoformat(timespec="seconds"), name, result["decision"], ref.get("decision"),
                        result["reference_agrees"], cb.get("pay_per_use_total"), cb.get("membership_total"),
                        ref.get("pay_per_use_total"), ref.get("membership_total"), result["steps"],
                        result["model_turns"], result["total_ms"], result["stop_reason"],
                        result["usage"]["total_tokens"], snap.get("sha256"), result.get("evidence_dir")])


if __name__ == "__main__":
    main()
