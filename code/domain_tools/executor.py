"""execute_tool: the single safe entry point to the domain tools (Part 4 / 5).

    execute_tool(name, inputs) -> JSON string of {ok, data, error}

Order of checks: known tool name -> input contract (Pydantic) -> storage call
(timeout + bounded retries) -> safety rule. Nothing escapes as an exception:
every failure becomes {"ok": false, "data": null, "error": "..."}.

Safety rule (Part 5) - small-group suppression: inspection_stats may not
return an aggregate over 1-4 inspections. Averages over so few rows
effectively disclose individual inspection results (e.g. "stats" for one
named facility is just that facility's score), which the county only
publishes per record through the normal detail view. Such calls are blocked.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from pydantic import ValidationError

from .envelope import Envelope, fail, ok
from .repository import InspectionRepository, SqlRepository
from .resilience import INTERACTIVE_POLICY, RetryPolicy, RetryResult, call_with_retry
from .tools import TOOLS, format_validation_error

MIN_AGGREGATE_GROUP = 5
SAFETY_PREFIX = "SAFETY_RULE_BLOCKED"

_default_repo: Optional[InspectionRepository] = None


def default_repo() -> InspectionRepository:
    global _default_repo
    if _default_repo is None:
        _default_repo = SqlRepository()
    return _default_repo


def check_safety_rule(name: str, data: Any) -> Optional[str]:
    """Return an error message if the result violates the safety rule."""
    if name == "inspection_stats":
        n = data.get("inspection_count", 0)
        if 0 < n < MIN_AGGREGATE_GROUP:
            return (f"{SAFETY_PREFIX}: inspection_stats matched {n} inspection(s); aggregates over "
                    f"fewer than {MIN_AGGREGATE_GROUP} inspections are suppressed because they would "
                    f"disclose individual results. Use get_inspection for a single record or widen the filter.")
    return None


def run_tool(
    name: str,
    inputs: Any,
    *,
    repo: Optional[InspectionRepository] = None,
    policy: RetryPolicy = INTERACTIVE_POLICY,
) -> tuple[Envelope, Optional[RetryResult]]:
    """execute_tool's logic, also returning the retry trace (attempts, timings)
    for the Part 3 experiments. Never raises."""
    spec = TOOLS.get(name)
    if spec is None:
        return fail(f"unknown tool '{name}'; available: {', '.join(TOOLS)}"), None
    if not isinstance(inputs, dict):
        return fail(f"invalid input for {name}: inputs must be a JSON object, got {type(inputs).__name__}"), None
    try:
        args = spec.input_model.model_validate(inputs)
    except ValidationError as exc:
        return fail(format_validation_error(name, exc)), None

    repo = repo if repo is not None else default_repo()
    trace = call_with_retry(lambda: spec.handler(repo, args), policy)
    if not trace.ok:
        if trace.error and trace.error.startswith("LookupError: "):
            return fail(trace.error.removeprefix("LookupError: ")), trace
        return fail(f"{name} failed after {trace.attempts} attempt(s): {trace.error}"), trace

    blocked = check_safety_rule(name, trace.value)
    if blocked:
        return fail(blocked), trace
    return ok(trace.value), trace


def execute_tool(
    name: str,
    inputs: Any,
    *,
    repo: Optional[InspectionRepository] = None,
    policy: RetryPolicy = INTERACTIVE_POLICY,
) -> str:
    try:
        envelope, _trace = run_tool(name, inputs, repo=repo, policy=policy)
    except Exception as exc:  # noqa: BLE001 - last line of defense, must not crash the agent
        envelope = fail(f"internal error in {name}: {type(exc).__name__}: {exc}")
    return json.dumps(envelope, default=str)
