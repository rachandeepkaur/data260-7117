"""MySQL-backed CRUD for inspection records (HW4 Part 2, extended in HW5).

Every route requires a logged-in user (server-side session cookie).
    POST   /api/records            add a record
    GET    /api/records            view all records (optional limit/offset)
    GET    /api/records/{id}       view one record
    PUT    /api/records/{id}       update a record (partial: only fields sent)
    DELETE /api/records/{id}       delete a record
    DELETE /api/records/highest    delete the highest-id record (HW2 dashboard)

HW5: each inspection has a unique inspection_code (INS-######), a score
(0-100, default 100) and belongs to one inspector (inspector_id FK).
Errors: 404 record not found, 422 validation error / unknown inspector_id,
409 duplicate inspection_code.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import Inspection, Inspector, User
from security import get_current_user

router = APIRouter(prefix="/api/records", tags=["records"])

INSPECTION_CODE_PATTERN = r"^INS-\d{6}$"


class RecordIn(BaseModel):
    inspection_code: str = Field(pattern=INSPECTION_CODE_PATTERN, examples=["INS-005001"])
    facility_name: str = Field(min_length=1, max_length=255)
    site_address: str = Field(min_length=1, max_length=255)
    score: int = Field(default=100, ge=0, le=100)
    inspector_id: int = Field(ge=1)


class RecordUpdate(BaseModel):
    # All optional so the HW2 dashboard's rename-only PUT keeps working.
    inspection_code: Optional[str] = Field(default=None, pattern=INSPECTION_CODE_PATTERN)
    facility_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    site_address: Optional[str] = Field(default=None, min_length=1, max_length=255)
    score: Optional[int] = Field(default=None, ge=0, le=100)
    inspector_id: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _not_empty(self) -> "RecordUpdate":
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        return self


class RecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    inspection_code: str
    facility_name: str
    site_address: str
    score: int
    inspector_id: int
    created_at: datetime
    updated_at: datetime


def _get_or_404(db_session_basede26: Session, record_id: int) -> Inspection:
    record = db_session_basede26.get(Inspection, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Record with id {record_id} not found")
    return record


def _require_inspector(db_session_basede26: Session, inspector_id: int) -> None:
    if db_session_basede26.get(Inspector, inspector_id) is None:
        raise HTTPException(status_code=422, detail=f"inspector_id {inspector_id} does not exist")


def _commit(db_session_basede26: Session, record: Inspection) -> Inspection:
    """Commit, mapping a duplicate inspection_code to 409, then reload
    server-generated columns (timestamps, score default)."""
    try:
        db_session_basede26.commit()
    except IntegrityError as exc:
        db_session_basede26.rollback()
        raise HTTPException(
            status_code=409, detail=f"inspection_code {record.inspection_code} already exists"
        ) from exc
    db_session_basede26.refresh(record)
    return record


@router.get("", response_model=list[RecordOut])
def list_records(
    response: Response,
    limit: Optional[int] = Query(default=None, ge=1, le=10000),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(get_current_user),
    db_session_basede26: Session = Depends(get_db),
) -> list[Inspection]:
    """Newest first, so a just-created record shows at the top of the list."""
    total = db_session_basede26.scalar(select(func.count()).select_from(Inspection))
    response.headers["X-Total-Count"] = str(total)
    stmt = select(Inspection).order_by(Inspection.id.desc()).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db_session_basede26.execute(stmt).scalars())


@router.post("", response_model=RecordOut, status_code=201)
def create_record(
    payload: RecordIn,
    _user: User = Depends(get_current_user),
    db_session_basede26: Session = Depends(get_db),
) -> Inspection:
    _require_inspector(db_session_basede26, payload.inspector_id)
    record = Inspection(
        inspection_code=payload.inspection_code,
        facility_name=payload.facility_name.strip(),
        site_address=payload.site_address.strip(),
        score=payload.score,
        inspector_id=payload.inspector_id,
    )
    db_session_basede26.add(record)
    return _commit(db_session_basede26, record)  # MySQL AUTO_INCREMENT assigns record.id


# Registered before "/{record_id}" so "highest" isn't parsed as an int id.
@router.delete("/highest", response_model=Optional[RecordOut])
def delete_highest_record(
    _user: User = Depends(get_current_user),
    db_session_basede26: Session = Depends(get_db),
) -> Optional[Inspection]:
    record = db_session_basede26.execute(
        select(Inspection).order_by(Inspection.id.desc()).limit(1)
    ).scalar_one_or_none()
    if record is None:
        return None
    db_session_basede26.delete(record)
    db_session_basede26.commit()
    return record


@router.get("/{record_id}", response_model=RecordOut)
def get_record(
    record_id: int,
    _user: User = Depends(get_current_user),
    db_session_basede26: Session = Depends(get_db),
) -> Inspection:
    return _get_or_404(db_session_basede26, record_id)


@router.put("/{record_id}", response_model=RecordOut)
def update_record(
    record_id: int,
    payload: RecordUpdate,
    _user: User = Depends(get_current_user),
    db_session_basede26: Session = Depends(get_db),
) -> Inspection:
    record = _get_or_404(db_session_basede26, record_id)
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "inspector_id" in changes:
        _require_inspector(db_session_basede26, changes["inspector_id"])
    for field, value in changes.items():
        setattr(record, field, value.strip() if isinstance(value, str) else value)
    return _commit(db_session_basede26, record)


@router.delete("/{record_id}", response_model=RecordOut)
def delete_record(
    record_id: int,
    _user: User = Depends(get_current_user),
    db_session_basede26: Session = Depends(get_db),
) -> Inspection:
    record = _get_or_404(db_session_basede26, record_id)
    deleted = RecordOut.model_validate(record)
    db_session_basede26.delete(record)  # cascades to its inspection_violations
    db_session_basede26.commit()
    return deleted
