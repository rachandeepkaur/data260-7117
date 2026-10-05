"""Part 5.IV: run the agent on the local Ollama model over five scenarios.

    make agent-hw05                  (or: python code/hw05/run_agent_scenarios.py)

Needs `ollama serve` with qwen3:8b pulled, and MySQL s7117_rel migrated.
Every step is appended to reports/hw05/raw/agent_runs.jsonl; the per-scenario
summary (steps, stop reason, tool calls) goes to raw/agent_scenarios.csv.
"""
from __future__ import annotations

import argparse
import csv
import json

from hw05_config import AGENT_LOG, LOCAL_MODEL, RAW_DIR

from domain_tools import execute_tool
from domain_tools.agent import DEFAULT_MAX_STEPS, OllamaModel, run_agent
from domain_tools.repository import SqlRepository


def scenarios(repo) -> list[tuple[str, str, int]]:
    # A facility id that occurs in exactly one inspection -> its aggregate trips the safety rule.
    rec = json.loads(execute_tool("get_inspection", {"inspection_code": "INS-000001"}, repo=repo))
    facility_id = rec["data"]["facility_name"].split(" - ")[0] if rec["ok"] else "FA0206933"
    return [
        ("search", "Find up to 5 inspections of facilities with GOLDEN in the name that scored at least 90. "
                   "List their inspection codes and scores.", DEFAULT_MAX_STEPS),
        ("detail", "What violations were found in inspection INS-000042, what was the score, "
                   "and which inspector did it?", DEFAULT_MAX_STEPS),
        ("aggregate", "What are the average inspection score and the pass rate for inspector 3?",
         DEFAULT_MAX_STEPS),
        ("safety", f"Use inspection_stats to give me the average score for facility {facility_id}.",
         DEFAULT_MAX_STEPS),
        ("max_steps", "Compare the average inspection score of inspectors 1, 2, 3, 4 and 5 (one "
                      "inspection_stats call each) and tell me which inspector has the highest.", 3),
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=LOCAL_MODEL)
    args = parser.parse_args()

    repo = SqlRepository()
    model = OllamaModel(args.model)
    rows = []
    for name, prompt, max_steps in scenarios(repo):
        print(f"== scenario {name} (max_steps={max_steps})\n   user: {prompt}")
        result = run_agent(prompt, model=model, max_steps=max_steps, repo=repo, log_path=AGENT_LOG, scenario=name)
        for e in result["events"]:
            if e["event"] == "step" and e.get("action") == "tool":
                r = e["result"]
                status = "ok" if r["ok"] else f"error: {r['error'][:120]}"
                print(f"   step {e['step']}: {e['tool']}({json.dumps(e['inputs'])}) -> {status}")
            elif e["event"] == "step":
                print(f"   step {e['step']}: {e.get('action') or 'error'}")
        print(f"   stop_reason={result['stop_reason']} steps={result['steps']} tool_calls={result['tool_calls']}")
        print(f"   final: {(result['final_answer'] or '')[:300]}\n")
        rows.append({k: result[k] for k in ("run_id", "scenario", "model", "max_steps", "steps",
                                            "tool_calls", "stop_reason", "user_input", "final_answer")})

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with (RAW_DIR / "agent_scenarios.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"appended steps to {AGENT_LOG}; summary in {RAW_DIR / 'agent_scenarios.csv'}")


if __name__ == "__main__":
    main()
