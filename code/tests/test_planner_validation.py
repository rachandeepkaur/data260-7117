import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agents_demo import PlannerOutput
from pydantic import ValidationError

TWENTY_SIX_WORDS = " ".join(f"word{i}" for i in range(26))
TWENTY_FIVE_WORDS = " ".join(f"word{i}" for i in range(25))

cases = [
    ("VALID: exactly 3 tags, 3-30 chars each, summary = 25 words", dict(
        tags=["health inspection", "food safety", "facility compliance"],
        draft_summary=TWENTY_FIVE_WORDS,
    ), True),
    ("INVALID: only 2 tags", dict(
        tags=["health inspection", "food safety"],
        draft_summary="A valid short summary under the limit.",
    ), False),
    ("INVALID: 4 tags", dict(
        tags=["health", "food safety", "facility compliance", "extra tag"],
        draft_summary="A valid short summary under the limit.",
    ), False),
    ("INVALID: tag too short (<3 chars)", dict(
        tags=["ok", "food safety", "facility compliance"],
        draft_summary="A valid short summary under the limit.",
    ), False),
    ("INVALID: tag too long (>30 chars)", dict(
        tags=["health inspection", "food safety", "x" * 31],
        draft_summary="A valid short summary under the limit.",
    ), False),
    ("INVALID: summary is 26 words (over the 25-word limit)", dict(
        tags=["health inspection", "food safety", "facility compliance"],
        draft_summary=TWENTY_SIX_WORDS,
    ), False),
]

print("=" * 70)
print("Pydantic validation test: PlannerOutput")
print("=" * 70)

all_passed = True
for label, payload, should_succeed in cases:
    try:
        result = PlannerOutput(**payload)
        outcome = "ACCEPTED"
        detail = f"tags={result.tags}"
        ok = should_succeed
    except ValidationError as exc:
        outcome = "REJECTED"
        detail = exc.errors()[0]["msg"]
        ok = not should_succeed

    status = "PASS" if ok else "FAIL"
    all_passed &= ok
    print(f"\n[{status}] {label}")
    print(f"  -> {outcome}: {detail}")

print("\n" + "=" * 70)
print("ALL CHECKS PASSED" if all_passed else "SOME CHECKS FAILED")
print("=" * 70)
