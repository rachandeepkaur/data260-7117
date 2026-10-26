"""Short-term, long-term (summary) and episodic memory over MongoDB (HW6 Part 2/3).

The /api/chat handler calls `handle_chat`, which runs the server steps in
the order the assignment lists them:

    1. save the user message                          -> messages
    2. load the short-term window (last N messages)   -> load_short_term
    3. load latest session + lifetime summary         -> latest_summary
    4. retrieve top-k episodic facts (cosine)         -> retrieve_episodes
    5. (optional) apply the memory-saving policy      -> apply_memory_policy
    6. compose the prompt                             -> build_prompt
    7. call the local model via the HW1 adapter       -> ModelClient.complete
    8. save the assistant reply                       -> messages
    9. extract <= 3 facts, embed, store               -> extract_facts / store_episodes
   10. every M user messages: session summary, and every few session
       summaries: condense into the lifetime summary  -> maybe_summarize

Every request also returns (and optionally appends to MEMORY_USAGE_LOG) the
Part 3.1 cost record: prompt/completion tokens, the tokens of each prompt
component and the latency.
"""
from __future__ import annotations

import json
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import token_counter
from doc_schemas import ChatRequest, ExtractedFacts
from pymongo import DESCENDING
from pymongo.database import Database

import settings

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
from model_client import ModelClient, ModelClientError  # noqa: E402  (HW1 model adapter)

SYSTEM_PRIMER = (
    "You are InspectBot, the assistant of the s7117 restaurant-inspection app (San Jose area food "
    "facility inspections). Answer in at most 4 short sentences. Use the memory sections below "
    "(summaries, earlier messages and remembered facts) when the user refers to anything said before; "
    "when two remembered facts disagree, trust the most recent one. If the memory does not contain "
    "the answer, say you do not know instead of guessing."
)

EXTRACT_SYSTEM = (
    "You extract durable facts from ONE user chat message for a long-term memory store. "
    "Return JSON only: {\"facts\": [{\"fact\": str, \"importance\": float}]}. Rules: at most 3 facts; "
    "each fact is a self-contained third-person sentence of at most 20 words that names the subject "
    "(e.g. 'The user's name is ...', 'Facility FA123 ...'); keep exact names, codes, dates and numbers; "
    "importance 0..1 (1 = identity, deadlines, decisions, corrections; 0.3 = minor preference); "
    "return {\"facts\": []} for greetings, questions or messages with no new information."
)

SESSION_SUMMARY_SYSTEM = (
    "You maintain a running summary of one chat session. Merge the previous summary with the new "
    "messages into at most 8 concise bullets starting with '- '. Keep names, facility codes, dates, "
    "numbers and decisions exactly; when something was corrected, keep only the corrected value and "
    "say it was changed. No preamble."
)

