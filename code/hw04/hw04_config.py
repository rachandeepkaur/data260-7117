"""HW4 personal configuration (Section 0) and shared paths."""
from __future__ import annotations

import os
import sys
from pathlib import Path

SID4 = 7117
PORT_BASE = 8000 + (SID4 % 900)  # 8817
PREFIX = f"s{SID4}"               # s7117
SEED = SID4                        # 7117
VERIFY_SEED = 260000 + SID4        # 267117
DOMAIN_ID = SID4 % 8               # 5 -> local restaurant inspections
DB_NAME = f"{PREFIX}_rel"          # s7117_rel

LOCAL_MODEL = "qwen3:8b"

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WEB_APP_DIR = REPO_ROOT / "code" / "web_application"
HW04_CODE_DIR = REPO_ROOT / "code" / "hw04"
REPORT_DIR = REPO_ROOT / "reports" / "hw04"
RAW_DIR = REPORT_DIR / "raw"

BASE_URL = os.getenv("HW04_BASE_URL", f"http://127.0.0.1:{PORT_BASE}")

# Demo login seeded by seed_data.py (dev only).
DEMO_USER_NAME = "Rachandeep Kaur"
DEMO_USER_EMAIL = "demo@s7117.dev"
DEMO_USER_PASSWORD = os.getenv("HW04_DEMO_PASSWORD", "Inspect!7117")

# MySQL server admin connection used only by setup_db.py (Homebrew default:
# root with no password over localhost).
MYSQL_ADMIN_URL = os.getenv("MYSQL_ADMIN_URL", "mysql+pymysql://root:@127.0.0.1:3306/")
APP_DB_USER = "s7117_app"
APP_DB_PASSWORD = "s7117_dev_pw"


def use_web_app_imports() -> None:
    """Make code/web_application importable (database, models, ...)."""
    if str(WEB_APP_DIR) not in sys.path:
        sys.path.insert(0, str(WEB_APP_DIR))
