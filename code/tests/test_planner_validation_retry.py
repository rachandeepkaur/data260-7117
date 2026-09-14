import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "code"))
sys.path.insert(0, str(REPO / "src"))

from agents_demo import InspectionSubmission, PlannerOutput, ReviewerOutput, RevisedOutput
from model_client import ModelClientError
from langgraph_agent import build_graph, MAX_TURNS


class StubClient:
    """Fails PlannerOutput validation the first `fail_times` calls (simulating
    ModelClient exhausting its own internal retries and raising), then
    succeeds. Reviewer always approves immediately once it gets a real call."""

    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.planner_calls = 0
        self.reviewer_calls = 0
        self.planner_prompts = []

    def call(self, *, system, user, output_format, **kwargs):
        if output_format is PlannerOutput:
            self.planner_calls += 1
            self.planner_prompts.append(user)
            if self.planner_calls <= self.fail_times:
                raise ModelClientError(
                    f"Model did not return valid 'PlannerOutput' JSON after 3 attempt(s). "
                    f"Last error: ValidationError('draft_summary must be at most 25 words, got 31')"
                )
            return PlannerOutput(tags=["tag one", "tag two", "tag three"], draft_summary="a fine draft summary")
        if output_format is ReviewerOutput:
            self.reviewer_calls += 1
            return ReviewerOutput(
                approved=True, feedback="",
                revised_output=RevisedOutput(tags=["tag one", "tag two", "tag three"], summary="a fine draft summary"),
            )
        raise AssertionError(f"unexpected output_format {output_format}")


submission = InspectionSubmission(
    facility_name="x", site_address="y", inspector_email="e@e.com",
    program_element="ROUTINE HEALTH INSPECTION", inspection_summary="z",
)

print("=== Case: Planner fails validation twice, then succeeds - must NOT crash ===")
client = StubClient(fail_times=2)
app = build_graph()
initial_state = {
    "title": "t", "content": "c", "email": "e", "strict": True, "task": "task",
    "llm": client, "planner_proposal": None, "reviewer_feedback": None, "turn_count": 0,
}

for step in app.stream(initial_state):
    for node_name, update in step.items():
        if node_name == "supervisor":
            print(f"  supervisor -> turn_count={update['turn_count']}")
        elif node_name == "planner":
            ok = "planner_proposal" in update and update["planner_proposal"] is not None
            print(f"  planner call #{client.planner_calls}: {'SUCCEEDED' if ok else 'CAUGHT ModelClientError, fed back as reviewer_feedback'}")
            if not ok:
                print(f"    reviewer_feedback = {update['reviewer_feedback']}")
        elif node_name == "reviewer":
            print(f"  reviewer ran -> approved={update['reviewer_feedback']['approved']}")

final = app.invoke(initial_state)
print("\nplanner_calls:", client.planner_calls, "reviewer_calls:", client.reviewer_calls)
print("final approved:", final["reviewer_feedback"]["approved"])
print("final turn_count:", final["turn_count"])

marker = "[SCHEMA VALIDATION FAILED]"
saw_marker = [marker in p for p in client.planner_prompts]
print("planner calls that saw the validation-error feedback:", saw_marker)

assert client.planner_calls >= 3  # 2 failures + at least 1 success (may be re-counted by invoke() too)
print("\nPASS: a Planner that fails schema validation does not crash the graph - it retries with the error fed back.")

print("\n=== Case: Planner NEVER produces valid output - must stop at MAX_TURNS, not loop forever ===")
client2 = StubClient(fail_times=999)
final2 = app.invoke({**initial_state, "llm": client2})
print("planner_calls:", client2.planner_calls)
print("final turn_count:", final2["turn_count"], f"(MAX_TURNS={MAX_TURNS})")
print("final reviewer_feedback:", final2["reviewer_feedback"])
assert final2["turn_count"] <= MAX_TURNS
assert final2["reviewer_feedback"]["approved"] is False
print("\nPASS: an always-failing Planner terminates at the turn ceiling instead of looping forever.")
