"""Server configuration for the MongoDB document API + chat memory (HW6).

Every value can be overridden with an environment variable of the same name,
which is how the Part 3 experiment runner restarts the server with a
different SHORT_TERM_N / MEMORY_POLICY for each run.
"""
from __future__ import annotations

import os

SID4 = 7117
PORT_BASE = 8000 + SID4 % 900
PREFIX = f"s{SID4}"

MONGO_URL = os.getenv("MONGO_URL", "mongodb://127.0.0.1:27017")
MONGO_DB = os.getenv("MONGO_DB", f"{PREFIX}_doc")
MONGO_TIMEOUT_MS = int(os.getenv("MONGO_TIMEOUT_MS", "3000"))

# Collections in MONGO_DB.
DOC_COLLECTION = "inspections"
MESSAGES = "messages"
SUMMARIES = "summaries"
EPISODES = "episodes"

# Memory layers.
SHORT_TERM_N = int(os.getenv("SHORT_TERM_N", "12"))
SUMMARIZE_EVERY_USER_MSGS = int(os.getenv("SUMMARIZE_EVERY_USER_MSGS", "5"))
LIFETIME_EVERY_SESSION_SUMMARIES = int(os.getenv("LIFETIME_EVERY_SESSION_SUMMARIES", "2"))
EPISODE_TOP_K = int(os.getenv("EPISODE_TOP_K", "3"))
EPISODE_MIN_SIMILARITY = float(os.getenv("EPISODE_MIN_SIMILARITY", "0.25"))
EPISODE_DEDUP_SIMILARITY = 0.92
MAX_FACTS_PER_MESSAGE = 3

# Context policy: "none" sends the last SHORT_TERM_N messages verbatim;
# "compress" keeps the newest COMPRESS_KEEP_VERBATIM verbatim and shortens
# older assistant turns.
MEMORY_POLICY = os.getenv("MEMORY_POLICY", "none")
COMPRESS_KEEP_VERBATIM = int(os.getenv("COMPRESS_KEEP_VERBATIM", "2"))
COMPRESS_ASSISTANT_CHARS = int(os.getenv("COMPRESS_ASSISTANT_CHARS", "160"))
COMPRESS_MIN_SIMILARITY = float(os.getenv("COMPRESS_MIN_SIMILARITY", "0.40"))

CHAT_MAX_TOKENS = int(os.getenv("CHAT_MAX_TOKENS", "200"))
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TOKENIZER_ID = "Qwen/Qwen3-8B"

# Per-request token usage is appended here as JSONL when set (Part 3 metrics).
USAGE_LOG = os.getenv("MEMORY_USAGE_LOG", "")


def memory_config() -> dict:
    """The memory settings in effect, echoed in /api/chat responses and logs."""
    return {
        "SHORT_TERM_N": SHORT_TERM_N,
        "SUMMARIZE_EVERY_USER_MSGS": SUMMARIZE_EVERY_USER_MSGS,
        "LIFETIME_EVERY_SESSION_SUMMARIES": LIFETIME_EVERY_SESSION_SUMMARIES,
        "EPISODE_TOP_K": EPISODE_TOP_K,
        "MEMORY_POLICY": MEMORY_POLICY,
    }
