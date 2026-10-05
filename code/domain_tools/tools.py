"""The three domain tools over s7117_rel and their input contracts (Part 2B / 3).

    search_inspections   search      {query, limit=10, min_score?}
    get_inspection       detail      {inspection_code}
    inspection_stats     aggregate   {inspector_id?, zip_code?, facility_query?}

Each input is a Pydantic model with extra="forbid", so a wrong type, an
out-of-range value, a malformed code, or an unknown field is rejected before
any query runs. TOOL_SCHEMAS (the JSON Schemas) is what the agent prompt and
the Part 3 write-up show.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .repository import InspectionRepository


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=2, max_length=100,
                       description="Text to match in facility name or address, or an exact inspection code")
    limit: int = Field(default=10, ge=1, le=25, description="Max results (1-25)")
    min_score: Optional[int] = Field(default=None, ge=0, le=100, description="Only scores >= this")


class DetailInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inspection_code: str = Field(pattern=r"^INS-\d{6}$", description="Inspection code, e.g. INS-000042")


class StatsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inspector_id: Optional[int] = Field(default=None, ge=1, description="Only this inspector's inspections")
    zip_code: Optional[str] = Field(default=None, pattern=r"^\d{5}$", description="5-digit San Jose ZIP")
    facility_query: Optional[str] = Field(default=None, min_length=2, max_length=100,
                                          description="Substring of the facility name")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[InspectionRepository, Any], Any]


def _search(repo: InspectionRepository, args: SearchInput) -> dict:
    rows = repo.search(args.query, args.limit, args.min_score)
    return {"count": len(rows), "results": rows, **({} if rows else {"message": "no matches"})}


def _detail(repo: InspectionRepository, args: DetailInput) -> dict:
    record = repo.get_by_code(args.inspection_code)
    if record is None:
        raise LookupError(f"inspection {args.inspection_code} not found")
    return record


def _stats(repo: InspectionRepository, args: StatsInput) -> dict:
    summary = repo.stats(args.inspector_id, args.zip_code, args.facility_query)
    return {"filters": args.model_dump(exclude_none=True), **summary}


TOOLS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in (
        ToolSpec("search_inspections",
                 "Search restaurant inspections by facility name, address text or exact inspection code.",
                 SearchInput, _search),
        ToolSpec("get_inspection",
                 "Full detail for one inspection: facility, score, inspector and violations.",
                 DetailInput, _detail),
        ToolSpec("inspection_stats",
                 "Aggregate over inspections (count, avg/min/max score, pass rate, violations), "
                 "optionally filtered by inspector_id, zip_code and/or facility_query.",
                 StatsInput, _stats),
    )
}

TOOL_SCHEMAS: dict[str, dict] = {name: spec.input_model.model_json_schema() for name, spec in TOOLS.items()}


def format_validation_error(tool: str, exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "input"
        parts.append(f"{loc}: {err['msg']}")
    return f"invalid input for {tool}: " + "; ".join(parts)
