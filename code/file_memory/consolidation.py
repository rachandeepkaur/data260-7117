"""MEMORY.md consolidation (HW6 Part 4.5): merge duplicates, resolve
contradictions explicitly, never drop a fact silently, audit the result.

Pipeline:
  1. parse every dated fact bullet and number it (F01..Fnn)
  2. deterministic pass: exact duplicates (after normalising case/punctuation)
     are merged without asking the model
  3. the local model (HW1 adapter) proposes a plan as JSON:
        {"facts": [{"text", "sources": [ids]}],
         "contradictions": [{"topic", "kept": id, "superseded": [ids], "reason"}]}
  4. validation: unknown ids are ignored; any fact the plan does not account
     for is kept verbatim under "Needs review" (no silent deletion); a
     superseded fact is written to "Resolved contradictions" next to the fact
     that won, so the conflict stays visible
  5. audit: each resolution is checked against the stated rule (newest date
     wins, unless the older fact is marked "confirmed" and the newer one
     "unverified"/"guess"); disagreements are flagged as possibly incorrect.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from pydantic import BaseModel, Field

from .memory_files import count_memory_lines, parse_facts, set_last_consolidated


class PlannedFact(BaseModel):
    text: str = Field(min_length=3)
    sources: list[str] = Field(default_factory=list)


class PlannedContradiction(BaseModel):
    topic: str
    kept: str
    superseded: list[str]
    reason: str = ""


class ConsolidationPlan(BaseModel):
    facts: list[PlannedFact] = Field(default_factory=list)
    contradictions: list[PlannedContradiction] = Field(default_factory=list)


CONSOLIDATE_SYSTEM = (
    "You consolidate a long-term memory file. Input: numbered, dated facts. Output JSON only:\n"
    '{"facts": [{"text": str, "sources": [ids]}], '
    '"contradictions": [{"topic": str, "kept": id, "superseded": [ids], "reason": str}]}\n'
    "Rules:\n"
    "1. Duplicates (same meaning, even if worded differently) become ONE fact whose sources list every id.\n"
    "2. Contradictions (same subject, incompatible values) go in `contradictions`: keep the NEWEST dated fact, "
    "unless the older one says 'confirmed' and the newer one says 'unverified' or 'guess' - then keep the "
    "confirmed one. Put the kept fact's text in `facts` too (sources = the kept id), never the superseded one.\n"
    "3. Every id must appear somewhere: in some fact's sources or in a superseded list. Never invent facts.\n"
    "4. Fact text: one short sentence, keep exact names, codes, dates and numbers; drop the (date) prefix."
)

CONFLICT_CHECK_SYSTEM = (
    "You check a consolidated memory file for contradictions that are still in it. Input: numbered, dated "
    "current facts. Two facts contradict when they give incompatible values for the same thing (a different "
    "person, place, date, code or format). Restatements of the same value are NOT contradictions.\n"
    'Output JSON only: {"contradictions": [{"topic": str, "kept": id, "superseded": [ids], "reason": str}]}\n'
    "Keep the NEWEST dated fact, unless the older one says 'confirmed' and the newer one 'unverified' or "
    "'guess'. Return {\"contradictions\": []} if none remain."
)

Planner = Callable[[str, str], str]  # (system, user) -> raw JSON text


class ConflictCheck(BaseModel):
    contradictions: list[PlannedContradiction] = Field(default_factory=list)


def _norm(text: str) -> str:
    text = re.sub(r"\b(confirmed|unverified|guess)\b", "", text.lower())
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _ollama_planner(system: str, user: str) -> str:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
    from model_client import ModelClient

    return ModelClient(temperature=0.0).complete(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format="json", max_tokens=3000)


@dataclass
class ConsolidationResult:
    text: str
    lines_before: int
    lines_after: int
    facts_before: int
    facts_after: int
    exact_duplicates_merged: int
    contradictions: list[dict]
    needs_review: list[dict]
    audit: list[dict] = field(default_factory=list)
    plan_raw: str = ""

    def summary(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k not in ("text", "plan_raw")}


def audit_resolution(kept: dict, superseded: list[dict]) -> dict:
    """Check one resolution against the stated rule; returns a verdict for the report."""
    def marked(f: dict, *words: str) -> bool:
        return any(re.search(rf"\b{w}\b", f["text"], re.I) for w in words)

    issues = []
    for s in superseded:
        override = marked(s, "unverified", "guess") and marked(kept, "confirmed")
        if s["date"] > kept["date"] and not override:
            issues.append(f"kept {kept['id']} ({kept['date']}) over NEWER {s['id']} ({s['date']})")
        if marked(s, "confirmed") and marked(kept, "unverified", "guess"):
            issues.append(f"kept unverified {kept['id']} over confirmed {s['id']}")
    return {"kept": kept["id"], "superseded": [s["id"] for s in superseded],
            "verdict": "possibly_incorrect" if issues else "consistent_with_rule", "issues": issues}


def consolidate(memory_text: str, planner: Optional[Planner] = None,
                now: Optional[datetime] = None) -> ConsolidationResult:
    planner = planner or _ollama_planner
    now = now or datetime.now(timezone.utc)
    facts = parse_facts(memory_text)
    by_id = {f["id"]: f for f in facts}

    # 2. exact duplicates: keep the newest copy as representative
    groups: dict[str, list[dict]] = {}
    for f in facts:
        groups.setdefault(_norm(f["text"]), []).append(f)
    reps, alias = [], {}
    for members in groups.values():
        rep = max(members, key=lambda f: f["date"])
        reps.append(rep)
        for m in members:
            alias[m["id"]] = rep["id"]
    exact_merged = len(facts) - len(reps)

    # 3. model plan over the de-duplicated list
    listing = "\n".join(f"{f['id']} ({f['date']}) {f['text']}" for f in sorted(reps, key=lambda f: f["id"]))
    raw = planner(CONSOLIDATE_SYSTEM, f"Facts:\n{listing}")
    try:
        plan = ConsolidationPlan.model_validate(json.loads(raw))
    except (ValueError, json.JSONDecodeError):
        plan = ConsolidationPlan()

    rep_ids = {r["id"] for r in reps}
    members_of = {rid: [f for f in facts if alias[f["id"]] == rid] for rid in rep_ids}

    # 4. validate contradictions first (they decide which ids may not appear as current facts)
    contradictions, superseded_ids = [], set()
    for c in plan.contradictions:
        kept = alias.get(c.kept)
        sup = [alias[s] for s in c.superseded if s in alias and alias[s] != kept]
        if kept not in rep_ids or not sup:
            continue
        sup = sorted(set(sup) - superseded_ids)
        superseded_ids.update(sup)
        contradictions.append({"topic": c.topic, "kept": by_id[kept], "superseded": [by_id[s] for s in sup],
                               "reason": c.reason, "audit": audit_resolution(by_id[kept], [by_id[s] for s in sup])})

    out_facts, covered = [], set(superseded_ids)
    for pf in plan.facts:
        src = sorted({alias[s] for s in pf.sources if s in alias} - superseded_ids)
        if not src:
            continue
        covered.update(src)
        date = max(m["date"] for s in src for m in members_of[s])
        all_ids = sorted({m["id"] for s in src for m in members_of[s]})
        out_facts.append({"date": date, "text": pf.text.strip().rstrip("."), "sources": all_ids})
    # a kept contradiction fact the model forgot to list as a fact is still current
    for c in contradictions:
        if c["kept"]["id"] not in covered:
            covered.add(c["kept"]["id"])
            out_facts.append({"date": c["kept"]["date"], "text": c["kept"]["text"].rstrip("."),
                              "sources": [m["id"] for m in members_of[c["kept"]["id"]]]})
    needs_review = [r for r in sorted(reps, key=lambda f: f["id"]) if r["id"] not in covered]

    # 4b. second pass: the first plan can leave both sides of a contradiction under Facts
    # (seen in run 1: 3 of 5 planted contradictions). Ask the model to check the result itself.
    numbered = {f"C{i + 1:02d}": f for i, f in enumerate(out_facts)}
    check_raw = planner(CONFLICT_CHECK_SYSTEM, "Facts:\n" + "\n".join(
        f"{cid} ({f['date']}) {f['text']}" for cid, f in numbered.items()))
    try:
        check = ConflictCheck.model_validate(json.loads(check_raw))
    except (ValueError, json.JSONDecodeError):
        check = ConflictCheck()
    removed: set[str] = set()
    for c in check.contradictions:
        sup = [s for s in c.superseded if s in numbered and s != c.kept and s not in removed]
        if c.kept not in numbered or c.kept in removed or not sup:
            continue
        as_fact = lambda cid: {"id": "+".join(numbered[cid]["sources"]), "date": numbered[cid]["date"],  # noqa: E731
                               "text": numbered[cid]["text"]}
        kept_f, sup_f = as_fact(c.kept), [as_fact(s) for s in sup]
        removed.update(sup)
        contradictions.append({"topic": c.topic, "kept": kept_f, "superseded": sup_f, "reason": c.reason,
                               "found_by": "conflict check", "audit": audit_resolution(kept_f, sup_f)})
    out_facts = [f for cid, f in numbered.items() if cid not in removed]
    raw = raw + "\n\n--- conflict check ---\n" + check_raw

    # 5. render
    lines = ["# MEMORY.md", "<!-- last_consolidated: placeholder -->",
             "<!-- Durable facts. Consolidated by code/file_memory/consolidation.py; [Fxx] = source lines "
             "of the version before consolidation. -->", "", "## Facts"]
    lines += [f"- ({f['date']}) {f['text']}. [{'+'.join(f['sources'])}]"
              for f in sorted(out_facts, key=lambda f: f["date"])]
    if contradictions:
        lines += ["", "## Resolved contradictions"]
        for c in contradictions:
            k = c["kept"]
            old = "; ".join(f"\"{s['text']}\" ({s['date']}, {s['id']})" for s in c["superseded"])
            flag = " AUDIT: possibly incorrect" if c["audit"]["verdict"] != "consistent_with_rule" else ""
            lines.append(f"- {c['topic']}: kept \"{k['text']}\" ({k['date']}, {k['id']}) over {old}.{flag}")
    if needs_review:
        lines += ["", "## Needs review (not resolved by consolidation, kept verbatim)"]
        lines += [f"- ({f['date']}) {f['text']} [{f['id']}]" for f in needs_review]
    text = set_last_consolidated("\n".join(lines) + "\n", now)

    return ConsolidationResult(
        text=text, lines_before=count_memory_lines(memory_text), lines_after=count_memory_lines(text),
        facts_before=len(facts), facts_after=len(out_facts) + len(needs_review),
        exact_duplicates_merged=exact_merged,
        contradictions=[{"topic": c["topic"], "kept": c["kept"]["id"], "superseded": [s["id"] for s in c["superseded"]],
                         "reason": c["reason"], "found_by": c.get("found_by", "plan"), "audit": c["audit"]}
                        for c in contradictions],
        needs_review=[{"id": f["id"], "text": f["text"]} for f in needs_review],
        audit=[c["audit"] for c in contradictions], plan_raw=raw)
