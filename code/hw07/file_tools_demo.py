"""HW7 Part 6: file tools + safety gate, in one combined test run.

    make file-tools-hw07     (or: python code/hw07/file_tools_demo.py [--offline])

Everything runs inside a fresh temporary course sandbox
($TMPDIR/data260_hw07_sandbox_*); nothing outside it is touched.

(a) Integration test: three small Python files are created, then ONE
    instruction is given to the hand-written agent loop (Part 2) with the
    six file tools; it must go glob_files -> search_in_files -> read_file and
    show the file containing DEBUG. --offline replays a scripted model.
    Also shows read_file(max_lines), edit_file's diff and search_in_files'
    file_pattern directly.
(b) Safety-gate test: 5 commands that should pass and 5 that should be
    blocked, first against the first-draft deny-list (kept here only to show
    the false allow it had), then against the final gate in
    file_tools/safety.py. Allowed commands are executed in the sandbox through
    the bash tool; blocked ones never run.

Writes raw/safety_gate_tests.csv, raw/safety_gate_tests.json and raw/file_tools_integration.json.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

# hw07_config puts code/ on sys.path, so it must be imported before the project packages.
from hw07_config import AGENT_TEMPERATURE, RAW_DIR, SEED

# isort: split
from agent_loop import OllamaChatModel, ScriptedModel, run_agent  # noqa: E402
from file_tools import (  # noqa: E402
    SAFE_PREFIXES,
    bash,
    confirm_bash,
    edit_file,
    is_destructive,
    make_file_toolset,
    read_file,
    search_in_files,
)

FILES = {
    "app.py": 'DEBUG = True\n\n\ndef main() -> None:\n    """Entry point."""\n    print("inspection app")\n',
    "utils.py": ('def slugify(name: str) -> str:\n    """Lower-case, dash-separated."""\n'
                 '    return "-".join(name.lower().split())\n'),
    "models.py": ('from dataclasses import dataclass\n\n\n@dataclass\nclass Inspection:\n'
                  '    code: str\n    score: int\n'),
}
INSTRUCTION = ("Find the Python file in the sandbox that contains DEBUG and show me its full contents. "
               "Use exactly three steps: glob_files to list the *.py files, then search_in_files for DEBUG with "
               "file_pattern *.py, then read_file on the matching file.")
FILE_SYSTEM_PROMPT = ("You are a file assistant working inside a sandbox directory. Use the provided tools; paths are "
                      "relative to the sandbox. Do one tool call per step and use each result to choose the next "
                      "call. When done, answer in plain text and include the file's contents exactly as read_file "
                      "returned them.")

# (command, should_pass) - the 10-command safety-gate test.
GATE_CASES = [
    ("ls -la", True),
    ("cat notes.txt", True),
    ("grep -n DEBUG app.py utils.py models.py", True),
    ("head -n 3 app.py", True),
    ("wc -l app.py", True),
    ("ls; rm -fr ./build", False),                     # recursive deletion hidden behind a safe prefix
    ("sudo chown root:wheel notes.txt", False),        # privilege escalation + ownership change
    ("dd if=/dev/zero of=/dev/disk2 bs=1m", False),    # raw-device write
    ("mkfs.ext4 /dev/sdb1", False),                    # filesystem creation
    ("cat notes.txt > /etc/hosts", False),             # redirection to a root path, safe prefix
]

# First-draft gate, kept only to document the false allow found by this test:
# prefix match on the whole string + a short regex deny-list.
DRAFT_DENY = [r"\brm\s+-rf\b", r"^\s*sudo\b", r"\bchmod\b", r"\bchown\b", r"\bdd\s+if=", r"\bmkfs", r">\s*/etc/"]


def draft_gate(command: str) -> bool:
    """True = the first draft would allow the command."""
    if any(re.search(p, command) for p in DRAFT_DENY):
        return False
    return any(command == p or command.startswith(p + " ") or command.startswith(p + ";") for p in SAFE_PREFIXES)


def integration_test(sandbox: Path, offline: bool) -> dict:
    """(a) glob -> search -> read through the agent loop with the file toolset."""
    for name, content in FILES.items():
        (sandbox / name).write_text(content)
    (sandbox / "notes.txt").write_text("sandbox notes for the safety-gate test\n")
    print(f"(a) Integration test - sandbox {sandbox}")
    print(f"    created: {', '.join(FILES)} (+ notes.txt)")
    print(f"    instruction: {INSTRUCTION}\n")
    model = ScriptedModel([
        {"tool_calls": [{"name": "glob_files", "arguments": {"pattern": "*.py"}}]},
        {"tool_calls": [{"name": "search_in_files", "arguments": {"pattern": "DEBUG", "file_pattern": "*.py"}}]},
        {"tool_calls": [{"name": "read_file", "arguments": {"path": "app.py"}}]},
        "app.py contains DEBUG:\n" + FILES["app.py"],
    ]) if offline else OllamaChatModel(temperature=AGENT_TEMPERATURE, seed=SEED)
    result = run_agent(INSTRUCTION, model=model, toolset=make_file_toolset(sandbox), system_prompt=FILE_SYSTEM_PROMPT)
    order = [c["tool"] for c in result["trace"]]
    read_paths = [c["inputs"].get("path") for c in result["trace"] if c["tool"] == "read_file" and c["ok"]]
    found = "app.py" in read_paths
    sequence_ok = order[:3] == ["glob_files", "search_in_files", "read_file"]
    shown = "DEBUG = True" in (result["final_answer"] or "")
    print(f"\n    final answer:\n{_indent(result['final_answer'] or '')}")
    print(f"    tool order: {' -> '.join(order)} | glob->search->read: {sequence_ok} | "
          f"read the DEBUG file (app.py): {found} | contents shown: {shown}")

    print("\n    direct checks:")
    r = read_file(sandbox, "models.py", max_lines=2)
    print(f"    read_file(models.py, max_lines=2) -> {r['data']['lines_returned']}/{r['data']['total_lines']} lines, "
          f"truncated={r['data']['truncated']}")
    s = search_in_files(sandbox, "def ", file_pattern="utils.py")
    print(f"    search_in_files('def ', file_pattern='utils.py') -> files {s['data']['files']}")
    e = edit_file(sandbox, "app.py", "DEBUG = True", "DEBUG = False")
    print("    edit_file(app.py, 'DEBUG = True' -> 'DEBUG = False') diff:\n" + _indent(e["data"]["diff"]))
    return {"instruction": INSTRUCTION, "offline": offline, "tool_order": order, "sequence_ok": sequence_ok,
            "found_debug_file": found, "contents_shown": shown, "stop_reason": result["stop_reason"],
            "tool_calls": result["tool_calls"], "final_answer": result["final_answer"],
            "trace": [{k: c[k] for k in ("tool", "inputs", "ok")} for c in result["trace"]],
            "read_max_lines": r["data"], "search_file_pattern": s["data"]["files"], "edit_diff": e["data"]["diff"],
            "passed": sequence_ok and found and shown}


def gate_test(sandbox: Path) -> list[dict]:
    """(b) the 10-command safety-gate test, draft vs final."""
    print("\n(b) Safety-gate test - 5 should pass, 5 should be blocked")
    print(f"    {'command':42} {'expect':6} {'draft':6} {'final':6} reason")
    rows = []
    for command, should_pass in GATE_CASES:
        draft_allowed = draft_gate(command)
        decision = confirm_bash(command)
        executed = bash(sandbox, command) if decision.allowed else None
        row = {"command": command, "expected": "allow" if should_pass else "block",
               "draft_decision": "allow" if draft_allowed else "block",
               "draft_false_allow": draft_allowed and not should_pass,
               "is_destructive": is_destructive(command), "decision": decision.decision, "reason": decision.reason,
               "categories": list(decision.categories), "correct": decision.allowed == should_pass,
               "exit_code": executed["data"]["exit_code"] if executed and executed["ok"] else None,
               "with_confirmation": confirm_bash(command, auto_approve=True).decision}
        rows.append(row)
        flag = "  <- draft FALSE ALLOW (fixed)" if row["draft_false_allow"] else ""
        print(f"    {command:42} {row['expected']:6} {row['draft_decision']:6} {row['decision']:6} "
              f"{decision.reason}{flag}")
    false_allows = [r["command"] for r in rows if r["draft_false_allow"]]
    final_ok = sum(r["correct"] for r in rows)
    print(f"\n    draft gate false allows: {false_allows or 'none'}")
    print("    fix: split compound commands (; && || | & $(...)) and check every piece, parse rm flags in any "
          "order (-rf, -fr, -r -f, --recursive), check redirections/tee targets, and run the deny-list before "
          "the allow-list.")
    n_allowed = sum(r["decision"] == "allow" for r in rows)
    print(f"    final gate: {final_ok}/10 correct ({n_allowed} allowed, {len(rows) - n_allowed} blocked); "
          f"destructive with explicit confirmation -> "
          f"{confirm_bash('rm -rf build', auto_approve=True).decision} ('rm -rf build', auto_approve=True)")
    return rows


def _indent(text: str) -> str:
    return "\n".join("      " + line for line in text.splitlines())


def main() -> None:
    """Run (a) and (b) in one sandbox and save the results."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="scripted model instead of qwen3:8b")
    args = parser.parse_args()
    sandbox = Path(tempfile.mkdtemp(prefix="data260_hw07_sandbox_"))
    print(f"HW7 Part 6 - {datetime.now():%Y-%m-%d %H:%M:%S}\n")
    try:
        integration = integration_test(sandbox, args.offline)
        rows = gate_test(sandbox)
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "file_tools_integration.json").write_text(json.dumps(integration, indent=2))
    (RAW_DIR / "safety_gate_tests.json").write_text(json.dumps(
        {"generated_at": datetime.now().isoformat(timespec="seconds"), "safe_prefixes": list(SAFE_PREFIXES),
         "draft_deny_patterns": DRAFT_DENY, "results": rows}, indent=2))
    with (RAW_DIR / "safety_gate_tests.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\nintegration passed: {integration['passed']} | gate correct: {sum(r['correct'] for r in rows)}/10 "
          f"-> {RAW_DIR / 'safety_gate_tests.csv'}")


if __name__ == "__main__":
    main()
