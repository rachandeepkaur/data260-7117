"""FastAPI backend for the restaurant inspection domain (DOMAIN_ID: 5).

Page routes are Jinja2-templated and split across two routers:
- routers/home.py: "/" (the welcome page).
- routers/auth.py: "/login" (GET+POST), "/dashboard", "/logout", plus the
  session state (Starlette's SessionMiddleware, a signed HttpOnly,
  SameSite=Lax, Secure cookie) they all read/write.
- routers/api_auth.py: JSON login/logout for the React client (HW4) - email +
  password checked against the MySQL `users` table, session stored in the
  `sessions` table, opaque token in an HttpOnly cookie.
- routers/records.py: MySQL-backed records CRUD (HW4; replaced the HW2
  in-memory list).
- routers/nplus1.py: naive vs. fixed list endpoints for the N+1 experiment.
This file only wires up the middleware/routers and serves the agent pipeline.

Runs on PORT_BASE = 8000 + (7117 mod 900) = 8817.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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
from routers.api_auth import router as api_auth_router
from routers.auth import router as auth_router
from routers.home import router as home_router
from routers.nplus1 import router as nplus1_router
from routers.records import router as records_router

PORT_BASE = 8000 + (7117 % 900)  # 8817

# Create FastAPI app
app = FastAPI(title="Restaurant Inspection Records API")

# Local dev only - the React dev server (Vite, :5173) calls this API. The
# session cookie needs allow_credentials, which can't be combined with a "*"
# origin, so the allowed origins are listed explicitly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-SQL-Query-Count", "X-Server-Time-Ms"],
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
app.include_router(api_auth_router)
app.include_router(nplus1_router)
app.include_router(records_router)

_client = ModelClient()


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
    uvicorn.run(app, host="0.0.0.0", port=PORT_BASE)
