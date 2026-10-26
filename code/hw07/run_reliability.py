"""HW7 Part 2.III: tool-call reliability over the three fixed cases.

    make reliability-hw07    (or: python code/hw07/run_reliability.py [--attempts-per-task 7])

21 attempts (3 fixed tasks x 7) with the SAME model settings (qwen3:8b,
temperature AGENT_TEMPERATURE, reasoning off, same prompt and tools); only the
sampling seed changes per attempt (VERIFY_SEED + i) so the attempts are
independent yet reproducible.

Per attempt it records the turn-level well-formedness counters from run_agent
and classifies failures:
    malformed_arguments    arguments not a JSON object / failed the tool schema
    unknown_tool           tool name not in the toolset
    text_instead_of_tool   plain text before any tool call
    lost_chain             the run ended without every required tool succeeding
Rates (pooled over all attempts):
    well-formed before repair = first-try OK turns / first-try turns
    well-formed after repair  = (first-try OK + repaired OK) / first-try turns
Writes raw/toolcall_reliability.csv (one row per attempt) and
raw/toolcall_reliability.jsonl (full traces).
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime

# hw07_config puts code/ on sys.path, so it must be imported before the project packages.
from hw07_config import AGENT_TEMPERATURE, LOCAL_MODEL, RAW_DIR, RELIABILITY_ATTEMPTS_PER_TASK, VERIFY_SEED

# isort: split
from agent_loop import OllamaChatModel, make_domain_toolset, run_agent  # noqa: E402
from agent_loop.tasks import chain_complete, load_tasks, verify  # noqa: E402

FIELDS = ["attempt", "task_id", "seed", "stop_reason", "tool_calls", "iterations", "first_try_turns", "first_try_ok",
          "repair_turns", "repaired_ok", "malformed_arguments", "unknown_tool", "text_instead_of_tool", "lost_chain",
          "chain_complete", "verifier_passed", "repairs", "total_tokens", "latency_ms", "tools_used"]


def main() -> None:
    """Run the attempts, classify failures and save per-attempt rows."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempts-per-task", type=int, default=RELIABILITY_ATTEMPTS_PER_TASK)
    args = parser.parse_args()
    tasks = load_tasks()
    toolset = make_domain_toolset()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    rows, traces = [], []
    print(f"HW7 Part 2.III reliability - {LOCAL_MODEL} temperature={AGENT_TEMPERATURE} - "
          f"{len(tasks)} tasks x {args.attempts_per_task} attempts - {datetime.now():%Y-%m-%d %H:%M:%S}")
    attempt = 0
    for i in range(args.attempts_per_task):
        for task in tasks:  # interleave tasks so a slow drift in the machine affects all equally
            attempt += 1
            seed = VERIFY_SEED + i
            print(f"\n--- attempt {attempt}: task {task.id} seed {seed}", flush=True)
            result = run_agent(task.prompt, model=OllamaChatModel(temperature=AGENT_TEMPERATURE, seed=seed),
                               toolset=toolset)
            kinds = Counter(f["kind"] for f in result["failures"])
            complete = chain_complete(task, result)
            verdict = verify(task, result)
            row = {"attempt": attempt, "task_id": task.id, "seed": seed, "stop_reason": result["stop_reason"],
                   "tool_calls": result["tool_calls"], "iterations": result["iterations"], **result["wellformed"],
                   "malformed_arguments": kinds["malformed_arguments"], "unknown_tool": kinds["unknown_tool"],
                   "text_instead_of_tool": kinds["text_instead_of_tool"], "lost_chain": int(not complete),
                   "chain_complete": complete, "verifier_passed": verdict.passed, "repairs": result["repairs"],
                   "total_tokens": result["usage"]["total_tokens"], "latency_ms": result["latency_ms"],
                   "tools_used": " > ".join(c["tool"] for c in result["trace"])}
            rows.append(row)
            traces.append({**row, "failures": result["failures"], "final_answer": result["final_answer"],
                           "trace": [{k: c[k] for k in ("tool", "inputs", "ok", "error")} for c in result["trace"]],
                           "verifier": verdict.to_dict(), "model": result["model"]})
            print(f"    -> {result['stop_reason']}, tools [{row['tools_used']}], failures {dict(kinds) or 'none'}, "
                  f"chain complete {complete}, verifier {'PASS' if verdict.passed else 'FAIL'}")

    with (RAW_DIR / "toolcall_reliability.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    with (RAW_DIR / "toolcall_reliability.jsonl").open("w", encoding="utf-8") as fh:
        for t in traces:
            fh.write(json.dumps(t, default=str) + "\n")

    turns = sum(r["first_try_turns"] for r in rows)
    ok = sum(r["first_try_ok"] for r in rows)
    repaired = sum(r["repaired_ok"] for r in rows)
    print(f"\n{len(rows)} attempts | first-try turns {turns} | well-formed before repair {ok}/{turns} "
          f"= {ok / turns:.1%} | after repair {ok + repaired}/{turns} = {(ok + repaired) / turns:.1%}")
    for kind in ("malformed_arguments", "unknown_tool", "text_instead_of_tool", "lost_chain"):
        print(f"  {kind:22} {sum(r[kind] for r in rows)}")
    print(f"Saved -> {RAW_DIR / 'toolcall_reliability.csv'}")


if __name__ == "__main__":
    main()
