"""CRUD for inspectors, the related entity (HW5 Part 1).

One inspector performs many inspections (inspections.inspector_id FK).
Every route requires a logged-in user (server-side session cookie).
    POST   /api/inspectors                     add an inspector
    GET    /api/inspectors?page=&page_size=    list with pagination (total in X-Total-Count)
    GET    /api/inspectors/{id}                one inspector
    PUT    /api/inspectors/{id}                update (partial: only fields sent)
    DELETE /api/inspectors/{id}                delete - 409 while inspections still reference it
    GET    /api/inspectors/{id}/inspections    relationship query: that inspector's inspections

Errors: 404 not found, 422 validation error (incl. malformed email), 409 duplicate
email or delete blocked by ON DELETE RESTRICT.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import Inspection, Inspector, User
from routers.records import RecordOut
from security import get_current_user

router = APIRouter(prefix="/api/inspectors", tags=["inspectors"])


class InspectorIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    district: str = Field(min_length=2, max_length=120)
    email: EmailStr


class InspectorUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    district: Optional[str] = Field(default=None, min_length=2, max_length=120)
    email: Optional[EmailStr] = None

    @model_validator(mode="after")
    def _not_empty(self) -> "InspectorUpdate":
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        return self


class InspectorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    district: str
    email: str
    created_at: datetime
    updated_at: datetime


def _get_or_404(db_session_basede26: Session, inspector_id: int) -> Inspector:
    inspector = db_session_basede26.get(Inspector, inspector_id)
    if inspector is None:
        raise HTTPException(status_code=404, detail=f"Inspector with id {inspector_id} not found")
    return inspector


def _commit(db_session_basede26: Session, inspector: Inspector) -> Inspector:
    try:
        db_session_basede26.commit()
    except IntegrityError as exc:
        db_session_basede26.rollback()
        raise HTTPException(status_code=409, detail=f"email {inspector.email} already exists") from exc
    db_session_basede26.refresh(inspector)
    return inspector


@router.post("", response_model=InspectorOut, status_code=201)
def create_inspector(
    payload: InspectorIn,
    _user: User = Depends(get_current_user),
    db_session_basede26: Session = Depends(get_db),
) -> Inspector:
    inspector = Inspector(
        full_name=payload.full_name.strip(),
        district=payload.district.strip(),
        email=payload.email.lower(),
    )
    db_session_basede26.add(inspector)
    return _commit(db_session_basede26, inspector)


@router.get("", response_model=list[InspectorOut])
def list_inspectors(
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    _user: User = Depends(get_current_user),
    db_session_basede26: Session = Depends(get_db),
) -> list[Inspector]:
    total = db_session_basede26.scalar(select(func.count()).select_from(Inspector))
    response.headers["X-Total-Count"] = str(total)
    stmt = select(Inspector).order_by(Inspector.id).offset((page - 1) * page_size).limit(page_size)
    return list(db_session_basede26.execute(stmt).scalars())


@router.get("/{inspector_id}", response_model=InspectorOut)
def get_inspector(
    inspector_id: int,
    _user: User = Depends(get_current_user),
    db_session_basede26: Session = Depends(get_db),
) -> Inspector:
    return _get_or_404(db_session_basede26, inspector_id)


@router.put("/{inspector_id}", response_model=InspectorOut)
def update_inspector(
    inspector_id: int,
    payload: InspectorUpdate,
    _user: User = Depends(get_current_user),
    db_session_basede26: Session = Depends(get_db),
) -> Inspector:
    inspector = _get_or_404(db_session_basede26, inspector_id)
    for field, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(inspector, field, value.lower() if field == "email" else value.strip())
    return _commit(db_session_basede26, inspector)


@router.delete("/{inspector_id}", response_model=InspectorOut)
def delete_inspector(
    inspector_id: int,
    _user: User = Depends(get_current_user),
    db_session_basede26: Session = Depends(get_db),
) -> InspectorOut:
    inspector = _get_or_404(db_session_basede26, inspector_id)
    deleted = InspectorOut.model_validate(inspector)
    db_session_basede26.delete(inspector)
    try:
        db_session_basede26.commit()  # MySQL FK ON DELETE RESTRICT is the source of truth
    except IntegrityError as exc:
        db_session_basede26.rollback()
        count = db_session_basede26.scalar(
            select(func.count()).select_from(Inspection).where(Inspection.inspector_id == inspector_id)
        )
        raise HTTPException(
            status_code=409,
            detail=f"Inspector {inspector_id} still has {count} inspection(s); reassign or delete them first",
        ) from exc
    return deleted


@router.get("/{inspector_id}/inspections", response_model=list[RecordOut])
def list_inspector_inspections(
    inspector_id: int,
    response: Response,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(get_current_user),
    db_session_basede26: Session = Depends(get_db),
) -> list[Inspection]:
    _get_or_404(db_session_basede26, inspector_id)
    where = Inspection.inspector_id == inspector_id
    response.headers["X-Total-Count"] = str(
        db_session_basede26.scalar(select(func.count()).select_from(Inspection).where(where))
    )
    stmt = select(Inspection).where(where).order_by(Inspection.id).offset(offset).limit(limit)
    return list(db_session_basede26.execute(stmt).scalars())
