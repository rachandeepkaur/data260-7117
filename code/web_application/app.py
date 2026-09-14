"""FastAPI backend for the restaurant inspection domain (DOMAIN_ID: 5).

The home view ("/") is the single static HTML/CSS/JS page (HW2-RachandeepKaur.html,
style.css, script.js): its existing inspection form doubles as the Create/Add
action, and a table below it handles Read/Update/Delete/Search, all driven by
the JSON endpoints under /api/records - no server-side HTML rendering. The
same page's form also calls /api/analyze to run the Planner -> Reviewer ->
Publish agent pipeline. 
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

THIS_DIR = Path(__file__).resolve().parent
CODE_DIR = THIS_DIR.parent

sys.path.insert(0, str(CODE_DIR))
from agents_demo import (
    InspectionSubmission,
    ModelClient,
    ModelClientError,
    PublishOutput,
    run_pipeline,
)

app = FastAPI(title="Restaurant Inspection Records API")

# Local dev only - the frontend and API run on different origins/ports here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_client = ModelClient()


# --- In-memory record store (facility_name = primary field, site_address = secondary field) ---
_records: list[dict] = [
    {"id": 1, "facility_name": "FA0206933 - YUMMY KITCHEN", "site_address": "1711 BRANHAM LN A9, SAN JOSE, CA 95118"},
    {"id": 2, "facility_name": "FA0198212 - GOLDEN WOK", "site_address": "455 E SANTA CLARA ST, SAN JOSE, CA 95112"},
]
_next_id = 3


class RecordIn(BaseModel):
    facility_name: str
    site_address: str


class RecordOut(RecordIn):
    id: int


class RecordUpdate(BaseModel):
    facility_name: str


@app.get("/api/records", response_model=list[RecordOut])
def list_records() -> list[dict]:
    return _records


@app.post("/api/records", response_model=RecordOut, status_code=201)
def create_record(payload: RecordIn) -> dict:
    global _next_id
    record = {"id": _next_id, **payload.model_dump()}
    _records.append(record)
    _next_id += 1
    return record


@app.put("/api/records/{record_id}", response_model=RecordOut)
def update_record(record_id: int, payload: RecordUpdate) -> dict:
    for record in _records:
        if record["id"] == record_id:
            record["facility_name"] = payload.facility_name
            return record
    raise HTTPException(status_code=404, detail=f"Record with id {record_id} not found")


@app.delete("/api/records/highest", response_model=Optional[RecordOut])
def delete_highest_record() -> Optional[dict]:
    if not _records:
        return None
    highest = max(_records, key=lambda r: r["id"])
    _records.remove(highest)
    return highest


# Post Api which gets the user input and send the analysis results back to the user
@app.post("/api/analyze", response_model=PublishOutput)
def analyze(submission: InspectionSubmission) -> PublishOutput:
    try:
        _draft, _review, publish = run_pipeline(_client, submission)
    except ModelClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return publish


@app.get("/")
def index() -> FileResponse:
    return FileResponse(THIS_DIR / "HW2-RachandeepKaur.html")


# Serves script.js, style.css (and anything else in this folder) as static
# files. Mounted last so it doesn't shadow the routes registered above.
app.mount("/", StaticFiles(directory=THIS_DIR), name="static")
