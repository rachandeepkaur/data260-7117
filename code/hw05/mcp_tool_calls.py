"""Record the MCP tool test calls (Part 2A + 2B) as machine-readable output.

    make mcp-calls                   (or: python code/hw05/mcp_tool_calls.py)

Starts each MCP server over STDIO exactly like MCP Inspector does, calls every
tool with the same inputs used in the Inspector screenshots (valid and the
intentionally invalid Part 2B calls), and saves the raw responses to
reports/hw05/raw/mcp_inspector_outputs.json.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from hw05_config import MCP_SERVERS_DIR, RAW_DIR

MEALS_CALLS = [
    ("search_meals_by_name", {"query": "Arrabiata", "limit": 5}),
    ("search_meals_by_name", {"query": "zzzqqq"}),  # "meals": null -> empty result + message
    ("meals_by_ingredient", {"ingredient": "chicken", "limit": 12}),
    ("meal_details", {"id": "52771"}),
    ("random_meal", {}),
]

# (label, tool, inputs) - the "invalid" ones are the Part 2B rejected calls reused in Part 3.
DOMAIN_CALLS = [
    ("valid", "search_inspections", {"query": "golden", "limit": 5, "min_score": 90}),
    ("invalid", "search_inspections", {"query": "golden", "limit": 500}),
    ("valid", "get_inspection", {"inspection_code": "INS-000038"}),
    ("invalid", "get_inspection", {"inspection_code": "12345"}),
    ("valid", "inspection_stats", {"inspector_id": 3}),
    ("invalid", "inspection_stats", {"zip_code": "95A18"}),
]


async def call_tools(script: str, calls: list[tuple[str, dict]], env: dict | None = None) -> dict:
    params = StdioServerParameters(command=sys.executable, args=[script], env={**os.environ, **(env or {})})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            tools = [t.name for t in (await session.list_tools()).tools]
            results = []
            for name, args in calls:
                res = await session.call_tool(name, args)
                text = res.content[0].text if res.content else ""
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = text
                results.append({"tool": name, "input": args, "is_error": res.isError, "output": parsed})
            return {"server": init.serverInfo.name, "tools": tools, "calls": results}


def main() -> None:
    meals = asyncio.run(call_tools(str(MCP_SERVERS_DIR / "meals_server.py"), MEALS_CALLS))
    domain = asyncio.run(call_tools(str(MCP_SERVERS_DIR / "inspections_server.py"),
                                    [(t, i) for _, t, i in DOMAIN_CALLS]))
    for (label, _, _), call in zip(DOMAIN_CALLS, domain["calls"]):
        call["label"] = label

    for server in (meals, domain):
        print(f"== server {server['server']}: tools {server['tools']}")
        for c in server["calls"]:
            out = json.dumps(c["output"])
            print(f"   {c.get('label', ''):7} {c['tool']}({json.dumps(c['input'])}) isError={c['is_error']}")
            print(f"           -> {out[:240]}{'...' if len(out) > 240 else ''}")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / "mcp_inspector_outputs.json"
    path.write_text(json.dumps({"recorded_at": datetime.now(timezone.utc).isoformat(),
                                "servers": [meals, domain]}, indent=2))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
