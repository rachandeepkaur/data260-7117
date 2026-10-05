"""Small, fixed in-memory dataset for offline tests and `--offline` runs.

Shaped like s7117_rel after the HW5 migration. Inspector 1 has 6 inspections
(enough for an aggregate); facility "FA0206933 - YUMMY KITCHEN" appears once,
so an aggregate over it trips the small-group safety rule.
"""
from __future__ import annotations

from .repository import InMemoryRepository

INSPECTORS = [
    {"id": 1, "full_name": "Maria Nguyen", "district": "Willow Glen", "email": "maria.nguyen@sccgov-eh.org"},
    {"id": 2, "full_name": "Ravi Patel", "district": "Berryessa", "email": "ravi.patel@sccgov-eh.org"},
]

INSPECTIONS = [
    {"id": 1, "inspection_code": "INS-000001", "facility_name": "FA0206933 - YUMMY KITCHEN",
     "site_address": "1711 BRANHAM LN A9, SAN JOSE, CA 95118", "score": 92, "inspector_id": 1},
    {"id": 2, "inspection_code": "INS-000002", "facility_name": "FA0311021 - GOLDEN WOK",
     "site_address": "455 STORY RD, SAN JOSE, CA 95122", "score": 64, "inspector_id": 1},
    {"id": 3, "inspection_code": "INS-000003", "facility_name": "FA0412877 - LUCKY PHO",
     "site_address": "1020 TULLY RD, SAN JOSE, CA 95122", "score": 88, "inspector_id": 1},
    {"id": 4, "inspection_code": "INS-000004", "facility_name": "FA0500123 - GOLDEN BAKERY",
     "site_address": "88 N 1ST ST, SAN JOSE, CA 95112", "score": 100, "inspector_id": 1},
    {"id": 5, "inspection_code": "INS-000005", "facility_name": "FA0598812 - BLUE TACOS",
     "site_address": "2300 KING RD, SAN JOSE, CA 95122", "score": 76, "inspector_id": 1},
    {"id": 6, "inspection_code": "INS-000006", "facility_name": "FA0623311 - JADE NOODLE HOUSE",
     "site_address": "3150 SENTER RD, SAN JOSE, CA 95111", "score": 96, "inspector_id": 1},
    {"id": 7, "inspection_code": "INS-000007", "facility_name": "FA0700042 - GOLDEN GRILL",
     "site_address": "900 CAPITOL EXPY, SAN JOSE, CA 95136", "score": 81, "inspector_id": 2},
]

VIOLATIONS = [
    {"inspection_id": 2, "violation_code": "7", "description": "Improper hot holding temperature (below 135F)",
     "severity": "MAJOR", "points_deducted": 4},
    {"inspection_id": 2, "violation_code": "23", "description": "Vermin or animal contamination observed",
     "severity": "MAJOR", "points_deducted": 4},
    {"inspection_id": 3, "violation_code": "33", "description": "Nonfood-contact surfaces not clean",
     "severity": "MINOR", "points_deducted": 1},
]


def make_fixture_repo() -> InMemoryRepository:
    """A fresh copy each call, so one test can't leak state into the next."""
    return InMemoryRepository(
        [dict(r) for r in INSPECTIONS], [dict(r) for r in INSPECTORS], [dict(r) for r in VIOLATIONS]
    )
