"""FastAPI backend for the restaurant inspection domain (DOMAIN_ID: 5).

Page routes are Jinja2-templated and split across two routers:
- routers/home.py: "/" (the welcome page).
- routers/auth.py: "/login" (GET+POST), "/dashboard", "/logout", plus the
  session state (Starlette's SessionMiddleware, a signed HttpOnly,
  SameSite=Lax, Secure cookie) they all read/write.
- routers/token_auth.py: POST /auth/login + GET /auth/me (HW7) - username +
  password checked against the PBKDF2 hash in the MySQL `users` table, then a
  JWT bearer token (security.py). Replaces HW4's session-cookie API, which is
  kept only as history at the hw4 tag.
- routers/records.py: MySQL-backed records CRUD (HW4; replaced the HW2
  in-memory list; HW5 adds inspection_code, score, inspector_id; HW7 adds
  JWT roles: read any role, create writer/moderator, delete moderator).
- routers/inspectors.py: inspectors CRUD + /{id}/inspections relationship
  query (HW5, the related entity).
- routers/nplus1.py: naive vs. fixed list endpoints for the N+1 experiment.
- routers/doc_inspections.py: MongoDB document CRUD /api/doc/inspections (HW6
  Part 1; connection in mongo.py, Pydantic schemas in doc_schemas.py, config
  in settings.py).
- routers/memory_chat.py: /api/chat, /api/memory/{user_id},
  /api/aggregate/{user_id} (HW6 Part 2; logic in memory_service.py).
- routers/bikeshare.py: /bikeshare page + POST /api/bikeshare/run, the Bay
  Wheels membership-vs-pay-per-use ReAct agent (HW7 Part 4).
This file only wires up the middleware/routers and serves the agent pipeline.

Runs on PORT_BASE = 8000 + (7117 mod 900) = 8817.
"""
from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pymongo.errors import PyMongoError
from starlette.middleware.sessions import SessionMiddleware

THIS_DIR = Path(__file__).resolve().parent
CODE_DIR = THIS_DIR.parent

sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(CODE_DIR))
import memory_service  # noqa: E402
import token_counter  # noqa: E402
from agents_demo import (
    InspectionSubmission,
    ModelClient,
    ModelClientError,
    PublishOutput,
    run_pipeline,
)

import mongo  # noqa: E402
from routers.auth import router as auth_router
from routers.bikeshare import router as bikeshare_router
from routers.doc_inspections import router as doc_inspections_router
from routers.home import router as home_router
from routers.inspectors import router as inspectors_router
from routers.memory_chat import router as memory_chat_router
from routers.nplus1 import router as nplus1_router
from routers.records import router as records_router
from routers.token_auth import router as token_auth_router

PORT_BASE = 8000 + (7117 % 900)  # 8817

# HW6 routes get the JSON body check + flattened validation errors below; the
# HW4/HW5 routes keep FastAPI's default behavior.
HW6_PREFIXES = ("/api/doc/", "/api/chat", "/api/memory/", "/api/aggregate/")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Create the s7117_doc collections/validators/indexes if MongoDB is up;
    # the MySQL-backed routes still work when it is not.
    try:
        mongo.ensure_collections()
    except PyMongoError as exc:
        print(f"[startup] MongoDB not available ({type(exc).__name__}); HW6 routes will return 503")
    # Load the embedding model + tokenizer now so the first /api/chat latency
    # measures the chat, not a model load.
    try:
        memory_service.embed(["warm-up"])
        token_counter.count_tokens("warm-up")
    except Exception as exc:  # noqa: BLE001 - offline: loaded lazily on first use instead
        print(f"[startup] memory warm-up skipped ({type(exc).__name__})")
    yield


# Create FastAPI app
app = FastAPI(title="Restaurant Inspection Records API", lifespan=lifespan)

# Local dev only - the React dev server (Vite, :5173) calls this API with a
# bearer token; the origins stay listed explicitly (allow_credentials can't be
# combined with a "*" origin).
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

# Secret key for session signing - set a real one via env in any deployment; this default
#  is only for local dev, since it can't sign anything securely
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



# JSON parsing middleware for the HW6 routes: a body must be declared as
# application/json (415 otherwise) and must parse as JSON (400 otherwise),
# before the route's Pydantic model validates it.
@app.middleware("http")
async def json_body_middleware(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH") and request.url.path.startswith(HW6_PREFIXES):
        if "application/json" not in request.headers.get("content-type", ""):
            return JSONResponse(status_code=415, content={
                "error": "unsupported_media_type", "detail": "Send the request body as application/json"})
        body = await request.body()
        try:
            json.loads(body or b"null")
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": "malformed_json", "detail": str(exc)})
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    if not request.url.path.startswith(HW6_PREFIXES):
        return await request_validation_exception_handler(request, exc)
    errors = [{"field": ".".join(str(p) for p in e["loc"] if p != "body") or "body",
               "message": e["msg"], "type": e["type"],
               **({"allowed": e["ctx"]["expected"]} if "expected" in e.get("ctx", {}) else {})}
              for e in exc.errors()]
    return JSONResponse(status_code=422, content={"error": "validation_error", "detail": errors})


@app.exception_handler(PyMongoError)
async def mongo_error_handler(_request: Request, exc: PyMongoError):
    return JSONResponse(status_code=503, content={"error": "database_unavailable",
                                                  "detail": f"MongoDB error: {type(exc).__name__}"})


@app.exception_handler(Exception)
async def server_error_handler(_request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": "internal_server_error", "detail": type(exc).__name__})


# Register routes
app.include_router(home_router)
app.include_router(auth_router)
app.include_router(token_auth_router)
app.include_router(nplus1_router)
app.include_router(records_router)
app.include_router(inspectors_router)
app.include_router(doc_inspections_router)
app.include_router(memory_chat_router)
app.include_router(bikeshare_router)

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
