"""Timeouts, bounded exponential-backoff retries, and seeded fault injection (Part 3).

call_with_retry(fn, policy) runs `fn` with a per-attempt timeout and retries
only *transient* failures (timeouts, dropped connections, injected faults).
Delays grow base, base*2, base*4, ... capped at max_delay; after
max_attempts it returns a failed RetryResult - it never raises.

Backoff has no random jitter on purpose: with a seeded FaultInjector the whole
run (which attempts fail, how long we wait) is reproducible from VERIFY_SEED.
"""
from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


class TransientError(Exception):
    """A failure worth retrying (connection reset, timeout, injected fault)."""


class ToolTimeout(TransientError):
    pass


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, (TransientError, TimeoutError, ConnectionError)):
        return True
    try:  # dropped/refused MySQL connections surface as OperationalError
        from sqlalchemy.exc import OperationalError

        return isinstance(exc, OperationalError)
    except ImportError:  # pragma: no cover
        return False


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3        # 1 try + 2 retries
    timeout_s: float = 2.0       # per attempt
    base_delay_s: float = 0.1    # wait before retry 1
    multiplier: float = 2.0
    max_delay_s: float = 1.0     # cap on any single wait

    def delay_before(self, retry_number: int) -> float:
        """Wait before retry `retry_number` (1-based)."""
        return min(self.max_delay_s, self.base_delay_s * self.multiplier ** (retry_number - 1))


INTERACTIVE_POLICY = RetryPolicy()
BATCH_POLICY = RetryPolicy(max_attempts=6, timeout_s=10.0, base_delay_s=0.5, max_delay_s=8.0)


@dataclass
class RetryResult:
    ok: bool
    value: Any = None
    error: Optional[str] = None
    attempts: int = 0
    attempt_log: list[dict] = field(default_factory=list)  # one entry per attempt
    elapsed_ms: float = 0.0


# Attempts run on worker threads so a hung call can be abandoned after
# timeout_s (Python can't kill the thread, but the caller stops waiting).
_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="tool-attempt")


def call_with_retry(
    fn: Callable[[], Any],
    policy: RetryPolicy = INTERACTIVE_POLICY,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> RetryResult:
    result = RetryResult(ok=False)
    start = time.perf_counter()
    for attempt in range(1, policy.max_attempts + 1):
        result.attempts = attempt
        t0 = time.perf_counter()
        try:
            value = _EXECUTOR.submit(fn).result(timeout=policy.timeout_s)
        except FutureTimeout:
            exc: BaseException = ToolTimeout(f"timed out after {policy.timeout_s:g}s")
        except Exception as e:  # noqa: BLE001 - classified below
            exc = e
        else:
            result.attempt_log.append({"attempt": attempt, "outcome": "success",
                                       "ms": round((time.perf_counter() - t0) * 1000, 3)})
            result.ok, result.value = True, value
            break

        transient = _is_transient(exc)
        entry = {"attempt": attempt, "outcome": "transient_error" if transient else "error",
                 "error": f"{type(exc).__name__}: {exc}",
                 "ms": round((time.perf_counter() - t0) * 1000, 3)}
        result.attempt_log.append(entry)
        result.error = entry["error"]
        if not transient or attempt == policy.max_attempts:
            break
        delay = policy.delay_before(attempt)
        entry["backoff_s"] = delay
        sleep(delay)
    result.elapsed_ms = round((time.perf_counter() - start) * 1000, 3)
    return result


class FaultInjector:
    """Fails each call with probability `rate`, decided by a seeded RNG, so
    the same (seed, rate) always gives the same success/failure sequence."""

    def __init__(self, rate: float, seed: int):
        self.rate = rate
        self.seed = seed
        self._rng = random.Random(seed)
        self.decisions: list[bool] = []  # True = injected failure

    def maybe_fail(self) -> None:
        fail = self._rng.random() < self.rate
        self.decisions.append(fail)
        if fail:
            raise TransientError(f"injected fault (rate={self.rate:g})")


class ScriptedFaults:
    """Fails exactly on the attempts listed in `script` (True = fail); used by
    the retry demo to force each of the three required outcomes."""

    def __init__(self, script: list[bool]):
        self.script = list(script)
        self.decisions: list[bool] = []

    def maybe_fail(self) -> None:
        fail = self.script.pop(0) if self.script else False
        self.decisions.append(fail)
        if fail:
            raise TransientError("injected fault (scripted)")
