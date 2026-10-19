"""Chat with short-term, long-term and episodic memory (HW6 Part 2).

    POST /api/chat                   {user_id, session_id?, message} -> reply + memory used
    GET  /api/memory/{user_id}       last 16 messages, latest session + lifetime summary, last 20 facts
    GET  /api/aggregate/{user_id}    daily message counts + most recent summaries

The memory logic itself lives in memory_service.py; these handlers only
validate input, map errors to status codes and shape the JSON.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pymongo import DESCENDING

import memory_service
import settings
from doc_schemas import ChatRequest, ChatResponse
from mongo import get_db

router = APIRouter(tags=["chat-memory (MongoDB)"])


def _iso(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    for key, value in doc.items():
        if hasattr(value, "isoformat"):
            doc[key] = value.isoformat()
    return doc


@router.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> dict:
    try:
        return memory_service.handle_chat(get_db(), req)
    except memory_service.ChatModelError as exc:
        raise HTTPException(status_code=502, detail=f"Local model call failed: {exc}") from exc


@router.get("/api/memory/{user_id}")
def get_memory(user_id: str, messages: int = Query(default=16, ge=1, le=200),
               facts: int = Query(default=20, ge=1, le=200)) -> dict:
    db = get_db()
    recent = list(db[settings.MESSAGES].find({"user_id": user_id})
                  .sort([("created_at", DESCENDING), ("_id", DESCENDING)]).limit(messages))
    if not recent and db[settings.EPISODES].count_documents({"user_id": user_id}, limit=1) == 0:
        raise HTTPException(status_code=404, detail=f"No memory stored for user '{user_id}'")
    session = db[settings.SUMMARIES].find_one({"user_id": user_id, "scope": "session"},
                                              sort=[("created_at", DESCENDING)])
    lifetime = db[settings.SUMMARIES].find_one({"user_id": user_id, "scope": "user"},
                                               sort=[("created_at", DESCENDING)])
    episodes = db[settings.EPISODES].find({"user_id": user_id}, {"embedding": 0}) \
        .sort("created_at", DESCENDING).limit(facts)
    dims = db[settings.EPISODES].find_one({"user_id": user_id}, {"embedding": 1})
    return {
        "user_id": user_id,
        "messages": [_iso(m) for m in reversed(recent)],
        "session_summary": _iso(session) if session else None,
        "lifetime_summary": _iso(lifetime) if lifetime else None,
        "episodic_facts": [_iso(e) for e in episodes],
        "embedding_dim": len(dims["embedding"]) if dims else None,
    }


@router.get("/api/aggregate/{user_id}")
def aggregate(user_id: str, tz: str = Query(default="America/Los_Angeles"),
              summaries: int = Query(default=5, ge=1, le=50)) -> dict:
    db = get_db()
    daily = list(db[settings.MESSAGES].aggregate([
        {"$match": {"user_id": user_id}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at", "timezone": tz}},
            "messages": {"$sum": 1},
            "user_messages": {"$sum": {"$cond": [{"$eq": ["$role", "user"]}, 1, 0]}},
            "assistant_messages": {"$sum": {"$cond": [{"$eq": ["$role", "assistant"]}, 1, 0]}},
            "sessions": {"$addToSet": "$session_id"},
        }},
        {"$project": {"_id": 0, "date": "$_id", "messages": 1, "user_messages": 1, "assistant_messages": 1,
                      "sessions": {"$size": "$sessions"}}},
        {"$sort": {"date": 1}},
    ]))
    if not daily:
        raise HTTPException(status_code=404, detail=f"No messages stored for user '{user_id}'")
    recent = db[settings.SUMMARIES].find({"user_id": user_id}).sort("created_at", DESCENDING).limit(summaries)
    return {"user_id": user_id, "timezone": tz, "daily_message_counts": daily,
            "total_messages": sum(d["messages"] for d in daily),
            "recent_summaries": [_iso(s) for s in recent]}
