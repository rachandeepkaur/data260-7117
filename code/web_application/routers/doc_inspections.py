"""MongoDB-backed CRUD for the document view of inspections (HW6 Part 1).

    POST   /api/doc/inspections          create          -> 201
    GET    /api/doc/inspections          retrieve all    -> 200 (optional status/program_element filter, limit/skip)
    GET    /api/doc/inspections/{id}     one by ObjectId -> 200
    PUT    /api/doc/inspections/{id}     update (fields sent only) -> 200
    DELETE /api/doc/inspections/{id}     delete          -> 200

Errors: 400 malformed ObjectId, 404 not found, 422 validation (Pydantic or
the collection's $jsonSchema), 503 MongoDB unreachable (handled in app.py).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from doc_schemas import (
    InspectionDocCreate,
    InspectionDocOut,
    InspectionDocUpdate,
    InspectionStatus,
    ProgramElement,
)
from fastapi import APIRouter, HTTPException, Query, Response, status
from pymongo import ReturnDocument
from pymongo.errors import WriteError

import settings
from mongo import get_db

router = APIRouter(prefix="/api/doc/inspections", tags=["doc-inspections (MongoDB)"])


def _collection():
    return get_db()[settings.DOC_COLLECTION]


def _object_id(doc_id: str) -> ObjectId:
    try:
        return ObjectId(doc_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail=f"'{doc_id}' is not a valid 24-character hex ObjectId") from None


def _not_found(doc_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Inspection document {doc_id} not found")


def _schema_rejected(exc: WriteError) -> HTTPException:
    # Only reachable if the Pydantic layer and the $jsonSchema validator disagree.
    return HTTPException(status_code=422, detail={"error": "document failed MongoDB schema validation",
                                                  "mongo": exc.details.get("errInfo") if exc.details else None})


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@router.post("", response_model=InspectionDocOut, status_code=status.HTTP_201_CREATED)
def create_inspection(payload: InspectionDocCreate) -> InspectionDocOut:
    now = datetime.now(timezone.utc)
    doc = payload.model_dump()
    doc["inspection_date"] = _as_utc(doc["inspection_date"])
    doc.update(created_at=now, updated_at=now)
    try:
        result = _collection().insert_one(doc)
    except WriteError as exc:
        raise _schema_rejected(exc) from exc
    doc["_id"] = result.inserted_id
    return InspectionDocOut.from_mongo(doc)


@router.get("", response_model=List[InspectionDocOut])
def list_inspections(
    response: Response,
    status_filter: Optional[InspectionStatus] = Query(default=None, alias="status"),
    program_element: Optional[ProgramElement] = None,
    limit: int = Query(default=50, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
) -> List[InspectionDocOut]:
    query: dict = {}
    if status_filter is not None:
        query["status"] = status_filter.value
    if program_element is not None:
        query["program_element"] = program_element.value
    coll = _collection()
    response.headers["X-Total-Count"] = str(coll.count_documents(query))
    cursor = coll.find(query).sort("inspection_date", -1).skip(skip).limit(limit)
    return [InspectionDocOut.from_mongo(d) for d in cursor]


@router.get("/{doc_id}", response_model=InspectionDocOut)
def get_inspection(doc_id: str) -> InspectionDocOut:
    doc = _collection().find_one({"_id": _object_id(doc_id)})
    if doc is None:
        raise _not_found(doc_id)
    return InspectionDocOut.from_mongo(doc)


@router.put("/{doc_id}", response_model=InspectionDocOut)
def update_inspection(doc_id: str, payload: InspectionDocUpdate) -> InspectionDocOut:
    oid = _object_id(doc_id)
    changes = payload.model_dump(exclude_unset=True)
    if "inspection_date" in changes:
        changes["inspection_date"] = _as_utc(changes["inspection_date"])
    changes["updated_at"] = datetime.now(timezone.utc)
    try:
        doc = _collection().find_one_and_update({"_id": oid}, {"$set": changes}, return_document=ReturnDocument.AFTER)
    except WriteError as exc:
        raise _schema_rejected(exc) from exc
    if doc is None:
        raise _not_found(doc_id)
    return InspectionDocOut.from_mongo(doc)


@router.delete("/{doc_id}")
def delete_inspection(doc_id: str) -> dict:
    result = _collection().delete_one({"_id": _object_id(doc_id)})
    if result.deleted_count == 0:
        raise _not_found(doc_id)
    return {"deleted": True, "id": doc_id}
