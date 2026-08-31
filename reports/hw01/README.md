# HW01 — Conversation & Context Notes

Answers below are grounded in [code/hw1_client.py](../../code/hw1_client.py) and
[src/model_client.py](../../src/model_client.py), and evidenced by
[code/hw1_client_transcript.txt](../../code/hw1_client_transcript.txt).

## Why is prior conversation context resent with every turn?

The model itself is stateless between calls: `ModelClient.complete()` (`src/model_client.py`) makes one `ChatOllama.invoke()` call per turn, and the model has no memory of anything outside that single call. `hw1_client.py` keeps the entire exchange in a Python list, `history`, and on every turn it
appends the new user message and calls `client.complete(history)` with the *whole list* system prompt plus every prior user/assistant message, not just the newest message. Resending the full history is what makes the model "remember" turn 1 while answering turn 5, for the each call is like a fresh conversation, and the illusion of memory comes entirely from the client replaying the transcript back to it each time.

## How is a system prompt different from a user message?

Both are just entries in the same `history` list with a `role` field (`"system"` vs `"user"`, mapped to `SystemMessage`/`HumanMessage` in `_to_langchain_messages`), but they play different roles in shaping the output:

- The **system message** (`AGENT.md`, loaded once via `load_system_prompt()` and inserted as `history[0]`) sets standing instructions/persona for the
*entire* conversation here, "respond only as a strict bullet-only codemreviewer." It's sent once and never changes.
- **User messages** are the turn-by-turn content the conversation is actually about (the code snippets being reviewed). Each one is new, appended once, and doesn't restate the rules.

Models are trained to give system-role instructions priority over user-role content, so the system prompt is the mechanism for asking "how should you
behave for every reply," while user messages are "what should you respond to right now." The transcript's turn 3/5 pressure tests (asking the model to
drop the bullet format) exercise exactly this: whether a user message can override a standing system instruction.

## Why do input tokens grow over a conversation?

Because `history` only ever grows (each turn appends a user message and, after a successful reply, an assistant message see `hw1_client.py`'s
`main()` loop), and the *entire* `history` is resent on every call. Turn N's input therefore contains the system prompt plus all `2*(N-1)` prior messages plus the new one. The recorded transcript shows this directly — per-turn input tokens climbed monotonically as the conversation went on:


| Turn | input tokens |
| ---- | ------------ |
| 1    | 267          |
| 2    | 314          |
| 3    | 381          |
| 4    | 441          |
| 5    | 502          |


`/stats`'s `serialized conversation-history length` (`len(json.dumps(history))`, 1888 chars after turn 3 → 2451 chars after turn 5) grows for the same reason it's the same accumulating list being measured a different way. Output tokens, by contrast, stay roughly flat per turn (~16–24 tokens) since each reply only has to cover that turn's content.

## What eventually limits that growth?

The model's **context window** — the fixed maximum number of tokens (input + output combined) `qwen3:8b` can process in a single call. Since input size grows roughly linearly with turn count while the window is fixed, a long enough conversation will eventually exceed it. `hw1_client.py` has no mitigation for this (no truncation, sliding window, or summarization of older turns). It will keep resending the full, ever-growing `history` until
a call fails or is truncated by the model backend. In a production client, this is normally handled by trimming the oldest turns, summarizing older
history into a shorter form, or capping total conversation length before that limit is hit. From my finding about the agentic memory that to mitigate these context memory size the history data has categories into different categoris whther that particular information needed for future or not. And stored it accordingly.