LIFETIME_SUMMARY_SYSTEM = (
    "You maintain a lifetime profile of one user across all chat sessions. Condense the previous "
    "lifetime summary and the session summaries into at most 10 concise bullets starting with '- '. "
    "Keep durable facts (identity, role, facilities, deadlines, preferences, decisions); drop small "
    "talk; newer information wins over older. No preamble."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


# ------------------------------------------------------------------ messages
def save_message(db: Database, user_id: str, session_id: str, role: str, content: str) -> dict:
    doc = {"user_id": user_id, "session_id": session_id, "role": role, "content": content, "created_at": _now()}
    doc["_id"] = db[settings.MESSAGES].insert_one(doc).inserted_id
    return doc


def load_short_term(db: Database, user_id: str, session_id: str, n: int, before_id=None) -> list[dict]:
    """Sliding window: the last n messages of the session (oldest first), excluding `before_id` onward."""
    if n <= 0:
        return []
    query: dict = {"user_id": user_id, "session_id": session_id}
    if before_id is not None:
        query["_id"] = {"$lt": before_id}  # ObjectIds increase monotonically within one process
    docs = list(db[settings.MESSAGES].find(query, {"role": 1, "content": 1, "created_at": 1})
                .sort([("created_at", DESCENDING), ("_id", DESCENDING)]).limit(n))
    return [{"role": d["role"], "content": d["content"]} for d in reversed(docs)]


# ----------------------------------------------------------------- summaries
def latest_summary(db: Database, user_id: str, scope: str, session_id: Optional[str] = None) -> Optional[dict]:
    query: dict = {"user_id": user_id, "scope": scope}
    query["session_id"] = session_id if scope == "session" else None
    return db[settings.SUMMARIES].find_one(query, sort=[("created_at", DESCENDING), ("_id", DESCENDING)])


def should_summarize(user_message_count: int, every: int = settings.SUMMARIZE_EVERY_USER_MSGS) -> bool:
    """Summarization trigger: true on every M-th user message of the session."""
    return every > 0 and user_message_count > 0 and user_message_count % every == 0


def _summarize(client_usage: list, system: str, user: str, max_tokens: int = 300) -> str:
    client = ModelClient()
    t0 = time.perf_counter()
    text = _clean(client.complete([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                  max_tokens=max_tokens))
    client_usage.append({**client.last_usage, "latency_ms": round((time.perf_counter() - t0) * 1000, 1)})
    return text


def maybe_summarize(db: Database, user_id: str, session_id: str, aux_usage: list) -> dict:
    """Summarization trigger + lifetime condensation. Returns what was (re)written."""
    updates = {"session_summary_updated": False, "lifetime_summary_updated": False}
    n_user = db[settings.MESSAGES].count_documents({"user_id": user_id, "session_id": session_id, "role": "user"})
    if not should_summarize(n_user):
        return updates

    previous = latest_summary(db, user_id, "session", session_id)
    recent = load_short_term(db, user_id, session_id, 2 * settings.SUMMARIZE_EVERY_USER_MSGS)
    transcript = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in recent)
    text = _summarize(aux_usage, SESSION_SUMMARY_SYSTEM,
                      f"Previous summary:\n{previous['text'] if previous else '(none)'}\n\nNew messages:\n{transcript}")
    if text:
        db[settings.SUMMARIES].insert_one({"user_id": user_id, "session_id": session_id, "scope": "session",
                                           "text": text, "created_at": _now()})
        updates["session_summary_updated"] = True

    # "Occasionally" = every LIFETIME_EVERY_SESSION_SUMMARIES session summaries of this user.
    n_session_summaries = db[settings.SUMMARIES].count_documents({"user_id": user_id, "scope": "session"})
    every = settings.LIFETIME_EVERY_SESSION_SUMMARIES
    if text and every > 0 and n_session_summaries % every == 0:
        latest_per_session = list(db[settings.SUMMARIES].aggregate([
            {"$match": {"user_id": user_id, "scope": "session"}},
            {"$sort": {"created_at": -1}},
            {"$group": {"_id": "$session_id", "text": {"$first": "$text"}, "at": {"$first": "$created_at"}}},
            {"$sort": {"at": -1}}, {"$limit": 5},
        ]))
        lifetime = latest_summary(db, user_id, "user")
        joined = "\n\n".join(f"Session {s['_id']}:\n{s['text']}" for s in reversed(latest_per_session))
        life_text = _summarize(aux_usage, LIFETIME_SUMMARY_SYSTEM,
                               f"Previous lifetime summary:\n{lifetime['text'] if lifetime else '(none)'}\n\n"
                               f"Session summaries:\n{joined}")
        if life_text:
            db[settings.SUMMARIES].insert_one({"user_id": user_id, "session_id": None, "scope": "user",
                                               "text": life_text, "created_at": _now()})
            updates["lifetime_summary_updated"] = True
    return updates


# ------------------------------------------------------------------ episodes
@lru_cache(maxsize=1)
def _embedder():
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=settings.EMBEDDING_MODEL)


def embed(texts: list[str]) -> list[list[float]]:
    return [[float(x) for x in v] for v in _embedder().embed(texts)]


