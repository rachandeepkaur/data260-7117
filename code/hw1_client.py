from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from model_client import ModelClient, ModelClientError  # noqa: E402

AGENT_MD_PATH = Path(__file__).resolve().parent.parent / "AGENT.md"


def load_system_prompt() -> str:
    return AGENT_MD_PATH.read_text().strip()


class ConversationStats:
    
    def __init__(self) -> None:
        self.turns = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def record(self, usage: Dict[str, int]) -> None:
        self.turns += 1
        self.input_tokens += usage.get("input_tokens", 0)
        self.output_tokens += usage.get("output_tokens", 0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def print_turn_usage(usage: Dict[str, int]) -> None:
    print(f"  [tokens] input={usage.get('input_tokens', 0)} "
          f"output={usage.get('output_tokens', 0)} "
          f"total={usage.get('total_tokens', 0)}")


def print_stats(stats: ConversationStats, history: List[Dict[str, str]]) -> None:
    # json.dumps(history) only reads the list - it doesn't mutate it, so this is safe to call as often as needed without affecting later turns.
    history_length = len(json.dumps(history))
    print("--- /stats ---")
    print(f"turns: {stats.turns}")
    print(f"cumulative input tokens: {stats.input_tokens}")
    print(f"cumulative output tokens: {stats.output_tokens}")
    print(f"cumulative total tokens: {stats.total_tokens}")
    print(f"serialized conversation-history length: {history_length} chars")
    print("--------------")


def print_exit_summary(stats: ConversationStats) -> None:
    print("--- session end ---")
    print(f"cumulative input tokens: {stats.input_tokens}")
    print(f"cumulative output tokens: {stats.output_tokens}")
    print(f"turn count: {stats.turns}")


def main() -> None:
    client = ModelClient()
    history: List[Dict[str, str]] = [{"role": "system", "content": load_system_prompt()}]
    stats = ConversationStats()

    print("hw1_client.py - type a message, /stats, or /exit (Ctrl-D also exits).")

    while True:
        try:
            user_input = input("> ").strip()
        except EOFError:
            print()
            break

        if not user_input:
            continue
        if user_input == "/exit":
            break
        if user_input == "/stats":
            print_stats(stats, history)
            continue

        history.append({"role": "user", "content": user_input})
        try:
            reply = client.complete(history)
        except ModelClientError as exc:
            print(f"Model call failed: {exc}", file=sys.stderr)
            history.pop() 
            continue

        history.append({"role": "assistant", "content": reply})
        stats.record(client.last_usage)

        print(reply)
        print_turn_usage(client.last_usage)

    print_exit_summary(stats)


if __name__ == "__main__":
    main()
