"""The three fixed verification tasks, their deterministic verifiers and an
independent oracle (HW7 Part 2.I / 2.III / 3).

    load_tasks()                     -> [Task A, Task B, Task C] from reports/hw07/cases/fixed_tasks.yaml
    verify(task, result)             -> Verdict: strict, trace-based assertions (used by Reflexion)
    oracle(task, result, repo)       -> dict: lenient outcome check against s7117_rel itself
    chain_complete(task, result)     -> bool: every required tool ran successfully

The verifier checks the *process* (the right tools, the right ids, chained in
the right order) and the *answer format* (numbers exactly as the tools
returned them, no unsupported claims). The oracle ignores process and format
and only asks "is the answer right?", recomputing the truth from the database
instead of from the trace. When the verifier rejects an answer the oracle
accepts, that is counted as a verifier false rejection (Part 3).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from .grounding import CODE_RE, NUMBER_RE, unsupported_claims

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TASKS_FILE = REPO_ROOT / "reports" / "hw07" / "cases" / "fixed_tasks.yaml"
COMPARISON_WORDS = re.compile(r"\b(higher|better|outscor\w*|more|greater|exceeds?|beats?)\b", re.I)
TIE_WORDS = re.compile(r"\b(same|equal|tie[sd]?|identical)\b", re.I)


@dataclass(frozen=True)
class Task:
    id: str
    kind: str
    prompt: str
    params: dict
    required_tools: tuple[str, ...]


@dataclass
class Verdict:
    passed: bool
    assertions: list[dict] = field(default_factory=list)  # {name, passed, message, evidence}

    @property
    def first_failure(self) -> Optional[dict]:
        """The first failed assertion (what a reflection should address)."""
        return next((a for a in self.assertions if not a["passed"]), None)

    def to_dict(self) -> dict:
        """JSON-serializable form for the raw files."""
        return {"passed": self.passed, "assertions": self.assertions}


def load_tasks(path: Path = TASKS_FILE) -> list[Task]:
    """The fixed cases A, B, C."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Task(t["id"], t["kind"], " ".join(t["prompt"].split()), t.get("params", {}),
                 tuple(t["required_tools"])) for t in data["tasks"]]


