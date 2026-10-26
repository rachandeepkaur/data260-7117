"""HW6 Part 4.4: generate one function with AGENT.md in the system prompt and
verify that it follows AGENT.md.

    make agent-md-check-hw06

The local model gets the file-memory system prompt (AGENT.md + MEMORY.md) and
a task that does NOT repeat the conventions: write `parse_fact_line`, the
parser for MEMORY.md bullets, plus its tests. The reply is saved to
reports/hw06/agent_md_check/generated_parse_fact_line.py and checked:
  static (ast)  - one check per AGENT.md rule that can be verified in code
  behavioural   - the generated tests and our own tests are run in a
                  subprocess (python -I) so nothing is imported into this one
Result -> raw/agent_md_check.json and agent_md_check/AGENT_MD_CHECK.md
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from hw06_config import AGENT_MD, MEMORY_MD, RAW_DIR, REPORT_DIR

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from file_memory import build_system_prompt, load_memory_files  # noqa: E402
from model_client import ModelClient  # noqa: E402  (path added by file_memory)

OUT_DIR = REPORT_DIR / "agent_md_check"
GENERATED = OUT_DIR / "generated_parse_fact_line.py"

TASK = (
    "Write a new Python module for this repository containing a function `parse_fact_line(line)` that "
    "parses one MEMORY.md bullet of the form '- (YYYY-MM-DD) fact text' and returns a tuple of "
    "(datetime.date, str) with the fact text stripped. Lines that do not match this form, or whose date "
    "is not a real calendar date, are invalid input. Include the module's tests in the same file. "
    "Reply with only the complete module in a single ```python code block."
)

OUR_TESTS = r'''
import datetime, importlib.util, sys
spec = importlib.util.spec_from_file_location("gen", sys.argv[1]); gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)
results = {}
def case(name, fn):
    try: fn(); results[name] = "pass"
    except Exception as exc: results[name] = f"fail: {type(exc).__name__}: {exc}"
def valid():
    assert gen.parse_fact_line("- (2026-10-12) The user's name is Rachandeep Kaur.") == \
        (datetime.date(2026, 10, 12), "The user's name is Rachandeep Kaur.")
def strips():
    assert gen.parse_fact_line("-  (2026-01-05)   Bay BBQ scored 98.  ")[1] == "Bay BBQ scored 98."
def bad_format():
    try: gen.parse_fact_line("The user likes tea")
    except ValueError: return
    raise AssertionError("no ValueError for a line without a date")
def bad_date():
    try: gen.parse_fact_line("- (2026-02-30) Impossible date")
    except ValueError: return
    raise AssertionError("no ValueError for 2026-02-30")
def generated_tests():
    names = [n for n in dir(gen) if n.startswith("test_") and callable(getattr(gen, n))]
    assert names, "module defines no test_* functions"
    for n in names: getattr(gen, n)()
    results["generated_test_names"] = names
for name, fn in [("valid_line", valid), ("strips_whitespace", strips), ("invalid_format_raises_ValueError", bad_format),
                 ("invalid_date_raises_ValueError", bad_date), ("generated_tests_pass", generated_tests)]:
    case(name, fn)
print(__import__("json").dumps(results))
'''


def extract_code(reply: str) -> str:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", reply, flags=re.S)
    return (m.group(1) if m else reply).strip() + "\n"


def static_checks(code: str) -> list[dict]:
    tree = ast.parse(code)
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    call_names = {n.func.id for n in calls if isinstance(n.func, ast.Name)}
    tests = [f for f in funcs if f.name.startswith("test_")]
    lib_funcs = [f for f in funcs if not f.name.startswith("test_")]

    def typed(f) -> bool:
        args = f.args.posonlyargs + f.args.args + f.args.kwonlyargs
        return f.returns is not None and all(a.annotation is not None for a in args if a.arg not in ("self", "cls"))

    def rule(rule_text, category, passed, evidence):
        return {"agent_md_rule": rule_text, "category": category, "passed": bool(passed), "evidence": evidence}

    return [
        rule("Every module starts with a docstring", "Coding conventions",
             ast.get_docstring(tree) is not None, "module docstring present" if ast.get_docstring(tree) else "missing"),
        rule("... and `from __future__ import annotations`", "Coding conventions",
             any(isinstance(n, ast.ImportFrom) and n.module == "__future__"
                 and any(a.name == "annotations" for a in n.names)
                 for n in tree.body), "checked top-level imports"),
        rule("Type hints on all parameters and on the return value", "Coding conventions",
             all(typed(f) for f in lib_funcs), {f.name: typed(f) for f in lib_funcs}),
        rule("Every function has a docstring", "Coding conventions",
             all(ast.get_docstring(f) for f in lib_funcs), {f.name: bool(ast.get_docstring(f)) for f in lib_funcs}),
        rule("snake_case function names, UPPER_CASE constants", "Coding conventions",
             all(re.fullmatch(r"[a-z_][a-z0-9_]*", f.name) for f in funcs)
             and all(re.fullmatch(r"[A-Z_][A-Z0-9_]*", t.id) for n in tree.body if isinstance(n, ast.Assign)
                     for t in n.targets if isinstance(t, ast.Name)),
             [f.name for f in funcs]),
        rule("Invalid input raises a specific exception; no bare `except:`", "Coding conventions",
             not any(isinstance(n, ast.ExceptHandler) and n.type is None for n in ast.walk(tree))
             and any(isinstance(n, ast.Raise) for f in lib_funcs for n in ast.walk(f)),
             "raise found, no bare except" if not any(isinstance(n, ast.ExceptHandler) and n.type is None
                                                      for n in ast.walk(tree)) else "bare except found"),
        rule("Never return None to signal an error", "Coding conventions",
             not any(isinstance(n, ast.Return)
                     and (n.value is None or (isinstance(n.value, ast.Constant) and n.value.value is None))
                     for f in lib_funcs for n in ast.walk(f)), "no `return None` in library functions"),
        rule("Library code does not print", "Coding conventions",
             not any(isinstance(n.func, ast.Name) and n.func.id == "print" for f in lib_funcs for n in ast.walk(f)
                     if isinstance(n, ast.Call)), "no print() in library functions"),
        rule("Tests are plain test_* functions using assert, valid + invalid case", "Testing approach",
             len(tests) >= 2 and all(any(isinstance(n, ast.Assert) for n in ast.walk(t)) or "raises" in ast.unparse(t)
                                     or "ValueError" in ast.unparse(t) for t in tests),
             [t.name for t in tests]),
        rule("Tests run offline (no network/DB/Ollama imports)", "Testing approach",
             not re.search(r"\b(import|from)\s+(requests|httpx|pymongo|sqlalchemy|socket|urllib)", code),
             "no network/database imports"),
        rule("Never use eval or exec", "Prohibited actions", not ({"eval", "exec"} & call_names),
             "no eval/exec calls"),
        rule("Never hard-code 8817 or s7117", "Project description", not re.search(r"8817|s7117", code),
             "no hard-coded port/prefix"),
    ]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    system = build_system_prompt(load_memory_files(AGENT_MD, MEMORY_MD))
    print(f"[{datetime.now():%H:%M:%S}] system prompt = AGENT.md + MEMORY.md ({len(system)} chars); task:\n  {TASK}")
    client = ModelClient(temperature=0.0)
    reply = client.complete([{"role": "system", "content": system}, {"role": "user", "content": TASK}], max_tokens=1500)
    code = extract_code(reply)
    GENERATED.write_text(code)
    print(f"\n--- generated module ({len(code.splitlines())} lines) -> {GENERATED} ---\n{code}")

    try:
        checks = static_checks(code)
    except SyntaxError as exc:
        checks = [{"agent_md_rule": "module parses", "category": "-", "passed": False, "evidence": str(exc)}]
    proc = subprocess.run([sys.executable, "-I", "-c", OUR_TESTS, str(GENERATED)],
                          capture_output=True, text=True, timeout=60)
    try:
        behaviour = json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        behaviour = {"error": proc.stderr.strip()[-500:]}
    behaviour_ok = all(v == "pass" for k, v in behaviour.items() if k != "generated_test_names")

    print("\n--- AGENT.md compliance ---")
    for c in checks:
        print(f"[{'PASS' if c['passed'] else 'FAIL'}] ({c['category']}) {c['agent_md_rule']}")
    print("\n--- behaviour ---")
    for k, v in behaviour.items():
        print(f"  {k}: {v}")
    passed = sum(c["passed"] for c in checks)
    print(f"\nstatic: {passed}/{len(checks)} AGENT.md rules followed; behaviour: {'pass' if behaviour_ok else 'FAIL'}")

    result = {"task": TASK, "model": "qwen3:8b", "generated_file": str(GENERATED.relative_to(REPORT_DIR.parent.parent)),
              "usage": client.last_usage, "static_checks": checks, "behaviour": behaviour,
              "rules_followed": passed, "rules_checked": len(checks), "behaviour_ok": behaviour_ok}
    (RAW_DIR / "agent_md_check.json").write_text(json.dumps(result, indent=2))
    rows = "\n".join(f"| {c['category']} | {c['agent_md_rule']} | {'PASS' if c['passed'] else 'FAIL'} |"
                     for c in checks)
    brows = "\n".join(f"| {k} | {v} |" for k, v in behaviour.items())
    (OUT_DIR / "AGENT_MD_CHECK.md").write_text(
        f"# AGENT.md compliance of a generated function\n\nGenerated {datetime.now():%Y-%m-%d %H:%M} by "
        f"`make agent-md-check-hw06` (qwen3:8b, system prompt = AGENT.md + MEMORY.md).\n\n"
        f"Task given to the model (it does not restate the conventions):\n\n> {TASK}\n\n"
        f"**{passed}/{len(checks)} checkable AGENT.md rules followed; behaviour tests: "
        f"{'pass' if behaviour_ok else 'FAIL'}.**\n\n| Category | AGENT.md rule | Result |\n|---|---|---|\n{rows}\n\n"
        f"## Behaviour (run with `python -I` in a subprocess)\n\n| Test | Result |\n|---|---|\n{brows}\n")


if __name__ == "__main__":
    main()
