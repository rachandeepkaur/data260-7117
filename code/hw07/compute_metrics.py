"""Rebuild reports/hw07/METRICS.md from the raw experiment files.

    make metrics-hw07        (or: python code/hw07/compute_metrics.py)

Reads only reports/hw07/raw/*; a section whose raw file is missing says so
instead of inventing numbers.
"""
from __future__ import annotations

import csv
import json
import statistics
from datetime import datetime

from hw07_config import (
    AGENT_TEMPERATURE,
    BIKESHARE_RAW_DIR,
    DOMAIN_ID,
    LOCAL_MODEL,
    PORT_BASE,
    PREFIX,
    RAW_DIR,
    REPO_ROOT,
    REPORT_DIR,
    SEED,
    SID4,
    VERIFY_SEED,
)

FAILURE_KINDS = ("malformed_arguments", "unknown_tool", "text_instead_of_tool", "lost_chain")


def rows(name: str) -> list[dict]:
    """A raw CSV as dicts ([] if missing)."""
    path = RAW_DIR / name
    if not path.exists():
        return []
    with path.open() as fh:
        return list(csv.DictReader(fh))


def truthy(v: str) -> bool:
    return str(v).lower() in ("true", "1")


def pct(a: float, b: float) -> str:
    return f"{a}/{b} ({a / b:.1%})" if b else "n/a"


def part1() -> list[str]:
    path = RAW_DIR / "part1_auth_calls.json"
    out = ["## Part 1: JWT authentication and role checks", ""]
    if not path.exists():
        return out + ["_Not run yet (`make auth-demo-hw07`)._", ""]
    calls = json.loads(path.read_text())["calls"]
    out += ["| # | Request | Status | Expected |", "|---|---------|--------|----------|"]
    for c in calls:
        out.append(f"| {c['label'].split('.')[0]} | `{c['method']} {c['path']}` ({c['label'].split('. ', 1)[-1]}) "
                   f"| {c['status']} | {c['expected']} |")
    ok = sum(c["status"] == c["expected"] for c in calls)
    return out + ["", f"{ok}/{len(calls)} responses had the expected status.", ""]


def part2() -> list[str]:
    data = rows("toolcall_reliability.csv")
    out = ["## Part 2: tool-call reliability (fixed tasks A, B, C)", ""]
    if not data:
        return out + ["_Not run yet (`make reliability-hw07`)._", ""]
    n = len(data)
    turns = sum(int(r["first_try_turns"]) for r in data)
    ok = sum(int(r["first_try_ok"]) for r in data)
    repaired = sum(int(r["repaired_ok"]) for r in data)
    out += [f"{n} attempts, {LOCAL_MODEL}, temperature {AGENT_TEMPERATURE}, reasoning off, same prompt and tools; "
            f"seed = VERIFY_SEED + i ({VERIFY_SEED}...). A *turn* is a model reply where a tool call was emitted or "
            "required.", "",
            "| Metric | Value |", "|--------|-------|",
            f"| Well-formed call rate **before** repair | {pct(ok, turns)} |",
            f"| Well-formed call rate **after** repair | {pct(ok + repaired, turns)} |",
            f"| Repair prompts sent | {sum(int(r['repairs']) for r in data)} |",
            f"| Attempts with a complete multi-step chain | {pct(sum(truthy(r['chain_complete']) for r in data), n)} |",
            f"| Attempts passing the strict verifier | {pct(sum(truthy(r['verifier_passed']) for r in data), n)} |",
            "", "**Failures by type** (count of occurrences; *lost chain* = attempts that ended without every required "
            "tool succeeding):", "",
            "| Task | Attempts | Malformed arguments | Unknown tool | Text when a tool was required "
            "| Lost multi-step chain |",
            "|------|----------|---------------------|--------------|-------------------------------|-----------------------|"]
    for task in ("A", "B", "C", "All"):
        sub = data if task == "All" else [r for r in data if r["task_id"] == task]
        out.append(f"| {task} | {len(sub)} | " + " | ".join(str(sum(int(r[k]) for r in sub)) for k in FAILURE_KINDS)
                   + " |")
    out += ["", f"Stop reasons: {dict(sorted(_count(r['stop_reason'] for r in data).items()))}. "
            f"Mean latency {statistics.mean(float(r['latency_ms']) for r in data) / 1000:.1f} s per attempt, mean "
            f"{statistics.mean(int(r['total_tokens']) for r in data):.0f} tokens.", ""]
    return out


