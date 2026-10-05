"""The one response envelope used by every domain tool (HW5 Part 2B).

    {"ok": true,  "data": <result>, "error": null}       success
    {"ok": false, "data": null,     "error": "<message>"} failure

The domain MCP server returns it, and execute_tool (Part 4) returns it as a
JSON string - both build it only through these two helpers.
"""
from __future__ import annotations

from typing import Any, TypedDict


class Envelope(TypedDict):
    ok: bool
    data: dict[str, Any] | None  # every tool's result is a JSON object
    error: str | None


def ok(data: dict[str, Any]) -> Envelope:
    return {"ok": True, "data": data, "error": None}


def fail(error: str) -> Envelope:
    return {"ok": False, "data": None, "error": error}
