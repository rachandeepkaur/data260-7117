"""Toolsets the hand-written agent loop can drive (HW7 Part 2 / Part 6).

A Toolset bundles, per tool: a description, a Pydantic input model (its JSON
Schema is what the model sees) and a runner that returns the tool's JSON
result string. The loop never calls a tool directly - it asks the toolset to
validate the call first, so an unknown tool name or malformed / schema-invalid
arguments are classified *before* anything executes.

    DOMAIN toolset   the three HW5 domain tools, executed through execute_tool
    file toolset     built by file_tools.make_file_toolset(sandbox) (Part 6)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Optional

from pydantic import BaseModel, ValidationError

UNKNOWN_TOOL = "unknown_tool"
MALFORMED_ARGUMENTS = "malformed_arguments"


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    input_model: type[BaseModel]
    run: Callable[[BaseModel], str]  # validated args -> JSON result string


@dataclass(frozen=True)
class CallCheck:
    """Outcome of validating one model tool call."""

    ok: bool
    args: Optional[BaseModel] = None
    kind: Optional[str] = None  # UNKNOWN_TOOL | MALFORMED_ARGUMENTS
    problem: str = ""


class Toolset:
    """A fixed, named set of tools. Built once per run and never changed by
    model output or reflections (HW7 Part 3 isolation rule)."""

    def __init__(self, name: str, tools: list[ToolDef]):
        self.name = name
        self._tools = {t.name: t for t in tools}

    @property
    def names(self) -> list[str]:
        """Tool names in registration order."""
        return list(self._tools)

    def schemas(self) -> list[dict]:
        """OpenAI-style function schemas passed to the model with every turn."""
        return [{"type": "function", "function": {
            "name": t.name, "description": t.description, "parameters": t.input_model.model_json_schema()}}
            for t in self._tools.values()]

    def schema_of(self, name: str) -> dict:
        """JSON Schema of one tool's input (used in repair prompts)."""
        return self._tools[name].input_model.model_json_schema()

    def check(self, name: Any, arguments: Any) -> CallCheck:
        """Classify a tool call: known tool name, JSON-object arguments, schema-valid."""
        if name not in self._tools:
            return CallCheck(False, kind=UNKNOWN_TOOL,
                             problem=f"unknown tool '{name}'. Available tools: {', '.join(self._tools)}")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError as exc:
                return CallCheck(False, kind=MALFORMED_ARGUMENTS,
                                 problem=f"arguments for {name} are not valid JSON ({exc.msg})")
        if not isinstance(arguments, dict):
            return CallCheck(False, kind=MALFORMED_ARGUMENTS,
                             problem=f"arguments for {name} must be a JSON object, got {type(arguments).__name__}")
        try:
            return CallCheck(True, args=self._tools[name].input_model.model_validate(arguments))
        except ValidationError as exc:
            details = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'input'}: {e['msg']}" for e in exc.errors())
            return CallCheck(False, kind=MALFORMED_ARGUMENTS,
                             problem=f"arguments for {name} failed schema validation: {details}")

    def run(self, name: str, args: BaseModel) -> str:
        """Execute an already-validated call; returns the tool's JSON string."""
        return self._tools[name].run(args)


def make_domain_toolset(repo: Any = None) -> Toolset:
    """The three HW5 domain tools; every call goes through execute_tool (which
    re-validates, retries transient errors and applies the HW5 safety rule)."""
    from domain_tools import execute_tool
    from domain_tools.tools import TOOLS

    def runner(tool_name: str) -> Callable[[BaseModel], str]:
        return lambda args: execute_tool(tool_name, args.model_dump(exclude_none=True), repo=repo)

    return Toolset("domain", [ToolDef(name, spec.description, spec.input_model, runner(name))
                              for name, spec in TOOLS.items()])
