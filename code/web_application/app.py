"""FastAPI backend for the restaurant inspection domain (DOMAIN_ID: 5).

Page routes are Jinja2-templated and split across two routers:
- routers/home.py: "/" (the welcome page).
- routers/auth.py: "/login" (GET+POST), "/dashboard", "/logout", plus the
  session state (Starlette's SessionMiddleware, a signed HttpOnly,
  SameSite=Lax, Secure cookie) they all read/write.
This file only wires up the middleware/routers and serves the JSON API for
the records CRUD and the agent pipeline.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

THIS_DIR = Path(__file__).resolve().parent
CODE_DIR = THIS_DIR.parent

sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(CODE_DIR))
from agents_demo import (
    InspectionSubmission,
    ModelClient,
    ModelClientError,
    PublishOutput,
    run_pipeline,
)
from routers.auth import router as auth_router
from routers.home import router as home_router

# Create FastAPI app
app = FastAPI(title="Restaurant Inspection Records API")

# Local dev only - the frontend and API run on different origins/ports here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Secret key for session signing - set a real one via env in any deployment; this default is only for local dev, since it can't sign anything securely
# once other people know it.
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-secret-key")

# Enable session support
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    https_only=True,
    same_site="lax",
    max_age=3600,
)

# Register routes
app.include_router(home_router)
app.include_router(auth_router)

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


# Serves script.js, style.css (and anything else in this folder) as static
# files. Mounted last so it doesn't shadow the page/API routes registered
# above (index.html/login.html/dashboard.html are Jinja2 templates under
# templates/, not part of this static tree, so they aren't reachable here).
app.mount("/", StaticFiles(directory=THIS_DIR), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
