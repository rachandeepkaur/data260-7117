"""Reusable model adapter around a local Ollama model (via LangChain)."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence, Type, TypeVar

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from pydantic import BaseModel, ValidationError

MODEL_ID = "qwen3:8b"
DEFAULT_MAX_ATTEMPTS = 3

T = TypeVar("T", bound=BaseModel)

Message = Dict[str, str]  # {"role": "system" | "user" | "assistant", "content": str}

_ROLE_TO_MESSAGE_CLASS = {
    "system": SystemMessage,
    "user": HumanMessage,
    "assistant": AIMessage,
}


class ModelClientError(RuntimeError):
    """Raised when the local model is unreachable, or never returns valid,
    schema-matching JSON within the retry budget."""


def _to_langchain_messages(messages: Sequence[Message]) -> List[BaseMessage]:
    converted: List[BaseMessage] = []
    for message in messages:
        role = message["role"]
        message_class = _ROLE_TO_MESSAGE_CLASS.get(role)
        if message_class is None:
            raise ValueError(f"Unsupported message role: {role!r}")
        converted.append(message_class(content=message["content"]))
    return converted


class ModelClient:
    """Adapter around a local Ollama chat model."""

    def __init__(self, model: str = MODEL_ID, temperature: float = 0.1) -> None:
        self._model_name = model
        self._llm = ChatOllama(model=model, temperature=temperature, reasoning=False)
        # Token usage (input/output/total) from the most recent complete() call, exposed for callers that want to report per-turn token counts.
        self.last_usage: Dict[str, int] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    def complete(
        self,
        messages: Sequence[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        *,
        response_format: Optional[str] = None,
        max_tokens: int = 4096,
    ) -> str:
        """Send `messages` to the model and return its raw text reply."""
        self._llm.num_predict = max_tokens
        self._llm.format = response_format
        model = self._llm.bind_tools(tools) if tools else self._llm

        try:
            response = model.invoke(_to_langchain_messages(messages))
        except Exception as exc:  # connection refused, model not pulled, daemon down
            raise ModelClientError(
                f"Could not reach Ollama model '{self._model_name}'. Make sure `ollama serve` "
                f"is running and `ollama pull {self._model_name}` has completed. ({exc})"
            ) from exc

        usage = response.usage_metadata or {}
        self.last_usage = {key: usage.get(key, 0) for key in self.last_usage}
        return response.content

    def call(
        self,
        *,
        system: str,
        user: str,
        output_format: Type[T],
        max_tokens: int = 4096,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> T:
        """Call the model and parse+validate its JSON reply as `output_format`."""
        messages: List[Message] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        last_error: Optional[Exception] = None
        last_raw = ""

        for _attempt in range(1, max_attempts + 1):
            last_raw = self.complete(messages, response_format="json", max_tokens=max_tokens)

            try:
                data = json.loads(last_raw)
                return output_format.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                continue

        raise ModelClientError(
            f"Model '{self._model_name}' did not return valid '{output_format.__name__}' JSON "
            f"after {max_attempts} attempt(s). Last error: {last_error!r}. "
            f"Last raw response: {last_raw!r}"
        )
