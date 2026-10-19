"""HW6 personal configuration (Section 0) and shared paths.

Section 0 values are fixed for the semester, so they are re-exported from
code/hw04/hw04_config.py; the web app's own settings live in
code/web_application/settings.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

_CODE_DIR = Path(__file__).resolve().parent.parent
for _p in (_CODE_DIR / "hw04", _CODE_DIR / "web_application", _CODE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from hw04_config import (  # noqa: E402,F401
    BASE_URL,
    DOMAIN_ID,
    LOCAL_MODEL,
    PORT_BASE,
    PREFIX,
    REPO_ROOT,
    SEED,
    SID4,
    VERIFY_SEED,
    WEB_APP_DIR,
)

HW = 6
MONGO_DB = f"{PREFIX}_doc"  # s7117_doc
HW06_CODE_DIR = REPO_ROOT / "code" / "hw06"
REPORT_DIR = REPO_ROOT / "reports" / "hw06"
RAW_DIR = REPORT_DIR / "raw"
RUN_LOG = REPORT_DIR / "RUN_LOG.txt"  # appended to by the Makefile targets (tee)
PROBES_FILE = REPORT_DIR / "memory_probes.yaml"
CONVERSATION_FILE = REPORT_DIR / "conversation_30.yaml"
AGENT_MD = REPO_ROOT / "AGENT.md"
MEMORY_MD = REPO_ROOT / "MEMORY.md"
MEMORY_TEST_DIR = REPORT_DIR / "memory_consolidation"

# Part 3 settings: (label, env overrides for the server process).
EXPERIMENT_SETTINGS = [
    ("SHORT_TERM_N=4", {"SHORT_TERM_N": "4", "MEMORY_POLICY": "none"}),
    ("SHORT_TERM_N=12", {"SHORT_TERM_N": "12", "MEMORY_POLICY": "none"}),
    ("SHORT_TERM_N=30", {"SHORT_TERM_N": "30", "MEMORY_POLICY": "none"}),
    ("Compression policy (N=12)", {"SHORT_TERM_N": "12", "MEMORY_POLICY": "compress"}),
]
INPUT_PRICE_PER_M = 1.0    # $ per 1M input tokens
OUTPUT_PRICE_PER_M = 5.0   # $ per 1M output tokens
N_CONVERSATIONS = 10_000
