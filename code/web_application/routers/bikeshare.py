"""Bike-share membership agent UI + API (HW7 Part 4).

    GET  /bikeshare            the page: CSV upload, pricing URL, Run; timeline + results panels
    POST /api/bikeshare/run    multipart {file: trips CSV, pricing_url} -> agent result JSON

Each run's evidence is saved under reports/hw07/raw/bikeshare/runs/<timestamp>_<csv sha8>/:
result.json, the exact pricing-page text the tools used (pricing_snapshot.txt
+ the raw HTML) and snapshot_meta.json (URL, access time, SHA-256), so later
changes to the public page cannot change the evidence.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

CODE_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = CODE_DIR.parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from bikeshare_agent import run_bikeshare_agent  # noqa: E402

PAGE = Path(__file__).resolve().parent.parent / "templates" / "bikeshare.html"
RUNS_DIR = REPO_ROOT / "reports" / "hw07" / "raw" / "bikeshare" / "runs"
SUMMARIES_DIR = REPO_ROOT / "reports" / "hw07" / "raw" / "bikeshare"
MAX_CSV_BYTES = 20_000_000

router = APIRouter(tags=["bikeshare"])


def save_run_evidence(result: dict, csv_bytes: bytes, label: str | None = None) -> Path:
    """Write result.json + the pricing snapshot(s) for one run; returns the run folder."""
    csv_sha = hashlib.sha256(csv_bytes).hexdigest()
    scenario = label
    for summary in SUMMARIES_DIR.glob("*_trip_summary.json"):
        data = json.loads(summary.read_text())
        if data.get("csv_sha256") == csv_sha:
            scenario = scenario or data["scenario"]
    folder = RUNS_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{scenario or 'upload'}_{csv_sha[:8]}"
    folder.mkdir(parents=True, exist_ok=True)
    registry = result.pop("_registry", None)
    metas = []
    for i, snap in enumerate((registry.snapshots.values() if registry else [])):
        suffix = "" if i == 0 else f"_{i}"
        (folder / f"pricing_snapshot{suffix}.txt").write_text(snap["text"], encoding="utf-8")
        (folder / f"pricing_snapshot{suffix}.html").write_text(snap["raw"], encoding="utf-8")
        metas.append({"url": snap["url"], "accessed_at": snap["accessed_at"], "text_sha256": snap["sha256"],
                      "html_sha256": snap["raw_sha256"], "text_file": f"pricing_snapshot{suffix}.txt",
                      "html_file": f"pricing_snapshot{suffix}.html"})
    (folder / "snapshot_meta.json").write_text(json.dumps(metas, indent=2))
    result.update(scenario=scenario, csv_sha256=csv_sha, evidence_dir=str(folder.relative_to(REPO_ROOT)))
    (folder / "result.json").write_text(json.dumps(result, indent=2, default=str))
    return folder


@router.get("/bikeshare", include_in_schema=False)
def bikeshare_page() -> FileResponse:
    """The single-page UI."""
    return FileResponse(PAGE)


@router.post("/api/bikeshare/run")
def run_bikeshare(file: UploadFile = File(...), pricing_url: str = Form(...)) -> dict:
    """Run the ReAct agent on the uploaded CSV and pricing URL (takes minutes on CPU)."""
    csv_bytes = file.file.read(MAX_CSV_BYTES + 1)
    if len(csv_bytes) > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="CSV larger than 20 MB")
    if not pricing_url.startswith(("https://", "http://")):
        raise HTTPException(status_code=422, detail="pricing_url must be an http(s) URL")
    try:
        result = run_bikeshare_agent(csv_bytes.decode("utf-8-sig"), pricing_url)
    except ValueError as exc:  # unreadable CSV / missing columns
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    save_run_evidence(result, csv_bytes)
    return result