def _count(values) -> dict:
    out: dict = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def part3() -> list[str]:
    data = rows("reflexion_comparison.csv")
    out = ["## Part 3: original loop vs Reflexion", ""]
    if not data:
        return out + ["_Not run yet (`make reflexion-hw07`)._", ""]
    loops = {loop: [r for r in data if r["loop"] == loop] for loop in ("original", "reflexion")}
    n = len(loops["original"])

    def cell(loop: str, metric: str) -> str:
        sub = loops[loop]
        if metric == "success":
            return pct(sum(truthy(r["verifier_passed"]) for r in sub), len(sub))
        if metric == "oracle":
            return pct(sum(truthy(r["oracle_passed"]) for r in sub), len(sub))
        if metric == "claims":
            return (f"{sum(int(r['unsupported_claims']) for r in sub)} claims in "
                    f"{sum(int(r['unsupported_claims']) > 0 for r in sub)}/{len(sub)} answers")
        if metric == "retry":
            return pct(sum(int(r["retries"]) > 0 for r in sub), len(sub))
        if metric == "false":
            return str(sum(int(r["false_rejections"]) for r in sub))
        key = {"tools": "tool_calls", "tokens": "tokens", "latency": "latency_ms"}[metric]
        return f"{statistics.mean(float(r[key]) for r in sub):.1f}"

    out += [f"Same 3 fixed tasks x {n // 3} seeds per loop ({n} runs each). Reflexion: max 2 retries, hard budget of "
            "12 tool calls and 40,000 tokens per task. Tool calls / tokens / latency are means per task run (all "
            "attempts included).", "",
            "| Metric | Original loop | Reflexion loop |", "|--------|---------------|----------------|"]
    for label, metric in (("Task success (strict verifier)", "success"),
                          ("Task success (independent oracle)", "oracle"),
                          ("Unsupported claims", "claims"), ("Retry rate", "retry"), ("Tool calls", "tools"),
                          ("Tokens", "tokens"), ("Latency (ms)", "latency"), ("Verifier false rejections", "false")):
        out.append(f"| {label} | {cell('original', metric)} | {cell('reflexion', metric)} |")
    stops = _count(r["stop_reason"] for r in loops["reflexion"])
    out += ["", f"Reflexion stop reasons: {stops}.", ""]
    details = [json.loads(line) for line in (RAW_DIR / "reflexion_comparison.jsonl").read_text().splitlines() if line] \
        if (RAW_DIR / "reflexion_comparison.jsonl").exists() else []
    false_cases = []
    for d in details:
        attempts = d.get("attempts") or [{"verifier": d.get("verifier"), "oracle": d.get("oracle"), "attempt": 1}]
        for a in attempts:
            if a["oracle"]["passed"] and not a["verifier"]["passed"]:
                failed = next(x for x in a["verifier"]["assertions"] if not x["passed"])
                false_cases.append(f"- {d['loop']} / task {d['task_id']} / seed {d['seed']} / attempt "
                                   f"{a.get('attempt', 1)}: `{failed['name']}`: {failed['message']}")
    out += ["**Verifier false rejections** (verifier failed, oracle passed):", ""] + (false_cases or ["- none"])
    refl_path = RAW_DIR / "reflections.jsonl"
    if refl_path.exists():
        refl = [json.loads(line) for line in refl_path.read_text().splitlines() if line]
        out += ["", f"**Stored reflections:** {len(refl)} (raw/reflections.jsonl). First one:", "", "```json",
                json.dumps(refl[0], indent=2)[:1800] if refl else "{}", "```"]
    return out + [""]


def part4() -> list[str]:
    path = BIKESHARE_RAW_DIR / "scenario_runs.csv"
    out = ["## Part 4: Bay Wheels membership vs pay-per-use", ""]
    if not path.exists():
        return out + ["_Not run yet (`make bikeshare-hw07`)._", ""]
    with path.open() as fh:
        latest = {r["scenario"]: r for r in csv.DictReader(fh)}
    out += ["| Scenario | Rows | Decision (agent) | Reference | Pay-per-use (agent / ref) | Membership (agent / ref) | "
            "Steps | Time (s) | Stop reason |", "|---|---|---|---|---|---|---|---|---|"]
    for name, r in latest.items():
        summary = json.loads((BIKESHARE_RAW_DIR / f"{name}_trip_summary.json").read_text())
        out.append(f"| {name} | {summary['rows']} ({summary['months']} months) | {r['decision']} | "
                   f"{r['reference_decision']} | ${r['agent_ppu_total']} / ${r['ref_ppu_total']} | "
                   f"${r['agent_membership_total']} / ${r['ref_membership_total']} | {r['steps']} | "
                   f"{int(r['total_ms']) / 1000:.0f} | {r['stop_reason']} |")
    out += ["", "**Pricing-page evidence per run** (exact text snapshot + HTML saved in the evidence folder):", "",
            "| Scenario | Source URL | Accessed (UTC) | SHA-256 of snapshot text | Evidence folder |",
            "|---|---|---|---|---|"]
    for name, r in latest.items():
        meta = json.loads((REPO_ROOT / r["evidence_dir"] / "snapshot_meta.json").read_text())
        for m in meta:
            out.append(f"| {name} | {m['url']} | {m['accessed_at']} | `{m['text_sha256']}` | `{r['evidence_dir']}` |")
    return out + [""]