def cosine(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    q = query / (np.linalg.norm(query) or 1.0)
    m = matrix / np.clip(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-12, None)
    return m @ q


def retrieve_episodes(db: Database, user_id: str, query_vec: list[float], k: int = settings.EPISODE_TOP_K,
                      min_similarity: float = settings.EPISODE_MIN_SIMILARITY) -> list[dict]:
    """Top-k episodes of this user by cosine similarity to the current message."""
    episodes = list(db[settings.EPISODES].find({"user_id": user_id},
                                               {"fact": 1, "importance": 1, "embedding": 1, "created_at": 1}))
    if not episodes or k <= 0:
        return []
    scores = cosine(np.asarray(query_vec), np.asarray([e["embedding"] for e in episodes]))
    ranked = sorted(zip(episodes, scores, strict=False), key=lambda p: p[1], reverse=True)
    return [{"id": str(e["_id"]), "fact": e["fact"], "importance": e["importance"], "similarity": round(float(s), 4),
             "created_at": e["created_at"].isoformat()}
            for e, s in ranked[:k] if s >= min_similarity]


def extract_facts(message: str, aux_usage: list) -> list[dict]:
    """Episode extraction: up to MAX_FACTS_PER_MESSAGE short facts with an importance score."""
    client = ModelClient()
    t0 = time.perf_counter()
    try:
        result = client.call(system=EXTRACT_SYSTEM, user=f"User message:\n{message}", output_format=ExtractedFacts,
                             max_tokens=220, max_attempts=2)
        facts = [f.model_dump() for f in result.facts[: settings.MAX_FACTS_PER_MESSAGE]]
    except ModelClientError:
        facts = []
    aux_usage.append({**client.last_usage, "latency_ms": round((time.perf_counter() - t0) * 1000, 1)})
    return facts


def store_episodes(db: Database, user_id: str, session_id: str, facts: list[dict]) -> list[dict]:
    """Embed each fact and store it; a near-duplicate (cos >= 0.92) refreshes the stored one instead."""
    if not facts:
        return []
    vectors = embed([f["fact"] for f in facts])
    existing = list(db[settings.EPISODES].find({"user_id": user_id}, {"embedding": 1, "importance": 1}))
    matrix = np.asarray([e["embedding"] for e in existing]) if existing else None
    stored = []
    for fact, vec in zip(facts, vectors, strict=False):
        importance = float(round(fact["importance"], 3))
        if matrix is not None:
            sims = cosine(np.asarray(vec), matrix)
            best = int(np.argmax(sims))
            if sims[best] >= settings.EPISODE_DEDUP_SIMILARITY:
                db[settings.EPISODES].update_one({"_id": existing[best]["_id"]}, {"$set": {
                    "fact": fact["fact"], "embedding": vec, "session_id": session_id, "created_at": _now(),
                    "importance": max(importance, float(existing[best]["importance"]))}})
                stored.append({"fact": fact["fact"], "importance": importance, "action": "merged"})
                continue
        db[settings.EPISODES].insert_one({"user_id": user_id, "session_id": session_id, "fact": fact["fact"],
                                          "importance": importance, "embedding": vec, "created_at": _now()})
        stored.append({"fact": fact["fact"], "importance": importance, "action": "inserted"})
    return stored


# ---------------------------------------------------------- policy + prompt
def _first_sentence(text: str, max_chars: int) -> str:
    m = re.match(r"(.+?[.!?])(\s|$)", text.strip(), flags=re.S)
    short = m.group(1) if m else text.strip()
    return short if len(short) <= max_chars else short[: max_chars - 1].rstrip() + "…"


def apply_memory_policy(window: list[dict], facts: list[dict], policy: str = settings.MEMORY_POLICY):
    """Part 3.4 compression policy.

    "compress": the newest COMPRESS_KEEP_VERBATIM messages stay verbatim; older
    *assistant* turns in the window are cut to their first sentence (<=160
    chars) because they mostly restate what the user said, while user turns -
    where the facts come from - are never shortened; episodic facts below
    cosine 0.40 are evicted as weak matches.
    """
    if policy != "compress":
        return window, facts, {"policy": "none"}
    keep = settings.COMPRESS_KEEP_VERBATIM
    out, truncated = [], 0
    for i, m in enumerate(window):
        if m["role"] == "assistant" and i < len(window) - keep:
            short = _first_sentence(m["content"], settings.COMPRESS_ASSISTANT_CHARS)
            truncated += short != m["content"]
            out.append({"role": "assistant", "content": short})
        else:
            out.append(m)
    kept = [f for f in facts if f["similarity"] >= settings.COMPRESS_MIN_SIMILARITY]
    return out, kept, {"policy": "compress", "assistant_turns_truncated": truncated,
                       "facts_evicted": len(facts) - len(kept)}


def build_prompt(window: list[dict], message: str, session_summary: Optional[str],
                 lifetime_summary: Optional[str], facts: list[dict]) -> tuple[list[dict], dict]:
    """Prompt assembly: system primer + long-term summaries | short-term window | current message + facts.

    Returns the chat messages and the text of each component (for token accounting).
    """
    long_term = ""
    if lifetime_summary:
        long_term += f"\n\n## Lifetime summary (all sessions)\n{lifetime_summary}"
    if session_summary:
        long_term += f"\n\n## Summary of this session so far\n{session_summary}"
    episodic = ""
    if facts:
        lines = "\n".join(f"- [{f['created_at'][:16].replace('T', ' ')}] {f['fact']}" for f in facts)
        episodic = f"\n\n[Remembered facts relevant to this message, newest date wins]\n{lines}"
    messages = [{"role": "system", "content": SYSTEM_PRIMER + long_term}, *window,
                {"role": "user", "content": message + episodic}]
    return messages, {"system_primer": SYSTEM_PRIMER, "long_term": long_term, "episodic": episodic}


# ------------------------------------------------------------------- handler
class ChatModelError(RuntimeError):
    pass


def handle_chat(db: Database, req: ChatRequest) -> dict:
    t0 = time.perf_counter()
    session_id = req.session_id or f"{req.user_id}-{uuid.uuid4().hex[:8]}"
    aux_usage: list[dict] = []

    user_doc = save_message(db, req.user_id, session_id, "user", req.message)
    window = load_short_term(db, req.user_id, session_id, settings.SHORT_TERM_N, before_id=user_doc["_id"])
    session_summary = latest_summary(db, req.user_id, "session", session_id)
    lifetime_summary = latest_summary(db, req.user_id, "user")
    query_vec = embed([req.message])[0]
    facts = retrieve_episodes(db, req.user_id, query_vec)
    window, facts, policy_info = apply_memory_policy(window, facts)

    messages, parts = build_prompt(window, req.message, session_summary and session_summary["text"],
                                   lifetime_summary and lifetime_summary["text"], facts)
    client = ModelClient()
    t_model = time.perf_counter()
    try:
        reply = _clean(client.complete(messages, max_tokens=settings.CHAT_MAX_TOKENS))
    except ModelClientError as exc:
        db[settings.MESSAGES].delete_one({"_id": user_doc["_id"]})  # keep history consistent on failure
        raise ChatModelError(str(exc)) from exc
    model_latency_ms = (time.perf_counter() - t_model) * 1000
    usage_main = dict(client.last_usage)
    save_message(db, req.user_id, session_id, "assistant", reply)

    extracted = store_episodes(db, req.user_id, session_id, extract_facts(req.message, aux_usage))
    updates = maybe_summarize(db, req.user_id, session_id, aux_usage)
    latency_ms = (time.perf_counter() - t0) * 1000

    tc = token_counter
    usage = {
        "prompt_tokens": usage_main.get("input_tokens", 0),          # reported by Ollama
        "completion_tokens": usage_main.get("output_tokens", 0),
        "components": {
            "system_primer": tc.count_tokens(parts["system_primer"]) + tc.CHATML_OVERHEAD_PER_MESSAGE,
            "long_term_summary": tc.count_tokens(parts["long_term"]),
            "short_term_window": tc.count_messages(window),
            "episodic_facts": tc.count_tokens(parts["episodic"]),
            "current_message": tc.count_tokens(req.message) + tc.CHATML_OVERHEAD_PER_MESSAGE,
        },
        "aux_prompt_tokens": sum(u.get("input_tokens", 0) for u in aux_usage),
        "aux_completion_tokens": sum(u.get("output_tokens", 0) for u in aux_usage),
        "aux_calls": len(aux_usage),
        "model_latency_ms": round(model_latency_ms, 1),
        "aux_latency_ms": round(sum(u["latency_ms"] for u in aux_usage), 1),
        "latency_ms": round(latency_ms, 1),
        "tokenizer": tc.tokenizer_name(),
    }
    usage["components"]["counted_total"] = sum(usage["components"].values())

    result = {
        "user_id": req.user_id,
        "session_id": session_id,
        "reply": reply,
        "memory_used": {
            "short_term_count": len(window),
            "short_term": window,
            "session_summary": session_summary["text"] if session_summary else None,
            "lifetime_summary": lifetime_summary["text"] if lifetime_summary else None,
            "episodic_facts": facts,
        },
        "memory_updates": {"facts_extracted": extracted, **updates, **policy_info},
        "usage": usage,
        "config": settings.memory_config(),
    }
    if settings.USAGE_LOG:
        row = {"ts": _now().isoformat(), "user_id": req.user_id, "session_id": session_id,
               "config": result["config"], **usage}
        with open(settings.USAGE_LOG, "a") as fh:
            fh.write(json.dumps(row) + "\n")
    return result
