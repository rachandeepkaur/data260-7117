"""run_agent: a bounded tool-using agent loop over the domain tools (Part 5).

Each step the model replies with ONE JSON object, either
    {"action": "tool", "tool": "<name>", "inputs": {...}}
or  {"action": "final", "answer": "<text>"}.
Tool calls go through execute_tool only. The harness stops on the first of:
    final_answer   the model gave a final answer          (normal completion)
    safety_block   execute_tool blocked a call (safety rule)
    max_steps      the turn counter reached max_steps     (ceiling)
    model_error    the local model could not be reached
Every step, tool call, input, result and the stop reason is appended to
agent_runs.jsonl.

The model is injected: OllamaModel (local qwen3:8b via src/model_client.py)
for real runs, MockModel (scripted replies) for offline tests.
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence

from .executor import SAFETY_PREFIX, execute_tool
from .repository import InspectionRepository
from .tools import TOOL_SCHEMAS, TOOLS

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_LOG_PATH = REPO_ROOT / "reports" / "hw05" / "raw" / "agent_runs.jsonl"
DEFAULT_MAX_STEPS = 6
MAX_RESULT_CHARS = 3000  # keep tool results from flooding the model's context


class ChatModel(Protocol):
    name: str

    def complete(self, messages: Sequence[dict], **kwargs: Any) -> str: ...


class OllamaModel:
    def __init__(self, model: Optional[str] = None, temperature: float = 0.0):
        sys.path.insert(0, str(REPO_ROOT / "src"))
        from model_client import MODEL_ID, ModelClient

        self.name = model or MODEL_ID
        self._client = ModelClient(model=self.name, temperature=temperature)

    def complete(self, messages: Sequence[dict], **kwargs: Any) -> str:
        return self._client.complete(messages, response_format="json", max_tokens=1024)


class MockModel:
    """Returns scripted replies in order; repeats the last one when exhausted."""

    name = "mock"

    def __init__(self, replies: Sequence[str | dict]):
        self.replies = [r if isinstance(r, str) else json.dumps(r) for r in replies]
        self.calls = 0

    def complete(self, messages: Sequence[dict], **kwargs: Any) -> str:
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return reply


def system_prompt() -> str:
    tool_lines = "\n".join(
        f"- {name}: {spec.description}\n  input JSON schema: {json.dumps(TOOL_SCHEMAS[name])}"
        for name, spec in TOOLS.items()
    )
    return (
        "You answer questions about San Jose restaurant health inspections (database s7117_rel) "
        "using these tools:\n"
        f"{tool_lines}\n\n"
        "Reply with exactly ONE JSON object and nothing else:\n"
        '  {"action": "tool", "tool": "<tool name>", "inputs": {...}}   to call a tool, or\n'
        '  {"action": "final", "answer": "<answer for the user>"}       when you can answer.\n'
        "Tool results come back as {ok, data, error}. Base answers only on tool results. "
        "Inspection codes look like INS-000042; a score below 70 is a failed inspection."
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def run_agent(
    user_input: str,
    *,
    model: Optional[ChatModel] = None,
    max_steps: int = DEFAULT_MAX_STEPS,
    repo: Optional[InspectionRepository] = None,
    log_path: Optional[Path] = DEFAULT_LOG_PATH,
    scenario: Optional[str] = None,
) -> dict:
    model = model if model is not None else OllamaModel()
    run_id = uuid.uuid4().hex[:12]
    messages: list[dict] = [{"role": "system", "content": system_prompt()},
                            {"role": "user", "content": user_input}]
    events: list[dict] = []

    def log(event: dict) -> None:
        record = {"run_id": run_id, "ts": _now(), "scenario": scenario, "model": model.name, **event}
        events.append(record)
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, default=str) + "\n")

    log({"event": "start", "user_input": user_input, "max_steps": max_steps})
    step = tool_calls = 0
    stop_reason, final_answer = "max_steps", None

    while step < max_steps:
        step += 1
        t0 = time.perf_counter()
        try:
            raw = model.complete(messages)
        except Exception as exc:  # noqa: BLE001 - Ollama down / model missing
            stop_reason, final_answer = "model_error", f"{type(exc).__name__}: {exc}"
            log({"event": "step", "step": step, "error": final_answer})
            break
        model_ms = round((time.perf_counter() - t0) * 1000, 1)
        messages.append({"role": "assistant", "content": raw})

        try:
            reply = json.loads(raw)
            action = reply.get("action")
        except (json.JSONDecodeError, AttributeError):
            reply, action = None, None

        if action == "final":
            final_answer = str(reply.get("answer", ""))
            stop_reason = "final_answer"
            log({"event": "step", "step": step, "model_ms": model_ms, "action": "final", "answer": final_answer})
            break

        if action != "tool":
            feedback = ('Invalid reply. Respond with one JSON object: {"action": "tool", ...} '
                        'or {"action": "final", "answer": ...}.')
            log({"event": "step", "step": step, "model_ms": model_ms, "action": "invalid", "raw": raw[:500]})
            messages.append({"role": "user", "content": feedback})
            continue

        tool, inputs = reply.get("tool"), reply.get("inputs", {})
        tool_calls += 1
        t1 = time.perf_counter()
        result_json = execute_tool(str(tool), inputs, repo=repo)
        result = json.loads(result_json)
        log({"event": "step", "step": step, "model_ms": model_ms, "action": "tool", "tool": tool,
             "inputs": inputs, "result": result, "tool_ms": round((time.perf_counter() - t1) * 1000, 1)})

        if not result["ok"] and str(result["error"]).startswith(SAFETY_PREFIX):
            stop_reason = "safety_block"
            final_answer = f"Request blocked by safety rule: {result['error']}"
            break
        messages.append({"role": "user", "content": f"TOOL_RESULT {tool}: {result_json[:MAX_RESULT_CHARS]}"})

    summary = {"run_id": run_id, "scenario": scenario, "model": model.name, "user_input": user_input,
               "stop_reason": stop_reason, "steps": step, "tool_calls": tool_calls,
               "max_steps": max_steps, "final_answer": final_answer}
    log({"event": "stop", **{k: v for k, v in summary.items() if k not in ("run_id", "scenario", "model")}})
    summary["events"] = events
    return summary
