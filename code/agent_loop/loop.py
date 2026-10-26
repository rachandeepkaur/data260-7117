"""run_agent: the hand-written tool-calling loop (HW7 Part 2).

    run_agent(user_input) -> dict

Each iteration sends the conversation plus the toolset's JSON schemas to the
model through the HW1 adapter (src/model_client.py, ModelClient.chat). Native
tool calls are validated by the toolset, executed, and their results appended
as tool-role messages; the loop continues until the model answers in text or
a hard ceiling is hit.

Repair path - a bad turn is answered with ONE reprompt naming the specific
problem, and the loop stops cleanly after `max_repairs` failed repairs:
    unknown_tool          the tool name is not in the toolset
    malformed_arguments   arguments are not a JSON object or fail the schema
    text_instead_of_tool  plain text before any tool was called

Stop reasons:
    final_answer      model answered after using tools        (normal)
    max_iterations    hard iteration ceiling reached
    repair_limit      more than max_repairs bad turns
    budget_exhausted  tool-call or token budget used up (Part 3 passes budgets)
    model_error       the local model could not be reached

Every tool invocation is logged with its name and inputs, and the total tool
call count is reported at the end. The model is injected, so offline tests
use ScriptedModel and real runs use OllamaChatModel (qwen3:8b).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional, Protocol, Sequence

from .toolsets import Toolset, make_domain_toolset

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_MAX_ITERATIONS = 8
DEFAULT_MAX_REPAIRS = 2
MAX_OBSERVATION_CHARS = 3000  # cap on a tool result inside the model context
TEXT_INSTEAD_OF_TOOL = "text_instead_of_tool"

DOMAIN_SYSTEM_PROMPT = (
    "You answer questions about Santa Clara County (San Jose) restaurant health inspections stored in the "
    "MySQL database s7117_rel. Use the provided tools to look facts up - never invent inspection codes, "
    "scores or numbers.\n"
    "Rules:\n"
    "- Call tools before answering. A question can need several tool calls: keep calling tools until you "
    "have every fact it asks for, then answer.\n"
    "- Inspection codes look like INS-000042. A score below 70 is a failed inspection. pass_rate is a "
    "fraction between 0 and 1.\n"
    "- Tool results are JSON {ok, data, error}. If ok is false, read the error and either fix the call or "
    "tell the user plainly what could not be found.\n"
    "- When you have everything, reply in plain text (no tool call) with a concise answer that cites the "
    "inspection codes and numbers exactly as the tools returned them."
)


class ChatModel(Protocol):
    name: str

    def chat(self, messages: Sequence[dict], tools: Optional[list[dict]] = None, **kwargs: Any) -> Any: ...


class OllamaChatModel:
    """The HW1 adapter (src/model_client.py) with native tool calling."""

    def __init__(self, temperature: float = 0.6, seed: Optional[int] = None, model: Optional[str] = None):
        sys.path.insert(0, str(REPO_ROOT / "src"))
        from model_client import MODEL_ID, ModelClient

        self.name = model or MODEL_ID
        self.settings = {"model": self.name, "temperature": temperature, "seed": seed, "reasoning": False}
        self._client = ModelClient(model=self.name, temperature=temperature, seed=seed)

    def chat(self, messages: Sequence[dict], tools: Optional[list[dict]] = None, **kwargs: Any) -> Any:
        """One model turn (ChatReply: content, tool_calls, invalid_tool_calls, usage)."""
        return self._client.chat(messages, tools, max_tokens=kwargs.get("max_tokens", 1024))


class ScriptedModel:
    """Offline stand-in: returns scripted replies in order (repeats the last).

    Each reply is a dict {"content": str, "tool_calls": [{"name", "arguments"}]}
    or a plain string (text-only reply)."""

    name = "scripted"
    settings = {"model": "scripted"}

    def __init__(self, replies: Sequence[Any]):
        self.replies = list(replies)
        self.calls = 0
        self.seen_messages: list[list[dict]] = []
        self.seen_tools: list[list[str]] = []

    def chat(self, messages: Sequence[dict], tools: Optional[list[dict]] = None, **kwargs: Any) -> Any:
        """Return the next scripted reply as a ChatReply-like object."""
        from types import SimpleNamespace

        self.seen_messages.append([dict(m) for m in messages])
        self.seen_tools.append([t["function"]["name"] for t in tools or []])
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        if isinstance(reply, str):
            reply = {"content": reply}
        calls = [{"id": f"s{self.calls}_{i}", "name": c["name"], "arguments": c.get("arguments")}
                 for i, c in enumerate(reply.get("tool_calls", []))]
        return SimpleNamespace(content=reply.get("content", ""), tool_calls=calls,
                               invalid_tool_calls=reply.get("invalid_tool_calls", []),
                               usage={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120})


def _repair_prompt(problems: list[str], toolset: Toolset, tool_names: list[str]) -> str:
    """The single reprompt sent after a bad turn: the specific problem(s) plus the relevant schema(s)."""
    lines = ["Your previous reply could not be executed:"] + [f"- {p}" for p in problems]
    for name in dict.fromkeys(n for n in tool_names if n in toolset.names):
        lines.append(f"Input JSON schema for {name}: {json.dumps(toolset.schema_of(name))}")
    lines.append(f"Fix the problem and call one of these tools with valid arguments: {', '.join(toolset.names)}.")
    return "\n".join(lines)


def run_agent(
    user_input: str,
    *,
    model: Optional[ChatModel] = None,
    toolset: Optional[Toolset] = None,
    system_prompt: str = DOMAIN_SYSTEM_PROMPT,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    max_repairs: int = DEFAULT_MAX_REPAIRS,
    context_note: Optional[str] = None,
    tool_call_budget: Optional[int] = None,
    token_budget: Optional[int] = None,
    log: Optional[Callable[[str], None]] = print,
) -> dict:
    """Run the tool-calling loop on `user_input` and return the full trace.

    context_note is appended to the user turn as separate data (Part 3 uses it
    for reflections); it never touches the system prompt or the toolset."""
    model = model if model is not None else OllamaChatModel()
    toolset = toolset if toolset is not None else make_domain_toolset()
    say = log or (lambda _msg: None)
    schemas = toolset.schemas()
    user_content = user_input if not context_note else f"{user_input}\n\n{context_note}"
    messages: list[dict] = [{"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_content}]

    trace: list[dict] = []        # executed (valid) tool calls with observations
    failures: list[dict] = []     # classified bad turns
    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    wellformed = {"first_try_turns": 0, "first_try_ok": 0, "repair_turns": 0, "repaired_ok": 0}
    repairs = 0
    pending_repair = False        # the current turn answers a repair prompt
    stop_reason, final_answer = "max_iterations", None
    started = time.perf_counter()
    iteration = 0

    while iteration < max_iterations:
        if token_budget is not None and usage["total_tokens"] >= token_budget:
            stop_reason = "budget_exhausted"
            break
        iteration += 1
        try:
            reply = model.chat(messages, schemas)
        except Exception as exc:  # noqa: BLE001 - Ollama down / model missing
            stop_reason, final_answer = "model_error", f"{type(exc).__name__}: {exc}"
            say(f"[agent] model error: {final_answer}")
            break
        for key in usage:
            usage[key] += int((reply.usage or {}).get(key, 0))

        calls = [dict(c, valid_json=True) for c in reply.tool_calls] + \
                [dict(c, valid_json=False) for c in reply.invalid_tool_calls]
        # Turns that count toward the well-formed rate: a tool call was emitted,
        # a tool call was required (none made yet), or a repair was requested.
        if calls or not trace or pending_repair:
            wellformed["repair_turns" if pending_repair else "first_try_turns"] += 1

        if not calls:
            if trace:  # tools were used -> this text is the final answer (a failed repair if one was pending)
                final_answer, stop_reason = (reply.content or "").strip(), "final_answer"
                messages.append({"role": "assistant", "content": reply.content})
                break
            failures.append({"iteration": iteration, "kind": TEXT_INSTEAD_OF_TOOL,
                             "detail": (reply.content or "")[:300]})
            say(f"[agent] iteration {iteration}: text reply but no tool has been called yet")
            if repairs >= max_repairs:
                stop_reason, final_answer = "repair_limit", (reply.content or "").strip()
                break
            repairs += 1
            pending_repair = True
            messages.append({"role": "assistant", "content": reply.content})
            messages.append({"role": "user", "content": (
                "You replied in text without calling a tool. This question must be answered from tool results. "
                f"Call one of these tools now: {', '.join(toolset.names)}.")})
            continue

        messages.append({"role": "assistant", "content": reply.content or "", "tool_calls": [
            {"id": c["id"], "name": str(c.get("name")),
             "arguments": c["arguments"] if isinstance(c.get("arguments"), dict) else {}} for c in calls]})
        problems, bad_names, budget_hit = [], [], False
        for call in calls:
            name, raw_args = call.get("name"), call.get("arguments")
            checked = toolset.check(name, raw_args if call["valid_json"] else str(raw_args))
            if not checked.ok:
                failures.append({"iteration": iteration, "kind": checked.kind, "detail": checked.problem,
                                 "tool": name, "arguments": raw_args})
                problems.append(checked.problem)
                bad_names.append(str(name))
                say(f"[agent] iteration {iteration}: rejected call {name}({json.dumps(raw_args, default=str)}) "
                    f"-> {checked.kind}")
                messages.append({"role": "tool", "tool_call_id": call["id"], "name": str(name),
                                 "content": json.dumps({"ok": False, "data": None, "error": checked.problem})})
                continue
            if tool_call_budget is not None and len(trace) >= tool_call_budget:
                budget_hit = True
                exhausted = {"ok": False, "data": None, "error": "tool-call budget exhausted"}
                messages.append({"role": "tool", "tool_call_id": call["id"], "name": name,
                                 "content": json.dumps(exhausted)})
                continue
            inputs = checked.args.model_dump(exclude_none=True)
            t0 = time.perf_counter()
            observation = toolset.run(name, checked.args)
            ms = round((time.perf_counter() - t0) * 1000, 1)
            try:
                parsed = json.loads(observation)
            except json.JSONDecodeError:
                parsed = {"ok": False, "error": "tool returned non-JSON output"}
            ok = bool(parsed.get("ok", parsed.get("success", False)))
            trace.append({"n": len(trace) + 1, "iteration": iteration, "tool": name, "inputs": inputs,
                          "ok": ok, "error": parsed.get("error"), "observation": observation, "ms": ms})
            say(f"[tool #{len(trace)}] {name} {json.dumps(inputs)} -> "
                f"{'ok' if ok else 'error: ' + str(parsed.get('error'))[:120]} ({ms} ms)")
            messages.append({"role": "tool", "tool_call_id": call["id"], "name": name,
                             "content": observation[:MAX_OBSERVATION_CHARS]})

        if pending_repair and not problems:
            wellformed["repaired_ok"] += 1
        elif not pending_repair and not problems:
            wellformed["first_try_ok"] += 1
        pending_repair = False

        if budget_hit:
            stop_reason = "budget_exhausted"
            break
        if problems:
            if repairs >= max_repairs:
                stop_reason = "repair_limit"
                say(f"[agent] stopping: {repairs} repair(s) already used")
                break
            repairs += 1
            pending_repair = True
            messages.append({"role": "user", "content": _repair_prompt(problems, toolset, bad_names)})

    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    say(f"[agent] stop_reason={stop_reason} iterations={iteration} total_tool_calls={len(trace)} "
        f"repairs={repairs} tokens={usage['total_tokens']} latency_ms={latency_ms}")
    return {
        "user_input": user_input,
        "final_answer": final_answer,
        "stop_reason": stop_reason,
        "iterations": iteration,
        "tool_calls": len(trace),
        "trace": trace,
        "failures": failures,
        "repairs": repairs,
        "wellformed": wellformed,
        "usage": usage,
        "latency_ms": latency_ms,
        "model": getattr(model, "settings", {"model": getattr(model, "name", "unknown")}),
        "toolset": toolset.name,
        "messages": messages,
    }
