"""HW5 personal configuration (Section 0) and shared paths.

The Section 0 values are the same as HW4 (they stay fixed for the semester),
so they are re-exported from code/hw04/hw04_config.py rather than redefined.
"""
from __future__ import annotations

import sys
from pathlib import Path

_CODE_DIR = Path(__file__).resolve().parent.parent
for _p in (_CODE_DIR / "hw04", _CODE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from hw04_config import (  # noqa: E402,F401
    APP_DB_PASSWORD,
    APP_DB_USER,
    BASE_URL,
    DB_NAME,
    DEMO_USER_EMAIL,
    DEMO_USER_NAME,
    DEMO_USER_PASSWORD,
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

HW = 5
HW05_CODE_DIR = REPO_ROOT / "code" / "hw05"
MCP_SERVERS_DIR = REPO_ROOT / "code" / "mcp_servers"
REPORT_DIR = REPO_ROOT / "reports" / "hw05"
RAW_DIR = REPORT_DIR / "raw"
RUN_LOG = REPORT_DIR / "RUN_LOG.txt"  # appended to by the Makefile targets (tee)
AGENT_LOG = RAW_DIR / "agent_runs.jsonl"

N_INSPECTORS = 20
FAILURE_RATES = (0.0, 0.2, 0.5)
CALLS_PER_RATE = 50

