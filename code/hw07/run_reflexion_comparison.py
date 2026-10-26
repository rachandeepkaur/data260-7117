"""HW7 Part 3: original loop (Part 2) vs bounded Reflexion on the same fixed tasks.

    make reflexion-hw07      (or: python code/hw07/run_reflexion_comparison.py [--runs-per-task 3])

For each task A/B/C and each seed (SEED + 100 + k) both loops run with the
same model settings. Per run it records: verifier pass (task success),
independent-oracle pass, unsupported claims in the final answer, retries,
tool calls, tokens, latency and the stop reason. A *verifier false rejection*
is any attempt the verifier rejected while the oracle (recomputed from
s7117_rel) accepted the answer.

Reflections (failure + strategy + evidence) are stored, per user and run, in
raw/reflections.jsonl. Results: raw/reflexion_comparison.csv + .jsonl.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime

# hw07_config puts code/ on sys.path, so it must be imported before the project packages.
from hw07_config import AGENT_TEMPERATURE, COMPARISON_RUNS_PER_TASK, LOCAL_MODEL, PREFIX, RAW_DIR, SEED

# isort: split
from agent_loop import OllamaChatModel, make_domain_toolset, run_agent  # noqa: E402
from agent_loop.grounding import unsupported_claims  # noqa: E402
from agent_loop.reflexion import (  # noqa: E402
    DEFAULT_TOKEN_BUDGET,
    DEFAULT_TOOL_CALL_BUDGET,
    MAX_RETRIES,
    ReflectionStore,
    run_reflexion,
)
from agent_loop.tasks import load_tasks, oracle, verify  # noqa: E402
from domain_tools.executor import default_repo  # noqa: E402

FIELDS = ["loop", "task_id", "seed", "verifier_passed", "oracle_passed", "unsupported_claims", "unsupported",
          "retries", "attempts", "tool_calls", "tokens", "latency_ms", "stop_reason", "false_rejections", "run_id"]


def main() -> None:
    """Run both loops on every (task, seed) pair and save the comparison rows."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-per-task", type=int, default=COMPARISON_RUNS_PER_TASK)
    args = parser.parse_args()
    tasks, toolset, repo = load_tasks(), make_domain_toolset(), default_repo()
    store = ReflectionStore(RAW_DIR / "reflections.jsonl")
    user_id = f"{PREFIX}-hw7-comparison"
    rows, details = [], []
    print(f"HW7 Part 3 - {LOCAL_MODEL} temperature={AGENT_TEMPERATURE} - max retries {MAX_RETRIES}, budgets "
          f"{DEFAULT_TOOL_CALL_BUDGET} tool calls / {DEFAULT_TOKEN_BUDGET} tokens - {datetime.now():%Y-%m-%d %H:%M:%S}")
    for k in range(args.runs_per_task):
        seed = SEED + 100 + k
        for task in tasks:
            print(f"\n=== task {task.id} seed {seed}: ORIGINAL loop", flush=True)
            res = run_agent(task.prompt, model=OllamaChatModel(temperature=AGENT_TEMPERATURE, seed=seed),
                            toolset=toolset)
            verdict, orc = verify(task, res), oracle(task, res, repo)
            claims = unsupported_claims(res["final_answer"], [c["observation"] for c in res["trace"]], task.prompt)
            rows.append({"loop": "original", "task_id": task.id, "seed": seed, "verifier_passed": verdict.passed,
                         "oracle_passed": orc["passed"], "unsupported_claims": len(claims),
                         "unsupported": " ".join(claims), "retries": 0, "attempts": 1,
                         "tool_calls": res["tool_calls"], "tokens": res["usage"]["total_tokens"],
                         "latency_ms": res["latency_ms"], "stop_reason": res["stop_reason"],
                         "false_rejections": int(orc["passed"] and not verdict.passed), "run_id": ""})
            details.append({"loop": "original", "task_id": task.id, "seed": seed, "verifier": verdict.to_dict(),
                            "oracle": orc, "final_answer": res["final_answer"],
                            "trace": [{k2: c[k2] for k2 in ("tool", "inputs", "ok")} for c in res["trace"]]})
            print(f"    original: verifier {'PASS' if verdict.passed else 'FAIL'} | oracle "
                  f"{'PASS' if orc['passed'] else 'FAIL'} | unsupported {claims}")

            print(f"=== task {task.id} seed {seed}: REFLEXION loop", flush=True)
            rr = run_reflexion(task, user_id=user_id, model=OllamaChatModel(temperature=AGENT_TEMPERATURE, seed=seed),
                               store=store, toolset=toolset)
            false_rej, attempt_log = 0, []
            for a in rr["attempts"]:
                o = oracle(task, a["result"], repo)
                false_rej += int(o["passed"] and not a["verdict"]["passed"])
                attempt_log.append({"attempt": a["attempt"], "verifier": a["verdict"], "oracle": o,
                                    "final_answer": a["result"]["final_answer"], "context_note": a["context_note"],
                                    "trace": [{k2: c[k2] for k2 in ("tool", "inputs", "ok")}
                                              for c in a["result"]["trace"]]})
            final = rr["final_result"] or {"trace": [], "final_answer": None}
            orc = oracle(task, final, repo)
            claims = unsupported_claims(rr["final_answer"], [c["observation"] for c in final["trace"]], task.prompt)
            rows.append({"loop": "reflexion", "task_id": task.id, "seed": seed,
                         "verifier_passed": rr["verifier_passed"],
                         "oracle_passed": orc["passed"], "unsupported_claims": len(claims),
                         "unsupported": " ".join(claims), "retries": rr["retries"], "attempts": len(rr["attempts"]),
                         "tool_calls": rr["tool_calls"], "tokens": rr["tokens"], "latency_ms": rr["latency_ms"],
                         "stop_reason": rr["stop_reason"], "false_rejections": false_rej, "run_id": rr["run_id"]})
            details.append({"loop": "reflexion", "task_id": task.id, "seed": seed, "run_id": rr["run_id"],
                            "stop_reason": rr["stop_reason"], "attempts": attempt_log,
                            "reflections": store.for_run(user_id, rr["run_id"])})
            print(f"    reflexion: stop {rr['stop_reason']} after {len(rr['attempts'])} attempt(s) | oracle "
                  f"{'PASS' if orc['passed'] else 'FAIL'} | false rejections {false_rej}")

    with (RAW_DIR / "reflexion_comparison.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    with (RAW_DIR / "reflexion_comparison.jsonl").open("w", encoding="utf-8") as fh:
        for d in details:
            fh.write(json.dumps(d, default=str) + "\n")
    for loop in ("original", "reflexion"):
        sub = [r for r in rows if r["loop"] == loop]
        print(f"{loop:9} success {sum(r['verifier_passed'] for r in sub)}/{len(sub)} | oracle "
              f"{sum(r['oracle_passed'] for r in sub)}/{len(sub)} | "
              f"retries {sum(r['retries'] > 0 for r in sub)}/{len(sub)} "
              f"| false rejections {sum(r['false_rejections'] for r in sub)}")
    print(f"Saved -> {RAW_DIR / 'reflexion_comparison.csv'}")


if __name__ == "__main__":
    main()
