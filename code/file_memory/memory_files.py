"""File-based memory: AGENT.md (durable instructions) + MEMORY.md (durable facts).

HW6 Part 4.2 - load both files, add them to the system prompt, read the
last-consolidated timestamp, and decide when consolidation is required:
    * more than 40 non-empty, non-comment lines in MEMORY.md, or
    * the recorded consolidation time is more than 24 hours old (or missing).

MEMORY.md format:
    # MEMORY.md
    <!-- last_consolidated: 2026-10-16T18:00:00+00:00 -->
    ## Facts
    - (2026-10-12) The user's name is Rachandeep Kaur.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENT_MD = REPO_ROOT / "AGENT.md"
MEMORY_MD = REPO_ROOT / "MEMORY.md"

MAX_MEMORY_LINES = 40
MAX_CONSOLIDATION_AGE = timedelta(hours=24)

TIMESTAMP_RE = re.compile(r"<!--\s*last_consolidated:\s*(?P<ts>[^>]+?)\s*-->")
FACT_RE = re.compile(r"^\s*[-*]\s+\((?P<date>\d{4}-\d{2}-\d{2})\)\s+(?P<text>.+?)\s*$")
EMPTY_MEMORY = "# MEMORY.md\n<!-- last_consolidated: never -->\n\n## Facts\n"


@dataclass
class MemoryFiles:
    agent: str
    memory: str
    agent_path: Path
    memory_path: Path


def load_memory_files(agent_path: Path = AGENT_MD, memory_path: Path = MEMORY_MD) -> MemoryFiles:
    """Read AGENT.md and MEMORY.md (a missing MEMORY.md is created empty)."""
    if not memory_path.exists():
        memory_path.write_text(EMPTY_MEMORY)
    return MemoryFiles(agent=agent_path.read_text(), memory=memory_path.read_text(),
                       agent_path=agent_path, memory_path=memory_path)


def _strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def build_system_prompt(files: MemoryFiles) -> str:
    """System prompt = AGENT.md instructions, then MEMORY.md facts (HTML comments removed)."""
    memory = _strip_comments(files.memory).strip() or "(no stored facts yet)"
    return (
        "# Agent instructions (from AGENT.md - always follow these)\n\n"
        f"{_strip_comments(files.agent).strip()}\n\n"
        "# Long-term memory (from MEMORY.md - facts learned in earlier conversations; "
        "when two facts disagree, prefer the newer date unless a fact is marked as resolved)\n\n"
        f"{memory}\n"
    )


def read_last_consolidated(memory_text: str) -> Optional[datetime]:
    """The `<!-- last_consolidated: ISO-8601 -->` timestamp, or None if missing/unparseable."""
    m = TIMESTAMP_RE.search(memory_text)
    if not m:
        return None
    try:
        ts = datetime.fromisoformat(m.group("ts").strip())
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def count_memory_lines(memory_text: str) -> int:
    """Non-empty, non-comment lines (multi-line <!-- --> comments are skipped too)."""
    return sum(1 for line in _strip_comments(memory_text).splitlines() if line.strip())


def needs_consolidation(memory_text: str, now: Optional[datetime] = None) -> tuple[bool, list[str]]:
    """Return (required?, reasons) using the 40-line and 24-hour rules."""
    now = now or datetime.now(timezone.utc)
    reasons = []
    n = count_memory_lines(memory_text)
    if n > MAX_MEMORY_LINES:
        reasons.append(f"{n} non-empty, non-comment lines > {MAX_MEMORY_LINES}")
    last = read_last_consolidated(memory_text)
    if last is None:
        reasons.append("no recorded consolidation time")
    elif now - last > MAX_CONSOLIDATION_AGE:
        reasons.append(f"last consolidated {now - last} ago (> 24h)")
    return bool(reasons), reasons


def set_last_consolidated(memory_text: str, when: datetime) -> str:
    stamp = f"<!-- last_consolidated: {when.isoformat(timespec='seconds')} -->"
    if TIMESTAMP_RE.search(memory_text):
        return TIMESTAMP_RE.sub(stamp, memory_text, count=1)
    lines = memory_text.splitlines()
    insert_at = 1 if lines and lines[0].startswith("#") else 0
    return "\n".join(lines[:insert_at] + [stamp] + lines[insert_at:]) + "\n"


def parse_facts(memory_text: str) -> list[dict]:
    """Every dated bullet outside the 'Resolved contradictions' section, numbered F01, F02, ..."""
    facts, section = [], ""
    for lineno, line in enumerate(memory_text.splitlines(), start=1):
        if line.startswith("## "):
            section = line[3:].strip().lower()
            continue
        m = FACT_RE.match(line)
        if m and "contradiction" not in section:
            facts.append({"id": f"F{len(facts) + 1:02d}", "date": m.group("date"), "text": m.group("text"),
                          "line": lineno, "section": section})
    return facts


def append_facts(memory_path: Path, facts: list[str], on: Optional[date] = None) -> list[str]:
    """Add new dated facts under '## Facts' (used by /dream). Returns the lines written."""
    on = on or date.today()
    text = memory_path.read_text() if memory_path.exists() else EMPTY_MEMORY
    new_lines = [f"- ({on.isoformat()}) {f.strip()}" for f in facts if f.strip()]
    if not new_lines:
        return []
    lines = text.rstrip("\n").splitlines()
    if "## Facts" not in lines:
        lines += ["", "## Facts"]
    idx = lines.index("## Facts") + 1
    while idx < len(lines) and not lines[idx].startswith("## "):
        idx += 1
    while idx > 0 and not lines[idx - 1].strip():  # insert before trailing blank lines of the section
        idx -= 1
    lines[idx:idx] = new_lines
    memory_path.write_text("\n".join(lines) + "\n")
    return new_lines