def load_error_recovery_prompt(path: Path = TASKS_FILE) -> str:
    """Part 2.II prompt (a nonexistent inspection code)."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))["error_recovery"]["prompt"]


# --- helpers over a run_agent() result ----------------------------------------
def _data(call: dict) -> dict:
    try:
        return json.loads(call["observation"]).get("data") or {}
    except (json.JSONDecodeError, AttributeError):
        return {}


def _calls(result: dict, tool: str) -> list[dict]:
    return [c for c in result.get("trace", []) if c["tool"] == tool and c["ok"]]


def _has_int(answer: str, value: Any) -> bool:
    """`value` appears in the answer as a standalone integer (92, not 920 or 9.2)."""
    return re.search(rf"(?<![\d.]){int(value)}(?![\d]|\.\d)", answer) is not None


def _numbers(answer: str) -> list[str]:
    return NUMBER_RE.findall(CODE_RE.sub(" ", answer))


def _evidence(call: Optional[dict]) -> dict:
    """The tool call + a short observation excerpt that an assertion is about."""
    if not call:
        return {}
    return {"tool_call": {"tool": call["tool"], "inputs": call["inputs"]},
            "observation": call["observation"][:300]}


def _assert(rows: list[dict], name: str, passed: bool, message: str, call: Optional[dict] = None) -> None:
    rows.append({"name": name, "passed": bool(passed), "message": message, "evidence": _evidence(call)})


def _observations(result: dict) -> list[str]:
    return [c["observation"] for c in result.get("trace", [])]


def chain_complete(task: Task, result: dict) -> bool:
    """Every required tool (with multiplicity) ran successfully - else a lost multi-step chain."""
    done = Counter(c["tool"] for c in result.get("trace", []) if c["ok"])
    return all(done[t] >= n for t, n in Counter(task.required_tools).items())


# --- strict verifiers -----------------------------------------------------------
def _verify_search_then_detail(task: Task, result: dict, answer: str, rows: list[dict]) -> None:
    term = task.params["term"].lower()
    searches = [c for c in _calls(result, "search_inspections")
                if term in c["inputs"].get("query", "").lower() and _data(c).get("results")]
    search = searches[0] if searches else None
    _assert(rows, "search_returned_results", search is not None,
            f"a successful search_inspections for '{term}' with >= 1 result" if search
            else f"no successful search_inspections call for '{term}' returned results", search)
    if search is None:
        return
    first = _data(search)["results"][0]["inspection_code"]
    details = [c for c in _calls(result, "get_inspection") if c["inputs"].get("inspection_code") == first]
    detail = details[0] if details else None
    _assert(rows, "detail_of_first_result", detail is not None,
            f"get_inspection called for the first result {first}" if detail
            else f"get_inspection was never called for the first search result {first}", detail or search)
    if detail is None:
        return
    score = _data(detail).get("score")
    cited = first in answer and score is not None and _has_int(answer, score)
    _assert(rows, "answer_cites_code_and_score", cited,
            f"answer cites {first} and its score {score}" if cited
            else f"answer must cite {first} and its score {score} exactly as returned", detail)


def _verify_aggregate_then_example(task: Task, result: dict, answer: str, rows: list[dict]) -> None:
    zip_code = task.params["zip_code"]
    stats_calls = [c for c in _calls(result, "inspection_stats")
                   if c["inputs"] == {"zip_code": zip_code}]
    stats = stats_calls[0] if stats_calls else None
    _assert(rows, "stats_for_zip_only", stats is not None,
            f"inspection_stats called with only zip_code={zip_code}" if stats
            else f"no successful inspection_stats call filtered only by zip_code={zip_code}", stats)
    if stats is None:
        return
    data = _data(stats)
    avg, pass_rate = data.get("avg_score"), data.get("pass_rate")
    numbers = [float(n) for n in _numbers(answer)]
    avg_ok = avg is not None and any(abs(n - round(avg, d)) < 1e-9 for n in numbers for d in (1, 2))
    _assert(rows, "answer_reports_avg_score", avg_ok,
            f"answer reports avg_score {avg} (to 1 or 2 decimals)" if avg_ok
            else f"answer must report avg_score {avg} to 1 or 2 decimals", stats)
    pr_forms = {round(pass_rate * 100, 1), round(pass_rate * 100, 2), round(pass_rate, 2), round(pass_rate, 4)} \
        if pass_rate is not None else set()
    pr_ok = any(abs(n - f) < 1e-9 for n in numbers for f in pr_forms)
    _assert(rows, "answer_reports_pass_rate", pr_ok,
            f"answer reports pass_rate {pass_rate}" if pr_ok
            else f"answer must report pass_rate {pass_rate} as a fraction or a percent with 1-2 decimals", stats)
    in_zip: dict[str, dict] = {}
    for call in _calls(result, "search_inspections") + _calls(result, "get_inspection"):
        rows_seen = _data(call).get("results") or [_data(call)]
        for r in rows_seen:
            if str(r.get("site_address", "")).endswith(f"CA {zip_code}"):
                in_zip.setdefault(r["inspection_code"], call)
    example = next((code for code in CODE_RE.findall(answer) if code in in_zip), None)
    _assert(rows, "example_from_zip", example is not None,
            f"answer cites {example}, a tool-returned inspection in {zip_code}" if example
            else f"answer cites no inspection code that a tool returned for an address in {zip_code}",
            in_zip.get(example) if example else (stats_calls[-1] if stats_calls else None))


def _verify_compare_two(task: Task, result: dict, answer: str, rows: list[dict]) -> None:
    term = task.params["term"].lower()
    searches = [c for c in _calls(result, "search_inspections")
                if term in c["inputs"].get("query", "").lower() and len(_data(c).get("results", [])) >= 2]
    search = searches[0] if searches else None
    _assert(rows, "search_returned_two", search is not None,
            f"search_inspections for '{term}' returned >= 2 results" if search
            else f"no successful search_inspections for '{term}' with >= 2 results", search)
    if search is None:
        return
    codes = [r["inspection_code"] for r in _data(search)["results"][:2]]
    details = {c["inputs"].get("inspection_code"): c for c in _calls(result, "get_inspection")}
    missing = [code for code in codes if code not in details]
    _assert(rows, "both_details_looked_up", not missing,
            f"get_inspection called for both {codes}" if not missing
            else f"get_inspection missing for {missing} (first two results are {codes})", search)
    if missing:
        return
    scores = {code: _data(details[code]).get("score") for code in codes}
    _assert(rows, "answer_names_both", all(code in answer for code in codes),
            f"answer names both {codes}" if all(code in answer for code in codes)
            else f"answer must name both inspection codes {codes}", details[codes[1]])
    both_scores = all(_has_int(answer, s) for s in scores.values())
    diff = abs(scores[codes[0]] - scores[codes[1]])
    diff_ok = TIE_WORDS.search(answer) is not None if diff == 0 else _has_int(answer, diff)
    _assert(rows, "answer_scores_and_difference", both_scores and diff_ok,
            f"answer states scores {scores} and difference {diff}" if both_scores and diff_ok
            else f"answer must state both scores {scores} and the difference {diff}", details[codes[0]])
    if diff:
        higher = max(codes, key=lambda c: scores[c])
        name = _data(details[higher]).get("facility_name", "").split(" - ")[-1]
        sentences = re.split(r"(?<=[.!?])\s+|\n+", answer)
        named = any(COMPARISON_WORDS.search(s) and (higher in s or (name and name.lower() in s.lower()))
                    for s in sentences)
        _assert(rows, "identifies_higher", named,
                f"a comparison sentence names the higher one ({higher})" if named
                else f"no comparison sentence names the higher-scoring inspection {higher}", details[higher])


_VERIFIERS = {
    "search_then_detail": _verify_search_then_detail,
    "aggregate_then_example": _verify_aggregate_then_example,
    "compare_two": _verify_compare_two,
}


def verify(task: Task, result: dict) -> Verdict:
    """Deterministic, trace-based check of one attempt."""
    answer = result.get("final_answer") or ""
    rows: list[dict] = []
    _assert(rows, "final_answer_given", result.get("stop_reason") == "final_answer" and bool(answer.strip()),
            "the loop ended with a final answer" if answer.strip()
            else f"no final answer (stop_reason={result.get('stop_reason')})")
    if rows[0]["passed"]:
        _VERIFIERS[task.kind](task, result, answer, rows)
        claims = unsupported_claims(answer, _observations(result), task.prompt)
        last = result["trace"][-1] if result.get("trace") else None
        _assert(rows, "no_unsupported_claims", not claims,
                "every code/number in the answer is in a tool observation" if not claims
                else f"claims not found in any tool observation: {claims}", last)
    return Verdict(passed=all(r["passed"] for r in rows), assertions=rows)


# --- independent oracle -----------------------------------------------------------
def oracle(task: Task, result: dict, repo: Any) -> dict:
    """Lenient outcome check: recompute the truth from the database (not from the
    trace) and accept any reasonable formatting of the right answer."""
    answer = result.get("final_answer") or ""
    numbers = [float(n) for n in _numbers(answer)]
    if task.kind == "search_then_detail":
        hits = repo.search(task.params["term"], 10, None)
        if not hits:
            return {"passed": False, "expected": None, "message": "no matching inspection in the database"}
        code = hits[0]["inspection_code"]
        score = repo.get_by_code(code)["score"]
        passed = code in answer and _has_int(answer, score)
        return {"passed": passed, "expected": {"inspection_code": code, "score": score},
                "message": "code and score present" if passed else "missing the first result's code or score"}
    if task.kind == "aggregate_then_example":
        zip_code = task.params["zip_code"]
        stats = repo.stats(None, zip_code, None)
        avg_ok = any(abs(n - stats["avg_score"]) <= 0.5 for n in numbers)
        pr = stats["pass_rate"]
        pr_ok = any(abs(n - pr * 100) <= 1.0 or abs(n - pr) <= 0.01 for n in numbers)
        example = next((c for c in CODE_RE.findall(answer)
                        if (rec := repo.get_by_code(c)) and rec["site_address"].endswith(f"CA {zip_code}")), None)
        passed = avg_ok and pr_ok and example is not None
        return {"passed": passed, "expected": {"avg_score": stats["avg_score"], "pass_rate": pr},
                "message": f"avg_ok={avg_ok} pass_rate_ok={pr_ok} example={example}"}
    if task.kind == "compare_two":
        codes = [h["inspection_code"] for h in repo.search(task.params["term"], 10, None)[:2]]
        scores = {c: repo.get_by_code(c)["score"] for c in codes}
        passed = (len(codes) == 2 and all(c in answer for c in codes)
                  and all(_has_int(answer, s) for s in scores.values()))
        return {"passed": passed, "expected": scores,
                "message": "both codes and scores present" if passed else "missing a code or a score"}
    raise ValueError(f"unknown task kind {task.kind!r}")
