"""HW5 Part 4 / 5 offline test runner for execute_tool and run_agent.

    make test-hw05        (or: python code/tests/test_hw05_tools.py)

Plain asserts, PASS/FAIL per test and an X/Y summary. Fully offline and
repeatable: every test builds a fresh in-memory fixture repository
(dependency injection via `repo=`), the agent uses MockModel, and nothing
touches MySQL, Ollama, TheMealDB or an API key.

The invalid inputs are the same rejected calls captured in MCP Inspector for
Part 2B / documented in Part 3:
    search_inspections  {"query": "golden", "limit": 500}
    get_inspection      {"inspection_code": "12345"}
    inspection_stats    {"zip_code": "95A18"}
"""
from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # code/

from domain_tools import SAFETY_PREFIX, execute_tool  # noqa: E402
from domain_tools.agent import MockModel, run_agent  # noqa: E402
from domain_tools.fixtures import make_fixture_repo  # noqa: E402
from domain_tools.repository import FaultyRepository  # noqa: E402
from domain_tools.resilience import RetryPolicy, ScriptedFaults  # noqa: E402

FAST = RetryPolicy(max_attempts=3, timeout_s=2.0, base_delay_s=0.0)  # no real sleeping in tests


def call(name: str, inputs, repo=None, policy: RetryPolicy = FAST) -> dict:
    raw = execute_tool(name, inputs, repo=repo or make_fixture_repo(), policy=policy)
    assert isinstance(raw, str), "execute_tool must return a JSON string"
    env = json.loads(raw)
    assert set(env) == {"ok", "data", "error"}, f"envelope keys were {sorted(env)}"
    return env


# --- search_inspections -------------------------------------------------------
def test_search_valid():
    env = call("search_inspections", {"query": "golden", "limit": 5})
    assert env["ok"] is True and env["error"] is None
    codes = [r["inspection_code"] for r in env["data"]["results"]]
    assert codes == ["INS-000002", "INS-000004", "INS-000007"], codes


def test_search_rejects_limit_out_of_range():
    env = call("search_inspections", {"query": "golden", "limit": 500})
    assert env["ok"] is False and env["data"] is None
    assert "limit" in env["error"]


def test_search_rejects_unknown_field():
    env = call("search_inspections", {"query": "golden", "sort": "score"})
    assert env["ok"] is False and "sort" in env["error"]


# --- get_inspection -----------------------------------------------------------
def test_detail_valid():
    env = call("get_inspection", {"inspection_code": "INS-000002"})
    assert env["ok"] is True
    assert env["data"]["facility_name"] == "FA0311021 - GOLDEN WOK"
    assert env["data"]["inspector_name"] == "Maria Nguyen"
    assert len(env["data"]["violations"]) == 2


def test_detail_rejects_malformed_code():
    env = call("get_inspection", {"inspection_code": "12345"})
    assert env["ok"] is False and env["data"] is None
    assert "inspection_code" in env["error"]


def test_detail_not_found_is_clean_error():
    env = call("get_inspection", {"inspection_code": "INS-999999"})
    assert env["ok"] is False and "not found" in env["error"]


# --- inspection_stats ---------------------------------------------------------
def test_stats_valid():
    env = call("inspection_stats", {"inspector_id": 1})
    assert env["ok"] is True
    d = env["data"]
    assert d["inspection_count"] == 6 and d["avg_score"] == 86.0 and d["min_score"] == 64


def test_stats_rejects_bad_zip():
    env = call("inspection_stats", {"zip_code": "95A18"})
    assert env["ok"] is False and "zip_code" in env["error"]


# --- execute_tool robustness ----------------------------------------------------
def test_unknown_tool_and_non_object_inputs():
    env = call("delete_inspection", {"inspection_code": "INS-000001"})
    assert env["ok"] is False and "unknown tool" in env["error"]
    env = call("search_inspections", ["golden"])
    assert env["ok"] is False and "JSON object" in env["error"]


def test_retry_recovers_after_transient_failure():
    repo = FaultyRepository(make_fixture_repo(), ScriptedFaults([True, False]))
    env = call("search_inspections", {"query": "golden"}, repo=repo)
    assert env["ok"] is True and repo.injector.decisions == [True, False]


def test_retry_exhausted_returns_clean_error():
    repo = FaultyRepository(make_fixture_repo(), ScriptedFaults([True, True, True]))
    env = call("search_inspections", {"query": "golden"}, repo=repo)
    assert env["ok"] is False and "after 3 attempt(s)" in env["error"]


# --- Part 5 additions -----------------------------------------------------------
def test_safety_rule_blocks_small_group_aggregate():
    env = call("inspection_stats", {"facility_query": "YUMMY"})  # matches exactly 1 inspection
    assert env == {"ok": False, "data": None, "error": env["error"]}
    assert env["error"].startswith(SAFETY_PREFIX)
    allowed = call("inspection_stats", {"facility_query": "FA0"})  # matches 7 -> allowed
    assert allowed["ok"] is True


def test_run_agent_stops_at_max_steps_with_mock_model():
    # The mock never answers - it keeps calling a tool - so only the ceiling can stop it.
    mock = MockModel([{"action": "tool", "tool": "search_inspections", "inputs": {"query": "golden"}}])
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "agent_runs.jsonl"
        result = run_agent("loop forever", model=mock, max_steps=3, repo=make_fixture_repo(), log_path=log_path)
        lines = [json.loads(l) for l in log_path.read_text().splitlines()]
    assert result["stop_reason"] == "max_steps"
    assert result["steps"] == 3 and result["tool_calls"] == 3 and mock.calls == 3
    assert lines[-1]["event"] == "stop" and lines[-1]["stop_reason"] == "max_steps"


def test_run_agent_normal_completion_with_mock_model():
    mock = MockModel([
        {"action": "tool", "tool": "get_inspection", "inputs": {"inspection_code": "INS-000002"}},
        {"action": "final", "answer": "GOLDEN WOK scored 64 (failed)."},
    ])
    result = run_agent("How did INS-000002 do?", model=mock, repo=make_fixture_repo(), log_path=None)
    assert result["stop_reason"] == "final_answer" and result["steps"] == 2 and result["tool_calls"] == 1


TESTS = [obj for name, obj in list(globals().items()) if name.startswith("test_") and callable(obj)]


def main() -> int:
    print("HW5 offline tool tests - Rachandeep Kaur (SID4 7117)")
    print("=" * 64)
    passed = 0
    for test in TESTS:
        try:
            test()
        except Exception:  # noqa: BLE001 - AssertionError or a crash both count as FAIL
            print(f"FAIL  {test.__name__}")
            print("      " + traceback.format_exc().strip().splitlines()[-1])
        else:
            passed += 1
            print(f"PASS  {test.__name__}")
    print("=" * 64)
    print(f"{passed}/{len(TESTS)} tests passed")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())
