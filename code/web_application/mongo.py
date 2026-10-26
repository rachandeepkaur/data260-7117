"""PyMongo connection for the <PREFIX>_doc database (HW6).

One MongoClient per process (it is thread-safe and pools connections).
`ensure_collections()` creates every collection with a $jsonSchema validator
plus its indexes; it is idempotent (existing collections get their validator
refreshed with collMod), so it runs on app startup and from setup_mongo.py.
"""
from __future__ import annotations

from functools import lru_cache

from doc_schemas import CATEGORIES, STATUSES
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import CollectionInvalid

import settings


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    return MongoClient(settings.MONGO_URL, serverSelectionTimeoutMS=settings.MONGO_TIMEOUT_MS, tz_aware=True)


def get_db() -> Database:
    return get_client()[settings.MONGO_DB]


# Database-level validation mirrors the Pydantic schemas, so a document that
# bypasses the API (e.g. inserted from mongosh) is still checked.
VALIDATORS: dict[str, dict] = {
    settings.DOC_COLLECTION: {
        "bsonType": "object",
        "required": ["facility_name", "status", "program_element", "inspection_date", "created_at", "updated_at"],
        "properties": {
            "facility_name": {"bsonType": "string", "minLength": 1, "maxLength": 100},
            "description": {"bsonType": ["string", "null"], "maxLength": 2000},
            "status": {"enum": list(STATUSES)},
            "program_element": {"enum": list(CATEGORIES)},
            "inspection_date": {"bsonType": "date"},
            "created_at": {"bsonType": "date"},
            "updated_at": {"bsonType": "date"},
        },
    },
    settings.MESSAGES: {
        "bsonType": "object",
        "required": ["user_id", "session_id", "role", "content", "created_at"],
        "properties": {
            "user_id": {"bsonType": "string", "minLength": 1},
            "session_id": {"bsonType": "string", "minLength": 1},
            "role": {"enum": ["user", "assistant"]},
            "content": {"bsonType": "string"},
            "created_at": {"bsonType": "date"},
        },
    },
    settings.SUMMARIES: {
        "bsonType": "object",
        "required": ["user_id", "session_id", "scope", "text", "created_at"],
        "properties": {
            "user_id": {"bsonType": "string", "minLength": 1},
            "session_id": {"bsonType": ["string", "null"]},  # null for the lifetime summary
            "scope": {"enum": ["session", "user"]},
            "text": {"bsonType": "string", "minLength": 1},
            "created_at": {"bsonType": "date"},
        },
    },
    settings.EPISODES: {
        "bsonType": "object",
        "required": ["user_id", "session_id", "fact", "importance", "embedding", "created_at"],
        "properties": {
            "user_id": {"bsonType": "string", "minLength": 1},
            "session_id": {"bsonType": "string"},
            "fact": {"bsonType": "string", "minLength": 1, "maxLength": 300},
            "importance": {"bsonType": "double", "minimum": 0, "maximum": 1},
            "embedding": {"bsonType": "array", "minItems": 1, "items": {"bsonType": "double"}},
            "created_at": {"bsonType": "date"},
        },
    },
}

INDEXES: dict[str, list[list[tuple[str, int]]]] = {
    settings.DOC_COLLECTION: [[("status", ASCENDING), ("inspection_date", DESCENDING)]],
    settings.MESSAGES: [[("user_id", ASCENDING), ("session_id", ASCENDING), ("created_at", DESCENDING)],
                        [("user_id", ASCENDING), ("created_at", DESCENDING)]],
    settings.SUMMARIES: [[("user_id", ASCENDING), ("scope", ASCENDING), ("session_id", ASCENDING),
                          ("created_at", DESCENDING)]],
    settings.EPISODES: [[("user_id", ASCENDING), ("created_at", DESCENDING)]],
}


def ensure_collections(db: Database | None = None) -> list[str]:
    """Create (or refresh the validator of) every HW6 collection; returns their names."""
    db = db if db is not None else get_db()
    for name, schema in VALIDATORS.items():
        validator = {"$jsonSchema": schema}
        try:
            db.create_collection(name, validator=validator, validationLevel="strict", validationAction="error")
        except CollectionInvalid:  # already exists
            db.command("collMod", name, validator=validator, validationLevel="strict", validationAction="error")
        for keys in INDEXES.get(name, []):
            db[name].create_index(keys)
    return list(VALIDATORS)


def ping() -> bool:
    get_client().admin.command("ping")
    return True
