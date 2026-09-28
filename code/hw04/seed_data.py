"""Seed 5,000 inspections + 200 related violations with SEED = 7117 (HW4 Part 3.1-3.2).

    python code/hw04/seed_data.py

Deterministic: the same SEED always produces byte-identical rows (a SHA-256
of the generated data is printed and saved to raw/seed_summary.json).
Existing inspections/violations are truncated first so ids restart at 1.

The 200 violations are assigned to random inspections among ids 1-250, so
the first pages the N+1 benchmark reads (offset 0, page sizes 10/50/200)
actually contain related rows to load.
"""
from __future__ import annotations

import hashlib
import json
import random
from datetime import date, timedelta

from sqlalchemy import insert, select, text

from hw04_config import (
    DEMO_USER_EMAIL,
    DEMO_USER_NAME,
    DEMO_USER_PASSWORD,
    RAW_DIR,
    SEED,
    use_web_app_imports,
)

use_web_app_imports()
from database import SessionLocal, engine  # noqa: E402
from models import Inspection, User, Violation  # noqa: E402
from security import hash_password  # noqa: E402

N_INSPECTIONS = 5000
N_VIOLATIONS = 200
VIOLATION_TARGET_MAX_ID = 250

NAME_WORDS_A = ["GOLDEN", "LUCKY", "SUNNY", "HAPPY", "OLD TOWN", "BLUE", "JADE", "ROYAL", "LITTLE",
                "GREEN", "SILVER", "RED", "BAY", "VALLEY", "MISSION", "EL", "LA", "CASA", "PHO", "TAQUERIA"]
NAME_WORDS_B = ["KITCHEN", "WOK", "GRILL", "CAFE", "BISTRO", "TACOS", "DINER", "BAKERY", "NOODLE HOUSE",
                "PIZZERIA", "SUSHI", "BBQ", "DELI", "CANTINA", "TEA HOUSE", "BURGERS", "RAMEN", "CURRY HOUSE"]
STREETS = ["BRANHAM LN", "E SANTA CLARA ST", "STORY RD", "TULLY RD", "KING RD", "N 1ST ST", "S BASCOM AVE",
           "STEVENS CREEK BLVD", "CAPITOL EXPY", "BLOSSOM HILL RD", "SARATOGA AVE", "ALMADEN EXPY",
           "MONTEREY RD", "WINCHESTER BLVD", "MCKEE RD", "SENTER RD", "HOSTETTER RD", "CAMDEN AVE"]
ZIPS = ["95110", "95111", "95112", "95116", "95117", "95118", "95120", "95122", "95123", "95124",
        "95125", "95126", "95127", "95128", "95131", "95132", "95133", "95136", "95148"]

# (code, description, severity, points) - modeled on the CA Retail Food Code
# violation categories used in the corpus inspection reports.
VIOLATION_TYPES = [
    ("1b", "Food safety certificate expired", "MINOR", 2),
    ("6", "Adequate handwashing facilities not supplied or accessible", "MAJOR", 4),
    ("7", "Improper hot holding temperature (below 135F)", "MAJOR", 4),
    ("8", "Improper cold holding temperature (above 41F)", "MAJOR", 4),
    ("9", "Improper cooling methods", "MAJOR", 4),
    ("14a", "Food contact surfaces not cleaned and sanitized", "MINOR", 2),
    ("23", "Vermin or animal contamination observed", "MAJOR", 4),
    ("29", "Toxic substances not properly identified or stored", "MINOR", 2),
    ("30b", "Food containers not labeled", "MINOR", 1),
    ("33", "Nonfood-contact surfaces not clean", "MINOR", 1),
    ("35", "Equipment/utensils not approved or in poor repair", "MINOR", 1),
    ("41", "Plumbing not in good repair", "MINOR", 1),
]


def generate(rng: random.Random) -> tuple[list[dict], list[dict]]:
    inspections = []
    for i in range(1, N_INSPECTIONS + 1):
        fa_number = f"FA{rng.randint(100000, 999999):07d}"
        name = f"{rng.choice(NAME_WORDS_A)} {rng.choice(NAME_WORDS_B)}"
        address = f"{rng.randint(10, 9999)} {rng.choice(STREETS)}, SAN JOSE, CA {rng.choice(ZIPS)}"
        inspections.append({"id": i, "facility_name": f"{fa_number} - {name}", "site_address": address})

    start = date(2025, 1, 1)
    violations = []
    for j in range(1, N_VIOLATIONS + 1):
        code, description, severity, points = rng.choice(VIOLATION_TYPES)
        violations.append({
            "id": j,
            "inspection_id": rng.randint(1, VIOLATION_TARGET_MAX_ID),
            "violation_code": code,
            "description": description,
            "severity": severity,
            "points_deducted": points,
            "observed_on": start + timedelta(days=rng.randint(0, 600)),
        })
    return inspections, violations


def main() -> None:
    rng = random.Random(SEED)
    inspections, violations = generate(rng)
    digest = hashlib.sha256(
        json.dumps([inspections, violations], default=str, sort_keys=True).encode()
    ).hexdigest()

    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        conn.execute(text("TRUNCATE TABLE inspection_violations"))
        conn.execute(text("TRUNCATE TABLE inspections"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        conn.execute(insert(Inspection), inspections)
        conn.execute(insert(Violation), violations)

    with SessionLocal() as db_session_basede26:
        if db_session_basede26.execute(select(User).where(User.email == DEMO_USER_EMAIL)).scalar_one_or_none() is None:
            db_session_basede26.add(User(name=DEMO_USER_NAME, email=DEMO_USER_EMAIL,
                                         password_hash=hash_password(DEMO_USER_PASSWORD)))
            db_session_basede26.commit()
            print(f"Created demo user {DEMO_USER_EMAIL}")

    with engine.connect() as conn:
        n_insp = conn.execute(text("SELECT COUNT(*) FROM inspections")).scalar()
        n_viol = conn.execute(text("SELECT COUNT(*) FROM inspection_violations")).scalar()
        n_with = conn.execute(text("SELECT COUNT(DISTINCT inspection_id) FROM inspection_violations")).scalar()
        per_page = {
            size: conn.execute(
                text("SELECT COUNT(*) FROM inspection_violations WHERE inspection_id <= :n"), {"n": size}
            ).scalar()
            for size in (10, 50, 200)
        }

    summary = {
        "seed": SEED,
        "inspections": n_insp,
        "violations": n_viol,
        "inspections_with_violations": n_with,
        "violations_in_first_page": {str(k): v for k, v in per_page.items()},
        "generated_data_sha256": digest,
        "sample_inspections": inspections[:3],
        "sample_violations": [{**v, "observed_on": v["observed_on"].isoformat()} for v in violations[:3]],
    }
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "seed_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