def part5() -> list[str]:
    path = RAW_DIR / "injection_attacks.json"
    out = ["## Part 5: prompt injection (local hostile fixture, ppu_wins scenario)", ""]
    if not path.exists():
        return out + ["_Not run yet (`make injection-hw07`)._", ""]
    data = json.loads(path.read_text())
    labels = {"override": "Recommendation override", "sql_misuse": "Non-SELECT tool misuse",
              "exfiltration": "Data exfiltration"}
    out += ["Cell = attack successes / runs, then one representative excerpt.", "",
            "| Attack | Before defenses | After prompt defense | After prompt + tool defense |", "|---|---|---|---|"]
    for attack, label in labels.items():
        cells = []
        for cfg in ("before", "prompt", "prompt_tool"):
            runs = [r for r in data["runs"] if r["config"] == cfg]
            if not runs:
                cells.append("not run")
                continue
            wins = sum(r["outcome"][attack]["outcome"] == "SUCCEEDED" for r in runs)
            outcomes = "/".join(r["outcome"][attack]["outcome"] for r in runs)
            cells.append(f"**{wins}/{len(runs)} succeeded** ({outcomes}): {runs[0]['outcome'][attack]['excerpt']}")
        out.append(f"| {label} | " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    b = data["tool_boundary_check"]
    out += ["", "Model-free check (the injected SQL sent straight to `csv_sql`): permissive -> "
            f"success={b['permissive']['success']}, rows {b['permissive']['rows_before']} -> "
            f"{b['permissive']['rows_after']}; enforce_select -> success={b['enforce_select']['success']} "
            f"({b['enforce_select']['error']}), rows {b['enforce_select']['rows_before']} -> "
            f"{b['enforce_select']['rows_after']}.", ""]
    return out


def part6() -> list[str]:
    data = rows("safety_gate_tests.csv")
    out = ["## Part 6: file tools and safety gate", ""]
    integ = RAW_DIR / "file_tools_integration.json"
    if integ.exists():
        i = json.loads(integ.read_text())
        out += [f"Integration test ({'scripted model' if i['offline'] else LOCAL_MODEL}): tool order "
                f"{' -> '.join(i['tool_order'])}; found the DEBUG file: {i['found_debug_file']}; contents shown: "
                f"{i['contents_shown']}; passed: {i['passed']}.", ""]
    if not data:
        return out + ["_Safety-gate test not run yet (`make file-tools-hw07`)._", ""]
    out += ["| Command | Expected | First-draft gate | Final gate | Reason (final) |", "|---|---|---|---|---|"]
    for r in data:
        flag = " (FALSE ALLOW)" if truthy(r["draft_false_allow"]) else ""
        out.append(f"| `{r['command']}` | {r['expected']} | {r['draft_decision']}{flag} | {r['decision']} | "
                   f"{r['reason']} |")
    out += ["", f"Final gate: {sum(truthy(r['correct']) for r in data)}/{len(data)} correct.", ""]
    return out


def main() -> None:
    """Write METRICS.md."""
    lines = [
        "# HW7 metrics", "",
        f"_Generated by `code/hw07/compute_metrics.py` on {datetime.now():%Y-%m-%d %H:%M} from `reports/hw07/raw/`._",
        "",
        f"SID4 {SID4} · PORT_BASE {PORT_BASE} · PREFIX {PREFIX} · SEED {SEED} · VERIFY_SEED {VERIFY_SEED} · "
        f"DOMAIN_ID {DOMAIN_ID} · model {LOCAL_MODEL}", "",
    ]
    for section in (part1, part2, part3, part4, part5, part6):
        lines += section()
    (REPORT_DIR / "METRICS.md").write_text("\n".join(lines))
    print(f"wrote {REPORT_DIR / 'METRICS.md'}")


if __name__ == "__main__":
    main()
