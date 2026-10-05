"""Part 3 Q19: show the timeout + bounded exponential-backoff retry policy.

    make retry-demo                  (or: python code/hw05/retry_demo.py [--offline])

Three scripted cases through execute_tool's real code path (search_inspections
against MySQL, or the in-memory fixture with --offline):
    1. success on the first attempt
    2. failure on attempt 1 (a timeout), success after one retry
    3. failure on every allowed attempt -> clean {ok: false} result, no crash
Writes reports/hw05/raw/retry_demo.json.
"""
from __future__ import annotations

import argparse
import json
import time

from hw05_config import RAW_DIR

from domain_tools.executor import run_tool
from domain_tools.fixtures import make_fixture_repo
from domain_tools.repository import FaultyRepository, SqlRepository
from domain_tools.resilience import INTERACTIVE_POLICY, TransientError


class Script:
    """Per-attempt behavior: "ok", "fail" (connection error) or "slow" (hangs past the timeout)."""

    def __init__(self, steps: list[str]):
        self.steps = list(steps)
        self.decisions: list[str] = []

    def maybe_fail(self) -> None:
        step = self.steps.pop(0) if self.steps else "ok"
        self.decisions.append(step)
        if step == "fail":
            raise TransientError("injected fault: connection reset by peer")
        if step == "slow":
            time.sleep(INTERACTIVE_POLICY.timeout_s + 0.5)


CASES = [
    ("1. success on first attempt", ["ok"]),
    ("2. timeout on attempt 1, success after retry", ["slow", "ok"]),
    ("3. failure after all allowed retries", ["fail", "fail", "fail"]),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="use the in-memory fixture instead of MySQL")
    args = parser.parse_args()
    base = make_fixture_repo() if args.offline else SqlRepository()

    p = INTERACTIVE_POLICY
    print(f"Retry policy: max_attempts={p.max_attempts}, timeout={p.timeout_s}s per attempt, "
          f"backoff={p.base_delay_s}s x{p.multiplier:g} (cap {p.max_delay_s}s)")
    print(f"Backend: {'in-memory fixture' if args.offline else 'MySQL s7117_rel'}\n")

    out = []
    for title, steps in CASES:
        repo = FaultyRepository(base, Script(steps))
        envelope, trace = run_tool("search_inspections", {"query": "golden", "limit": 3}, repo=repo)
        print(f"== {title}")
        for a in trace.attempt_log:
            extra = f" -> backoff {a['backoff_s']}s" if "backoff_s" in a else ""
            err = f" ({a['error']})" if "error" in a else ""
            print(f"   attempt {a['attempt']}: {a['outcome']}{err} [{a['ms']:.1f} ms]{extra}")
        shown = {**envelope, "data": (f"<{envelope['data']['count']} results>" if envelope["ok"] else None)}
        print(f"   result after {trace.attempts} attempt(s), {trace.elapsed_ms:.1f} ms: {json.dumps(shown)}\n")
        out.append({"case": title, "script": steps, "attempts": trace.attempts, "elapsed_ms": trace.elapsed_ms,
                    "attempt_log": trace.attempt_log, "envelope": envelope})

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "retry_demo.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"wrote {RAW_DIR / 'retry_demo.json'}")


if __name__ == "__main__":
    main()
