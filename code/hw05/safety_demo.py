"""Part 5.I: one allowed and one blocked call through execute_tool's safety rule.

    make safety-demo                 (or: python code/hw05/safety_demo.py [--offline])

Rule (domain_tools/executor.py): inspection_stats may not aggregate over 1-4
inspections (small-group suppression). The blocked call comes back as
{ok: false, data: null, error: "SAFETY_RULE_BLOCKED: ..."} - no exception.
"""
from __future__ import annotations

import argparse
import json

from hw05_config import RAW_DIR

from domain_tools import MIN_AGGREGATE_GROUP, execute_tool
from domain_tools.fixtures import make_fixture_repo
from domain_tools.repository import SqlRepository


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    repo = make_fixture_repo() if args.offline else SqlRepository()

    # One facility appears in exactly one inspection, so its "stats" would just be its own score.
    one = json.loads(execute_tool("get_inspection", {"inspection_code": "INS-000001"}, repo=repo))
    facility_id = one["data"]["facility_name"].split(" - ")[0] if one["ok"] else "FA0206933"

    calls = [
        ("ALLOWED", "inspection_stats", {"inspector_id": 1}),
        ("BLOCKED", "inspection_stats", {"facility_query": facility_id}),
    ]
    print(f"Safety rule: inspection_stats must cover >= {MIN_AGGREGATE_GROUP} inspections\n")
    out = []
    for label, tool, inputs in calls:
        result = execute_tool(tool, inputs, repo=repo)
        print(f"[{label}] execute_tool({tool!r}, {json.dumps(inputs)})")
        print(f"  -> {result}\n")
        out.append({"label": label, "tool": tool, "inputs": inputs, "result": json.loads(result)})
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "safety_demo.json").write_text(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
