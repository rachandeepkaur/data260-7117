"""List endpoints for the N+1 experiment (HW4, Part 3).

Both return the same page of inspections (ordered by id) with each
inspection's violations embedded; they differ only in how violations load:

    GET /api/nplus1/naive?page_size=N   1 query for the page + 1 per record  -> N+1
    GET /api/nplus1/fixed?page_size=N   1 query for the page + 1 IN (...)     -> 2
                                        (SQLAlchemy selectinload eager loading)

Each response carries the SQL statement count for the endpoint's own work
(the auth/session lookup is excluded) in the body and in X-SQL-Query-Count,
plus the server-side handler time in X-Server-Time-Ms.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from database import get_db
from models import Inspection, User, Violation
from query_counter import count_queries
from security import get_current_user

router = APIRouter(prefix="/api/nplus1", tags=["n+1 experiment"])


class ViolationOut(BaseModel):
    id: int
    violation_code: str
    description: str
    severity: str
    points_deducted: int
    observed_on: str


class InspectionWithViolations(BaseModel):
    id: int
    facility_name: str
    site_address: str
    violations: list[ViolationOut]


class PageOut(BaseModel):
    version: str
    page_size: int
    offset: int
    sql_queries: int
    record_count: int
    violation_count: int
    items: list[InspectionWithViolations]


def _serialize(inspection: Inspection, violations: list[Violation]) -> dict:
    return {
        "id": inspection.id,
        "facility_name": inspection.facility_name,
        "site_address": inspection.site_address,
        "violations": [
            {
                "id": v.id,
                "violation_code": v.violation_code,
                "description": v.description,
                "severity": v.severity,
                "points_deducted": v.points_deducted,
                "observed_on": v.observed_on.isoformat(),
            }
            for v in violations
        ],
    }


def _page_response(response: Response, version: str, page_size: int, offset: int,
                   sql_queries: int, items: list[dict], started: float) -> dict:
    response.headers["X-SQL-Query-Count"] = str(sql_queries)
    response.headers["X-Server-Time-Ms"] = f"{(time.perf_counter() - started) * 1000:.3f}"
    return {
        "version": version,
        "page_size": page_size,
        "offset": offset,
        "sql_queries": sql_queries,
        "record_count": len(items),
        "violation_count": sum(len(i["violations"]) for i in items),
        "items": items,
    }


@router.get("/naive", response_model=PageOut)
def list_naive(
    response: Response,
    page_size: int = Query(default=10, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(get_current_user),
    db_session_basede26: Session = Depends(get_db),
) -> dict:
    """Intentionally naive: one extra SELECT per inspection on the page."""
    started = time.perf_counter()
    with count_queries() as counter:
        inspections = db_session_basede26.execute(
            select(Inspection).order_by(Inspection.id).limit(page_size).offset(offset)
        ).scalars().all()
        items = []
        for inspection in inspections:
            violations = db_session_basede26.execute(
                select(Violation)
                .where(Violation.inspection_id == inspection.id)
                .order_by(Violation.id)
            ).scalars().all()
            items.append(_serialize(inspection, violations))
    return _page_response(response, "naive", page_size, offset, counter.count, items, started)


@router.get("/fixed", response_model=PageOut)
def list_fixed(
    response: Response,
    page_size: int = Query(default=10, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(get_current_user),
    db_session_basede26: Session = Depends(get_db),
) -> dict:
    """Fixed: eager-load all violations for the page in one IN (...) query."""
    started = time.perf_counter()
    with count_queries() as counter:
        inspections = db_session_basede26.execute(
            select(Inspection)
            .options(selectinload(Inspection.violations))
            .order_by(Inspection.id)
            .limit(page_size)
            .offset(offset)
        ).scalars().all()
        items = [_serialize(inspection, inspection.violations) for inspection in inspections]
    return _page_response(response, "fixed", page_size, offset, counter.count, items, started)
