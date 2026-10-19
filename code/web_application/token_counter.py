"""Token counting for the per-component memory cost log (HW6 Part 3.1).

Ollama only reports the *total* prompt/completion tokens of a call, so the
split into system primer / long-term summary / short-term window / episodic
facts is counted locally with the same tokenizer as the served model
(Qwen3, from the Hugging Face hub - downloaded once, then cached). If the
tokenizer cannot be loaded the count falls back to len(text)/4, and
`tokenizer_name()` says so in every log row.
"""
from __future__ import annotations

from functools import lru_cache

import settings

# <|im_start|>{role}\n ... <|im_end|>\n wrapped around every chat message.
CHATML_OVERHEAD_PER_MESSAGE = 5


@lru_cache(maxsize=1)
def _tokenizer():
    try:
        from tokenizers import Tokenizer

        return Tokenizer.from_pretrained(settings.TOKENIZER_ID)
    except Exception:  # noqa: BLE001 - offline / hub unreachable
        return None


def tokenizer_name() -> str:
    return settings.TOKENIZER_ID if _tokenizer() is not None else "chars/4 estimate"


def count_tokens(text: str) -> int:
    if not text:
        return 0
    tok = _tokenizer()
    if tok is None:
        return max(1, len(text) // 4)
    return len(tok.encode(text, add_special_tokens=False).ids)


def count_messages(messages: list[dict]) -> int:
    """Tokens of chat messages including the ChatML wrapper of each."""
    return sum(count_tokens(m["content"]) + CHATML_OVERHEAD_PER_MESSAGE for m in messages)
