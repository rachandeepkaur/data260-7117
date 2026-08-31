"""FastAPI backend for the inspection form.

Serves the static HTML/JS in this folder and exposes POST /api/analyze, which
runs a submitted form through the Planner -> Reviewer -> Publish agent
pipeline in code/agents_demo.py and returns the Publish JSON.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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

app = FastAPI(title="Restaurant Inspection Agents API")

# Local dev only - the frontend and API run on different origins/ports here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_client = ModelClient()

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
    return FileResponse(THIS_DIR / "HW1-RachandeepKaur.html")


# Serves script.js (and anything else in this folder) as static files.
# Mounted last so it doesn't shadow the routes registered above.
app.mount("/", StaticFiles(directory=THIS_DIR), name="static")
