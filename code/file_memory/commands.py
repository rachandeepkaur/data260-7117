"""Chat session over file-based memory + the /memory /compact /dream /help commands.

The session keeps the in-process conversation (`history`); the durable state
is only AGENT.md + MEMORY.md, re-read before every turn so an edit to either
file takes effect immediately.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .consolidation import Planner, consolidate
from .memory_files import (
    AGENT_MD,
    MEMORY_MD,
    append_facts,
    build_system_prompt,
    count_memory_lines,
    load_memory_files,
    needs_consolidation,
    parse_facts,
    read_last_consolidated,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
from model_client import ModelClient, ModelClientError  # noqa: E402

HELP_TEXT = """Commands:
  /memory   show AGENT.md + MEMORY.md as loaded into the system prompt, with line count,
            last-consolidated time and whether consolidation is due
  /compact  consolidate MEMORY.md (merge duplicates, resolve contradictions) and compact the
            conversation into a summary; reports the counts before and after
  /dream    find durable long-term facts in the recent conversation and add them to MEMORY.md
  /help     this help
  /exit     quit (Ctrl-D also works)
Anything else is sent to the model with AGENT.md + MEMORY.md in the system prompt."""

DREAM_SYSTEM = (
    "From the conversation below, list durable long-term facts worth remembering in future "
    "conversations (identity, role, facilities, deadlines, preferences, decisions). Skip general "
    "knowledge and anything already in the existing memory. Each fact is one self-contained sentence. "
    "Return JSON only: {\"facts\": [str, ...]} with at most 5 facts."
)

COMPACT_SYSTEM = (
    "Summarize this conversation in at most 6 bullets starting with '- ' so it can continue without "
    "the full transcript. Keep names, codes, dates and decisions exactly."
)

LLM = Callable[[list[dict], Optional[str]], str]  # (messages, response_format) -> text


def _ollama_llm(messages: list[dict], response_format: Optional[str] = None) -> str:
    return ModelClient().complete(messages, response_format=response_format, max_tokens=800)


@dataclass
class FileMemorySession:
    agent_path: Path = AGENT_MD
    memory_path: Path = MEMORY_MD
    llm: LLM = _ollama_llm
    planner: Optional[Planner] = None
    history: list[dict] = field(default_factory=list)  # user/assistant turns only
    last_summary: Optional[dict] = None                 # result of the latest consolidation
    last_plan_raw: str = ""

    # ----------------------------------------------------------------- chat
    def system_prompt(self) -> str:
        return build_system_prompt(load_memory_files(self.agent_path, self.memory_path))

    def chat(self, text: str) -> str:
        self.history.append({"role": "user", "content": text})
        try:
            reply = self.llm([{"role": "system", "content": self.system_prompt()}, *self.history], None)
        except ModelClientError:
            self.history.pop()
            raise
        self.history.append({"role": "assistant", "content": reply})
        return reply

    def handle(self, line: str) -> Optional[str]:
        """Run a /command and return its output, or None if `line` is not a command."""
        cmd = line.strip().split()[0].lower() if line.strip().startswith("/") else ""
        return {"/memory": self.cmd_memory, "/compact": self.cmd_compact, "/dream": self.cmd_dream,
                "/help": lambda: HELP_TEXT}.get(cmd, lambda: None)()

    # ------------------------------------------------------------- commands
    def consolidation_status(self) -> str:
        text = self.memory_path.read_text()
        due, reasons = needs_consolidation(text)
        last = read_last_consolidated(text)
        return (f"MEMORY.md: {count_memory_lines(text)} non-empty non-comment lines, {len(parse_facts(text))} facts; "
                f"last consolidated: {last.isoformat() if last else 'never'}; "
                f"consolidation {'REQUIRED (' + '; '.join(reasons) + ')' if due else 'not required'}")

    def cmd_memory(self) -> str:
        files = load_memory_files(self.agent_path, self.memory_path)
        return (f"----- {self.agent_path.name} ({len(files.agent.splitlines())} lines) -----\n{files.agent.strip()}\n\n"
                f"----- {self.memory_path.name} -----\n{files.memory.strip()}\n\n{self.consolidation_status()}")

    def consolidate_memory(self) -> dict:
        before_text = self.memory_path.read_text()
        result = consolidate(before_text, planner=self.planner)
        self.memory_path.write_text(result.text)
        self.last_summary, self.last_plan_raw = result.summary(), result.plan_raw
        return self.last_summary

    def cmd_compact(self) -> str:
        s = self.consolidate_memory()
        msgs_before = len(self.history)
        if self.history:
            transcript = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in self.history)
            summary = self.llm([{"role": "system", "content": COMPACT_SYSTEM},
                                {"role": "user", "content": transcript}], None).strip()
            self.history = [{"role": "user", "content": f"(Summary of the earlier conversation)\n{summary}"},
                            {"role": "assistant", "content": "Understood - continuing from that summary."}]
        out = [
            "/compact done",
            f"  MEMORY.md lines (non-empty, non-comment): {s['lines_before']} -> {s['lines_after']}",
            f"  MEMORY.md facts:                          {s['facts_before']} -> {s['facts_after']}",
            f"  conversation messages:                    {msgs_before} -> {len(self.history)}",
            f"  exact duplicates merged: {s['exact_duplicates_merged']}; contradictions resolved: "
            f"{len(s['contradictions'])}; needs review: {len(s['needs_review'])}",
        ]
        for c in s["contradictions"]:
            out.append(f"  - {c['topic']}: kept {c['kept']} over {', '.join(c['superseded'])} "
                       f"[{c['audit']['verdict']}]")
        return "\n".join(out)

    def cmd_dream(self) -> str:
        recent = self.history[-20:]
        if not recent:
            return "/dream: no conversation yet - nothing to learn."
        transcript = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in recent)
        raw = self.llm([{"role": "system", "content": DREAM_SYSTEM},
                        {"role": "user", "content": f"Existing memory:\n{self.memory_path.read_text()}\n\n"
                                                    f"Conversation:\n{transcript}"}], "json")
        try:
            facts = [str(f) for f in json.loads(raw).get("facts", [])][:5]
        except (ValueError, AttributeError):
            facts = []
        known = {f["text"].lower().rstrip(".") for f in parse_facts(self.memory_path.read_text())}
        facts = [f for f in facts if f.lower().rstrip(".") not in known]
        written = append_facts(self.memory_path, facts, on=date.today())
        out = [f"/dream added {len(written)} fact(s) to {self.memory_path.name}:", *[f"  {w}" for w in written]]
        due, reasons = needs_consolidation(self.memory_path.read_text(), datetime.now(timezone.utc))
        if due and any(">" in r and "lines" in r for r in reasons):
            out.append(f"  consolidation now required ({'; '.join(reasons)}) - running it:")
            s = self.consolidate_memory()
            out.append(f"  MEMORY.md lines {s['lines_before']} -> {s['lines_after']}")
        return "\n".join(out)
