"""Pydantic schemas for the MongoDB document API and the chat-memory API (HW6).

Document entity (collection `inspections` in s7117_doc), mapped from the
generic task-style field list in the assignment:
    facility_name    required short text, 1-100 chars        (the "title")
    description      optional findings text, <= 2000 chars
    status           enum, default "scheduled"               (status-style enum)
    program_element  enum, fixed set from DOMAIN_SCHEMA.md   (category-style field)
    inspection_date  required ISO-8601 date/time
    created_at / updated_at   set by the server, never by the client
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InspectionStatus(str, Enum):
    scheduled = "scheduled"
    in_progress = "in_progress"
    passed = "passed"
    failed = "failed"
    follow_up_required = "follow_up_required"


class ProgramElement(str, Enum):
    fp11 = "FOOD PREP / FOOD SVC OP 0-5 EMPLOYEES RC 3 - FP11"
    fp_6_25 = "FOOD PREP / FOOD SVC OP 6-25 EMPLOYEES"
    routine = "ROUTINE HEALTH INSPECTION"
    follow_up = "FOLLOW-UP COMPLIANCE CHECK"


STATUSES = tuple(s.value for s in InspectionStatus)
CATEGORIES = tuple(c.value for c in ProgramElement)


def _strip_required(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


class InspectionDocCreate(BaseModel):
    # extra="forbid" so a typo such as "staus" is reported instead of ignored,
    # and clients cannot set created_at/updated_at themselves.
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    facility_name: str = Field(min_length=1, max_length=100, examples=["FA0206933 - YUMMY KITCHEN"])
    description: Optional[str] = Field(default=None, max_length=2000)
    status: InspectionStatus = InspectionStatus.scheduled
    program_element: ProgramElement
    inspection_date: datetime = Field(examples=["2026-10-20T09:30:00Z"])

    _strip = field_validator("facility_name")(_strip_required)


class InspectionDocUpdate(BaseModel):
    """PUT body: every field optional, but at least one must be sent."""
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    facility_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)
    status: Optional[InspectionStatus] = None
    program_element: Optional[ProgramElement] = None
    inspection_date: Optional[datetime] = None

    @field_validator("facility_name")
    @classmethod
    def _strip(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else _strip_required(value)

    @model_validator(mode="after")
    def _not_empty(self) -> "InspectionDocUpdate":
        if not self.model_fields_set:
            raise ValueError("provide at least one field to update")
        for name in ("facility_name", "status", "program_element", "inspection_date"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class InspectionDocOut(BaseModel):
    id: str
    facility_name: str
    description: Optional[str] = None
    status: InspectionStatus
    program_element: ProgramElement
    inspection_date: datetime
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_mongo(cls, doc: dict) -> "InspectionDocOut":
        return cls(id=str(doc["_id"]), **{k: v for k, v in doc.items() if k != "_id"})


# ---------------------------------------------------------------- chat memory
class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.@-]+$")
    session_id: Optional[str] = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.@-]+$")
    message: str = Field(min_length=1, max_length=4000)

    _strip = field_validator("message")(_strip_required)


class MemoryUsed(BaseModel):
    short_term_count: int
    short_term: List[dict]
    session_summary: Optional[str]
    lifetime_summary: Optional[str]
    episodic_facts: List[dict]


class ChatResponse(BaseModel):
    user_id: str
    session_id: str
    reply: str
    memory_used: MemoryUsed
    memory_updates: dict
    usage: dict
    config: dict


class EpisodeFact(BaseModel):
    """One fact as returned by the extraction model call."""
    fact: str = Field(min_length=3, max_length=300)
    importance: float = Field(ge=0.0, le=1.0)


class ExtractedFacts(BaseModel):
    facts: List[EpisodeFact] = Field(default_factory=list)

    @field_validator("facts", mode="before")
    @classmethod
    def _cap(cls, value: Any) -> Any:
        return value[:3] if isinstance(value, list) else value
