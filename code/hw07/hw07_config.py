"""HW7 personal configuration (Section 0) and shared paths.

Section 0 values are fixed for the semester, so they are re-exported from
code/hw04/hw04_config.py; the JWT settings live in
code/web_application/security.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_CODE_DIR = Path(__file__).resolve().parent.parent
for _p in (_CODE_DIR / "hw04", _CODE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from hw04_config import (  # noqa: E402,F401
    BASE_URL,
    DB_NAME,
    DOMAIN_ID,
    LOCAL_MODEL,
    MYSQL_ADMIN_URL,
    PORT_BASE,
    PREFIX,
    REPO_ROOT,
    SEED,
    SID4,
    VERIFY_SEED,
    WEB_APP_DIR,
    use_web_app_imports,
)

HW = 7
HW07_CODE_DIR = REPO_ROOT / "code" / "hw07"
REPORT_DIR = REPO_ROOT / "reports" / "hw07"
RAW_DIR = REPORT_DIR / "raw"
CASES_DIR = REPORT_DIR / "cases"
FIXTURES_DIR = REPORT_DIR / "fixtures"
RUN_LOG = REPORT_DIR / "RUN_LOG.txt"  # appended to by the Makefile targets (tee)

# Part 1 - one MySQL user per role, created by migrate.py (dev-only passwords).
ROLE_USERS = {
    "reader": f"{PREFIX}_reader",
    "writer": f"{PREFIX}_writer",
    "moderator": f"{PREFIX}_moderator",
}
ROLE_PASSWORD = os.getenv("HW07_ROLE_PASSWORD", "Role!7117")

# Part 2 / 3 - model settings shared by every agent run.
AGENT_TEMPERATURE = 0.6
RELIABILITY_ATTEMPTS_PER_TASK = 7   # 3 tasks x 7 = 21 attempts (>= 20 required)
COMPARISON_RUNS_PER_TASK = 3        # Part 3: same (task, seed) pairs for both loops

# Part 4 - Bay Wheels (SF Bay Area).
BIKESHARE_CITY = "Bay Wheels (SF Bay Area)"
PRICING_URL = "https://www.lyft.com/bikes/bay-wheels/pricing"
TRIP_DATA_INDEX = "https://s3.amazonaws.com/baywheels-data/"
BIKESHARE_CASES_DIR = CASES_DIR / "bikeshare"
BIKESHARE_RAW_DIR = RAW_DIR / "bikeshare"
