### Question 1: What you used an AI assistant for vs. what you did yourself
* **AI Assistant:** I Used AI to help me understand the assignment requirements and break down each part of the assignment into small understandable tasks. I have used AI to help me the write the code snippets and agent prompts (`langgraph_agent.py`'s `AgentState`, `planner_node`, `reviewer_node`, `supervisor_node`, `router_logic`, and the `StateGraph` wiring).
* **Self Effort:** I did my assignment step by step to understand the difference between LangChain and LangGraph — how LangGraph gives the ability to route control back through the Planner if the Reviewer rejects, and how a Supervisor node with a turn-count ceiling makes an otherwise-open-ended agent loop safe to run unattended.

### Question 2: One AI-produced output that was wrong/unsuitable, or one issue you independently verified / resolved with AI
* **Issue Encountered:** The AI's first `langgraph_agent.py` implementation technically matched the assignment's diagram text but not its intent: on a Reviewer rejection, `reviewer_node` kept `planner_proposal` populated (overwriting it with its own `revised_output`), so the Reviewer was quietly self-correcting the draft in place instead of the Supervisor ever sending control back to the Planner. A "loop proof" screenshot the AI produced showed `"Finished after 2 supervisor turn(s)"` with `approved: true` on the very first pass — I pointed out that wasn't loop evidence at all, since the Reviewer had approved immediately and the graph never had a reason to go back to the Planner.
* **AI Assistance:** The AI traced the bug to `reviewer_node` never clearing `planner_proposal`, which meant `router_logic`'s `"no proposal -> Planner"` branch could only ever fire once, on the very first Supervisor visit.

### Question 3: How you detected the problem or verified the result
* **Detection:** I read the AI's own captured terminal output and noticed the run finished in the minimum possible number of turns with immediate approval — not a loop, the simplest possible successful path — and said so before accepting it as evidence.
* **Verification:** After the fix (rejection now clears `planner_proposal` to `None`), the AI added a temporary test hook that forces `reviewer_node` to report `approved: False` for the first two review passes, ran it against the real local model, and I ran it myself too. The trace showed `turn_count` climbing 1→6, `planner_proposal` genuinely going to `null` after each rejection, and the regenerated draft's tags changing between rounds in response to the Reviewer's feedback — real evidence the Planner was re-invoked, not just re-reviewed. The hack was reverted immediately after (confirmed with `grep`), and a normal run reconfirmed real behavior (2 turns, genuinely approved).

### Question 4: What you changed and why it works now
* **Changes Made:** `reviewer_node` now returns `planner_proposal: None` on rejection instead of a self-corrected draft, and `planner_node` reads `reviewer_feedback` to fold the prior critique into its retry prompt so the next attempt actually addresses what was wrong. `MAX_TURNS` raised from 6 to 8 so a full 2-3 round retry demo can complete before hitting the safety cap mid-round.
* **Why It Works:** `router_logic`'s `"no proposal -> Planner"` branch is the only thing that can send control back to the Planner, and it's driven entirely by whether `planner_proposal` is falsy — clearing it on rejection is what makes the Supervisor -> Planner -> Supervisor -> Reviewer cycle actually happen, matching the assignment's diagram literally instead of just its outward shape.

## CRUD Records (Add / Update / Delete / Search)

### Question 1: What you used an AI assistant for vs. what you did yourself
* **AI Assistant:** Used AI to build the `/api/records` FastAPI endpoints (`GET`/`POST`/`PUT /{record_id}`/`DELETE /records/highest`) and wire the existing inspection form to double as the Add action, plus the client-side table rendering, search filter, and Update/Delete handlers in `script.js`.
* **Self Effort:** Decided the CRUD UI should live in the existing HW page (reusing the current form for Add) rather than a separate page, and that Update should target a record by an explicit ID field rather than a hardcoded "record 1" — the AI's first draft hardcoded ID 1, and I asked for it to be made dynamic.

### Question 2: One AI-produced output that was wrong/unsuitable, or one issue you independently verified / resolved with AI
* **Issue Encountered:** After the dynamic-ID change, submitting the Update form threw `Uncaught (in promise) TypeError: Cannot read properties of undefined (reading 'value')` in the browser console.
* **AI Assistance:** The AI traced this to `form.id.value` in the update handler — `id` is a reserved property on every `HTMLFormElement` (the form's own `id="updateForm"` attribute), so it shadows a same-named `<input name="id">` instead of exposing it. `form.id` was silently returning the string `"updateForm"`, not the input element.

### Question 3: How you detected the problem or verified the result
* **Detection:** I hit the real error in the browser while testing the Update form myself and pasted the exact console error back.
* **Verification:** The AI fixed it to read both fields via `document.getElementById(...)` instead (matching how the rest of the file already reads inputs) and confirmed with a headless-browser run: filled Record ID `1` / New Name, submitted, zero console errors, table updated to the new name, status message read "Record 1 updated."

### Question 4: What you changed and why it works now
* **Changes Made:** `script.js`'s `updateForm` handler now reads `document.getElementById("update_id").value` and `document.getElementById("update_facility_name").value` instead of `form.id.value`/`form.facility_name.value`.
* **Why It Works:** Named form-control shorthand (`form.<name>`) is shadowed by any built-in `HTMLFormElement` property of the same name (`id`, `action`, `method`, etc.) - `getElementById` has no such collision.

## Pydantic Validation & Retry-on-Failure

### Question 1: What you used an AI assistant for vs. what you did yourself
* **AI Assistant:** Asked the AI to verify a specific requirement ("exactly 3 string tags, 3-30 chars each, summary <=25 words") against the actual `PlannerOutput` model before assuming it was already satisfied.
* **Self Effort:** Reviewed the verification result and confirmed the gap was real before accepting the fix, and separately asked for the validation-failure retry behavior ("feed the error back into the Planner, bounded by the turn ceiling") as its own follow-up requirement.

### Question 2: One AI-produced output that was wrong/unsuitable, or one issue you independently verified / resolved with AI
* **Issue Encountered:** The AI found that `PlannerOutput.tags` only constrained the *list* to exactly 3 items (`min_length=3, max_length=3` on `List[str]`) - there was no per-tag character-length check, and "at most 25 words" on the summary was just descriptive text, never actually enforced by Pydantic. Separately, `planner_node`'s call to the LLM was unguarded: if schema validation kept failing even after the model client's own internal retries, it would raise straight through the node and crash the whole graph.
* **AI Assistance:** Added a per-tag `Annotated[str, Field(min_length=3, max_length=30)]` type and a `field_validator` for the word count on `draft_summary`; added a `try/except ModelClientError` in `planner_node` that reports the failure through the same `reviewer_feedback` slot a Reviewer rejection uses (no new `AgentState` key needed, since the assignment fixes that schema to 9 keys), so the existing "no proposal -> Planner" retry path handles it for free, bounded by `MAX_TURNS`.

### Question 3: How you detected the problem or verified the result
* **Detection:** Requested explicit verification of the stated requirement rather than assuming the original `Field(min_length=3, max_length=3)` already covered it.
* **Verification:** The AI wrote a deterministic test (`code/tests/test_planner_validation.py`) constructing 6 cases (1 valid + 5 invalid: too few/many tags, tag too short, tag too long, summary over 25 words) and confirmed Pydantic rejects every invalid one with the expected message. For the retry behavior, a second test (`code/tests/test_planner_validation_retry.py`) used a stub client that fails validation N times before succeeding, confirming the graph doesn't crash, the error text is genuinely read by the next Planner attempt, and an always-failing Planner still terminates at `MAX_TURNS` instead of looping forever. Both were re-run against the real local model afterward to confirm normal operation wasn't broken.

### Question 4: What you changed and why it works now
* **Changes Made:** `agents_demo.py`'s `PlannerOutput` gained the `Tag` type alias and word-count validator; `langgraph_agent.py`'s `planner_node` gained the `except ModelClientError` block described above.
* **Why It Works:** Schema correctness is now enforced at the type level (Pydantic rejects malformed LLM output immediately) instead of only being described in the prompt text, and a validation failure is treated as just another kind of "try again" signal the existing Planner-retry loop already knows how to handle - not a special case that needs its own new mechanism or state field.

## Experiments: Frozen-Input Classification & Turn-Ceiling Comparison

### Question 1: What you used an AI assistant for vs. what you did yourself
* **AI Assistant:** Use AI to write the experiemnts for turn-ceiling comparison and frozen-input experiment abd also used AI to write the METRICS.md and TURN_CEILING.md files.
* **Self Effort:** Verify both the turn-ceiling comparison and  frozen-input experiment.


