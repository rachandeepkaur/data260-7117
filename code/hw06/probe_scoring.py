"""Score a probe reply 1-5 with the rubric in reports/hw06/memory_probes.yaml."""
from __future__ import annotations

import re

import yaml

from hw06_config import PROBES_FILE


def load_probes(path=PROBES_FILE) -> dict:
    return yaml.safe_load(path.read_text())


def _hits(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, flags=re.I) for p in patterns)


def score_reply(probe: dict, reply: str) -> dict:
    met = [c["name"] for c in probe["criteria"] if _hits(c["any"], reply)]
    f = len(met) / len(probe["criteria"])
    score = 5 if f == 1 else 4 if f >= 2 / 3 else 3 if f >= 0.5 else 2 if f > 0 else 1
    stale = probe.get("stale")
    stale_hit = bool(stale) and _hits(stale["any"], reply)
    explained = bool(stale) and _hits([re.escape(w) for w in stale.get("change_words", [])], reply)
    if stale_hit and not explained:
        score = 1 if f == 0 else max(1, min(score - 1, 3))
    return {"score": score, "criteria_met": met, "criteria_total": len(probe["criteria"]),
            "stale_value_mentioned": stale_hit, "change_explained": explained}
