"""HW6 Part 4.5: consolidate the 55-line test MEMORY.md and grade the result.

    make consolidation-test-hw06

1. copies reports/hw06/memory_consolidation/MEMORY.original.md -> MEMORY.md
2. runs /compact through FileMemorySession (the same path as the chat CLI),
   so the before/after counts printed here are the /compact evidence
3. saves MEMORY.md -> memory_consolidation/MEMORY.consolidated.md
4. grades it against expected.yaml: < 40 lines, duplicates merged, each
   contradiction resolved correctly / incorrectly / missing, and no
   superseded value silently deleted; compares with the audit flags
   -> raw/consolidation_audit.json + memory_consolidation/CONSOLIDATION_REPORT.md
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import yaml

from hw06_config import MEMORY_MD, MEMORY_TEST_DIR, RAW_DIR

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from file_memory import FileMemorySession, needs_consolidation  # noqa: E402

ORIGINAL = MEMORY_TEST_DIR / "MEMORY.original.md"
CONSOLIDATED = MEMORY_TEST_DIR / "MEMORY.consolidated.md"
EXPECTED = MEMORY_TEST_DIR / "expected.yaml"


def sections(text: str) -> dict[str, list[str]]:
    out, name = {}, ""
    for line in text.splitlines():
        if line.startswith("## "):
            name = line[3:].strip().lower()
            out[name] = []
        elif line.strip().startswith("- ") and name:
            out[name].append(line)
    return out


def grade(text: str, expected: dict, audit: list[dict], summary: dict) -> dict:
    sec = sections(text)
    facts = sec.get("facts", [])
    elsewhere = sec.get("resolved contradictions", []) + next(
        (v for k, v in sec.items() if k.startswith("needs review")), [])
    contradictions = []
    for c in expected["contradictions"]:
        keep_now = any(c["keep"].lower() in f.lower() for f in facts)
        drop_now = any(c["drop"].lower() in f.lower() for f in facts)
        visible = any(c["drop"].lower() in line.lower() for line in elsewhere)
        status = ("correct" if keep_now and not drop_now else
                  "incorrect" if drop_now and not keep_now else
                  "unresolved_both_kept" if keep_now and drop_now else "missing")
        flagged = any(c["drop"].lower() in line.lower() and "AUDIT" in line for line in sec.get("resolved "
                                                                                                "contradictions", [])) \
            or any(c["keep"].lower() in line.lower() and "AUDIT" in line for line in sec.get("resolved "
                                                                                             "contradictions", []))
        contradictions.append({"topic": c["topic"], "status": status, "superseded_value_still_visible": visible,
                               "silently_deleted": not drop_now and not visible,
                               "audit_flagged": flagged, "rule": c["rule"]})
    dups = []
    for d in expected["duplicates"]:
        n = sum(bool(re.search(d["pattern"], f)) for f in facts)
        dups.append({"topic": d["topic"], "copies_before": d["copies"], "lines_after": n, "merged": n == 1})
    total_lines = len(text.splitlines())
    return {
        "total_lines_before": len(ORIGINAL.read_text().splitlines()),
        "total_lines_after": total_lines,
        "under_40_lines": total_lines < 40,
        "non_comment_lines": [summary["lines_before"], summary["lines_after"]],
        "facts": [summary["facts_before"], summary["facts_after"]],
        "exact_duplicates_merged_deterministically": summary["exact_duplicates_merged"],
        "duplicates": dups,
        "duplicates_merged": sum(d["merged"] for d in dups),
        "contradictions": contradictions,
        "contradictions_correct": sum(c["status"] == "correct" for c in contradictions),
        "no_silent_deletion": not any(c["silently_deleted"] for c in contradictions),
        "needs_review": summary["needs_review"],
        "model_resolutions_audit": audit,
    }


def main() -> None:
    expected = yaml.safe_load(EXPECTED.read_text())
    shutil.copyfile(ORIGINAL, MEMORY_MD)
    print(f"[{datetime.now():%H:%M:%S}] copied {ORIGINAL.name} ({len(ORIGINAL.read_text().splitlines())} lines) "
          f"-> {MEMORY_MD}")
    due, reasons = needs_consolidation(MEMORY_MD.read_text())
    print(f"needs_consolidation: {due} - {reasons}")

    session = FileMemorySession(memory_path=MEMORY_MD)
    print("\n> /compact")
    print(session.cmd_compact())
    shutil.copyfile(MEMORY_MD, CONSOLIDATED)
    text = CONSOLIDATED.read_text()
    print(f"\nsaved {CONSOLIDATED} ({len(text.splitlines())} lines):\n{text}")

    summary = session.last_summary
    result = grade(text, expected, summary["audit"], summary)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "consolidation_audit.json").write_text(json.dumps(result, indent=2))
    (RAW_DIR / "consolidation_model_plan.json").write_text(session.last_plan_raw)

    rows = "\n".join(f"| {c['topic']} | {c['status']} | {'yes' if c['superseded_value_still_visible'] else 'no'} | "
                     f"{'yes' if c['audit_flagged'] else 'no'} | {c['rule']} |" for c in result["contradictions"])
    drows = "\n".join(f"| {d['topic']} | {d['copies_before']} | {d['lines_after']} |" for d in result["duplicates"])
    report = f"""# Consolidation test (HW6 Part 4.5)

Generated by `make consolidation-test-hw06` on {datetime.now():%Y-%m-%d %H:%M}.
Input: `MEMORY.original.md` ({result['total_lines_before']} lines). Output: `MEMORY.consolidated.md`
({result['total_lines_after']} lines, under 40: **{result['under_40_lines']}**).

- Non-empty, non-comment lines: {result['non_comment_lines'][0]} -> {result['non_comment_lines'][1]}
- Facts: {result['facts'][0]} -> {result['facts'][1]}
- Exact duplicates merged before the model call: {result['exact_duplicates_merged_deterministically']}
- Duplicate topics merged to one line: {result['duplicates_merged']}/{len(result['duplicates'])}
- Contradictions resolved correctly: {result['contradictions_correct']}/{len(result['contradictions'])}
- Superseded values still visible (no silent deletion): {result['no_silent_deletion']}
- Facts left for review: {len(result['needs_review'])}

## Contradictions

| Topic | Result | Superseded value still visible | Flagged by audit | Correct rule |
|---|---|---|---|---|
{rows}

## Duplicates

| Topic | Copies before | Lines after |
|---|---|---|
{drows}
"""
    (MEMORY_TEST_DIR / "CONSOLIDATION_REPORT.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
