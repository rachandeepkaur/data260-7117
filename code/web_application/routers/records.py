"""MySQL-backed CRUD for inspection records (HW4, Part 2).

Every route requires a logged-in user (server-side session cookie).
    POST   /api/records            add a record
    GET    /api/records            view all records (optional limit/offset)
    GET    /api/records/{id}       view one record
    PUT    /api/records/{id}       update a record
    DELETE /api/records/{id}       delete a record
    DELETE /api/records/highest    delete the highest-id record (HW2 dashboard)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from models import Inspection, User
from security import get_current_user

router = APIRouter(prefix="/api/records", tags=["records"])


class RecordIn(BaseModel):
    facility_name: str = Field(min_length=1, max_length=255)
    site_address: str = Field(min_length=1, max_length=255)


class RecordUpdate(BaseModel):
    facility_name: str = Field(min_length=1, max_length=255)
    # Optional so the HW2 dashboard's rename-only PUT keeps working.
    site_address: Optional[str] = Field(default=None, min_length=1, max_length=255)


class RecordOut(RecordIn):
    id: int


def _get_or_404(db_session_basede26: Session, record_id: int) -> Inspection:
    record = db_session_basede26.get(Inspection, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Record with id {record_id} not found")
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
    record = Inspection(facility_name=payload.facility_name.strip(), site_address=payload.site_address.strip())
    db_session_basede26.add(record)
    db_session_basede26.commit()  # MySQL AUTO_INCREMENT assigns record.id
    return record


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
    record.facility_name = payload.facility_name.strip()
    if payload.site_address is not None:
        record.site_address = payload.site_address.strip()
    db_session_basede26.commit()
    return record


@router.delete("/{record_id}", response_model=RecordOut)
def delete_record(
    record_id: int,
    _user: User = Depends(get_current_user),
    db_session_basede26: Session = Depends(get_db),
) -> Inspection:
    record = _get_or_404(db_session_basede26, record_id)
    deleted = RecordOut(id=record.id, facility_name=record.facility_name, site_address=record.site_address)
    db_session_basede26.delete(record)  # cascades to its inspection_violations
    db_session_basede26.commit()
    return deleted
