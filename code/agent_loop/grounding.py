"""Unsupported-claim detection for agent answers (HW7 Part 3 metric).

A *claim* is an inspection code (INS-######), a facility code (FA#######) or a
number with at least two digits / a decimal point in the final answer. A claim
is *supported* when it can be traced to the run's tool observations or the
user's own question:

- codes must appear verbatim in an observation;
- numbers must match an observed number after rounding (integers within 0.5,
  decimals to the shown precision), the percentage form of an observed
  fraction (0.8375 -> 83.75 / 83.8 / 84), or the difference between two
  observed scores (for "higher by N points").

Anything else is counted as unsupported. The check is deliberately
mechanical, so it can be wrong in both directions; the Part 3 write-up
discusses where.
"""
from __future__ import annotations

import json
import re
from itertools import combinations
from typing import Any, Iterable

CODE_RE = re.compile(r"\b(?:INS-\d{6}|FA\d{7})\b")
NUMBER_RE = re.compile(r"(?<![\w.\-/])(\d+(?:\.\d+)?)(?![\w\-/])")


def _walk_numbers(value: Any, out: list[float], scores: list[float]) -> None:
    """Collect every number in a parsed JSON value (and numbers inside strings)."""
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        out.append(float(value))
    elif isinstance(value, str):
        out.extend(float(m) for m in NUMBER_RE.findall(value))
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in ("score", "avg_score", "min_score", "max_score") and isinstance(item, (int, float)):
                scores.append(float(item))
            _walk_numbers(item, out, scores)
    elif isinstance(value, list):
        for item in value:
            _walk_numbers(item, out, scores)


def observed_facts(observations: Iterable[str], user_input: str = "") -> tuple[set[str], list[float]]:
    """Codes and numbers (including derived percentages and score differences)
    available to the agent in this run."""
    codes: set[str] = set(CODE_RE.findall(user_input))
    numbers: list[float] = [float(m) for m in NUMBER_RE.findall(user_input)]
    scores: list[float] = []
    for raw in observations:
        codes.update(CODE_RE.findall(raw))
        try:
            _walk_numbers(json.loads(raw), numbers, scores)
        except json.JSONDecodeError:
            numbers.extend(float(m) for m in NUMBER_RE.findall(raw))
    derived = [n * 100 for n in numbers if 0 <= n <= 1]
    derived += [abs(a - b) for a, b in combinations(sorted(set(scores)), 2)]
    return codes, numbers + derived


def _supported(claim: str, numbers: list[float]) -> bool:
    """True if the number `claim` (as written) matches an observed number after rounding."""
    value = float(claim)
    decimals = len(claim.split(".")[1]) if "." in claim else 0
    tolerance = 0.5 if decimals == 0 else 0.5 * 10 ** -decimals + 1e-9
    return any(abs(value - n) <= tolerance for n in numbers)


def unsupported_claims(answer: str | None, observations: Iterable[str], user_input: str = "") -> list[str]:
    """Claims in `answer` that no observation (or the question) supports."""
    if not answer:
        return []
    codes, numbers = observed_facts(list(observations), user_input)
    bad = [c for c in CODE_RE.findall(answer) if c not in codes]
    stripped = CODE_RE.sub(" ", answer)
    for claim in NUMBER_RE.findall(stripped):
        if len(claim.replace(".", "")) < 2 and "." not in claim:
            continue  # single digits ("2 inspections", "step 1") are not counted as claims
        if not _supported(claim, numbers):
            bad.append(claim)
    return bad
