"""MCP server "s7117-inspections": three tools over the s7117_rel MySQL data (HW5 Part 2B).

    mcp dev code/mcp_servers/inspections_server.py
    python code/mcp_servers/inspections_server.py              # plain STDIO server
    S7117_OFFLINE=1 python code/mcp_servers/inspections_server.py   # in-memory fixture data

    search_inspections(query, limit=10, min_score=None)        search
    get_inspection(inspection_code)                            detail lookup
    inspection_stats(inspector_id=None, zip_code=None, facility_query=None)   aggregate

Every tool returns the same envelope {ok, data, error} (error is null on
success). The tools are thin adapters over domain_tools.execute_tool, so input
validation, timeouts/retries and the safety rule are identical here, in the
offline tests and in the agent. The MCP signatures carry only the JSON types
(so Inspector renders proper fields); ranges and formats (limit 1-25,
INS-######, 5-digit ZIP) are checked by our own contract, so a type-correct
but invalid value comes back as an envelope error rather than an MCP error.
Logs go to stderr only.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # code/ -> domain_tools

from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

from domain_tools import execute_tool  # noqa: E402
from domain_tools.envelope import Envelope  # noqa: E402

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(asctime)s %(levelname)s s7117-inspections: %(message)s")
log = logging.getLogger("s7117-inspections")

REPO = None
if os.getenv("S7117_OFFLINE") == "1":
    from domain_tools.fixtures import make_fixture_repo  # noqa: E402

    REPO = make_fixture_repo()
    log.info("offline mode: using in-memory fixture data")

mcp = FastMCP("s7117-inspections")

# All three tools only read s7117_rel.
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


def _call(name: str, inputs: dict[str, Any]) -> Envelope:
    # Drop parameters the client left empty (Inspector may send "" for a
    # blank optional field), so "not given" stays distinguishable.
    inputs = {k: v for k, v in inputs.items() if v is not None and v != ""}
    log.info("call %s %s", name, inputs)
    envelope = json.loads(execute_tool(name, inputs, repo=REPO))
    log.info("result %s ok=%s error=%s", name, envelope["ok"], envelope["error"])
    return envelope


@mcp.tool(annotations=READ_ONLY)
def search_inspections(query: str, limit: int = 10, min_score: Optional[int] = None) -> Envelope:
    """Search restaurant inspections by facility name, address text, or exact
    inspection code. query: 2-100 chars; limit: 1-25 (default 10); min_score: 0-100."""
    return _call("search_inspections", {"query": query, "limit": limit, "min_score": min_score})


@mcp.tool(annotations=READ_ONLY)
def get_inspection(inspection_code: str) -> Envelope:
    """Full detail for one inspection (facility, score, inspector, violations).
    inspection_code must look like INS-000042."""
    return _call("get_inspection", {"inspection_code": inspection_code})


@mcp.tool(annotations=READ_ONLY)
def inspection_stats(
    inspector_id: Optional[int] = None, zip_code: Optional[str] = None, facility_query: Optional[str] = None
) -> Envelope:
    """Aggregate over inspections: count, avg/min/max score, pass rate (score >= 70)
    and violation count. Optional filters: inspector_id (int >= 1), zip_code
    (5 digits), facility_query (2-100 chars). Aggregates over 1-4 inspections
    are blocked by the small-group safety rule."""
    return _call("inspection_stats",
                 {"inspector_id": inspector_id, "zip_code": zip_code, "facility_query": facility_query})


if __name__ == "__main__":
    log.info("starting s7117-inspections MCP server over STDIO")
    mcp.run()
