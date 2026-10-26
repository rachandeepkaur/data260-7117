"""HW7 Part 2.I + 2.II: the hand-written agent on tasks A, B, C and the error-recovery case.

    make agent-demo-hw07     (or: python code/hw07/run_agent_demo.py [--seed N] [--offline])

Each task is ONE user message - no follow-up prompting. Every tool invocation
is logged (name + inputs + outcome) and the total tool-call count is printed
at the end of each run. Task E asks for INS-999999, which does not exist:
execute_tool returns a useful "not found" error and the agent must answer
without crashing. Results go to raw/agent_demo_runs.jsonl.

--offline uses the fixture repository and scripted replies (no MySQL/Ollama).
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime

# hw07_config puts code/ on sys.path, so it must be imported before the project packages.
from hw07_config import AGENT_TEMPERATURE, LOCAL_MODEL, RAW_DIR, SEED

# isort: split
from agent_loop import OllamaChatModel, ScriptedModel, make_domain_toolset, run_agent  # noqa: E402
from agent_loop.tasks import chain_complete, load_error_recovery_prompt, load_tasks, verify  # noqa: E402

OFFLINE_SCRIPT = {
    "A": [{"tool_calls": [{"name": "search_inspections", "arguments": {"query": "jade"}}]},
          {"tool_calls": [{"name": "get_inspection", "arguments": {"inspection_code": "INS-000006"}}]},
          "INS-000006 (FA0623311 - JADE NOODLE HOUSE) scored 96; inspector Maria Nguyen; no violations."],
    "E": [{"tool_calls": [{"name": "get_inspection", "arguments": {"inspection_code": "INS-999999"}}]},
          "Inspection INS-999999 was not found in the database, so there are no details to show."],
}


def main() -> None:
    """Run A, B, C and E once each and save the traces."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    repo = None
    if args.offline:
        from domain_tools.fixtures import make_fixture_repo

        repo = make_fixture_repo()
    toolset = make_domain_toolset(repo)
    cases = [(t.id, t.prompt, t) for t in load_tasks()] + [("E", load_error_recovery_prompt(), None)]
    if args.offline:
        cases = [c for c in cases if c[0] in OFFLINE_SCRIPT]
    out = RAW_DIR / "agent_demo_runs.jsonl"
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"HW7 Part 2 agent demo - model {LOCAL_MODEL} temperature={AGENT_TEMPERATURE} seed={args.seed} - "
          f"{datetime.now():%Y-%m-%d %H:%M:%S}")
    for task_id, prompt, task in cases:
        print(f"\n=== Task {task_id}: {prompt}")
        model = ScriptedModel(OFFLINE_SCRIPT[task_id]) if args.offline else \
            OllamaChatModel(temperature=AGENT_TEMPERATURE, seed=args.seed)
        result = run_agent(prompt, model=model, toolset=toolset)
        print(f"--- final answer ({result['stop_reason']}):\n{result['final_answer']}")
        record = {"ts": datetime.now().isoformat(timespec="seconds"), "task_id": task_id, "seed": args.seed,
                  **{k: v for k, v in result.items() if k != "messages"}}
        if task is not None:
            verdict = verify(task, result)
            record.update(verifier=verdict.to_dict(), chain_complete=chain_complete(task, result))
            print(f"--- verifier: {'PASS' if verdict.passed else 'FAIL'} | chain complete: {record['chain_complete']} "
                  f"| tool calls: {result['tool_calls']}")
        else:
            errors = [c["error"] for c in result["trace"] if not c["ok"]]
            record.update(execute_tool_errors=errors, crashed=False)
            print(f"--- execute_tool returned: {errors} | agent stop_reason: {result['stop_reason']} (no crash)")
        with out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
