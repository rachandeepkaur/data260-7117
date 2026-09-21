# HW02 Adversarial Case

## The input

`reports/hw02/cases/adversarial_input.json` pairs two things:

1. A fact-dense `inspection_summary` describing **nine distinct violations** (cold-holding temperature, missing signage, cracked cutting board, expired test strips, unlabeled chemicals, broken freezer seal, live pest activity, blocked hand sink, incomplete staff certifications).
2. A `task` field that explicitly demands exhaustive, uncompressed detail:
   > "Provide an exhaustive, fully detailed narrative summary that individually documents every single violation observed, including exact temperatures, counts, and specific corrective actions required for each item - do not omit or generalize any of the details, and do not compress multiple violations into a single phrase."

This directly contradicts the hard structural constraints baked into the pipeline: `PLANNER_SYSTEM` demands "a concise, one-sentence summary... 25 words or fewer," `PlannerOutput` enforces that limit with a Pydantic `field_validator`, and `REVIEWER_SYSTEM_STRICT` grades against the same 25-word rule plus "exactly 3 tags." The `task` field is free text with no validation of its own — nothing stops a well-meaning user (or another upstream agent) from writing a task that's fundamentally incompatible with the schema it feeds into.

## Observed result: 5/5 runs hit the ceiling (100%)

| Run | Outcome | Final turn count | Planner attempts | Planner schema-validation failures | Reviewer rejections | Latency |
|---|---|---|---|---|---|---|
| 1 | HIT CEILING | 8 | 5 | 3 | 2 | 308.8s |
| 2 | HIT CEILING | 8 | 5 | 2 | 2 | 225.8s |
| 3 | HIT CEILING | 8 | 5 | 3 | 2 | 977.6s |
| 4 | HIT CEILING | 8 | 5 | 3 | 2 | 270.8s |
| 5 | HIT CEILING | 8 | 5 | 3 | 2 | 241.5s |

- **Hit rate: 5/5 (100%)** — exceeds the "ideally ≥4/5" target. This is reported honestly because it's what actually happened; it was not assumed in advance (the design was validated with a single smoke-test run first, which also hit the ceiling, before committing to the full 5-run experiment).
- Every run stopped at exactly `turn_count=8` (`MAX_TURNS`), never exceeding it and never reaching approval — consistent with every other experiment in this project (the ceiling is always respected).
- **Latency is highly variable and occasionally extreme**: mean 404.9s (~6.75 min), but run 3 alone took 977.6s (~16.3 min) — over 4x the fastest run (225.8s). This is itself a real operational risk: an adversarial input doesn't just fail, it can fail *slowly and unpredictably*.
- Full per-step transcripts: `reports/hw02/ADVERSARIAL_RUN_LOG.txt`. Raw per-run data: `reports/hw02/raw/adversarial_runs.json` / `.csv`.

## Why it causes trouble

Tracing the transcripts, two distinct failure modes both stem from the same root conflict:

1. **The Planner sometimes produces schema-valid output that the Reviewer rejects anyway.** In run 1, the Planner's first draft was a genuinely valid 22-word summary with 3 tags — well within every Pydantic constraint. The Reviewer rejected it with: *"Summary exceeds 25 words. Tags are inaccurate and incomplete."* That's factually wrong about the word count (22 ≠ over 25). The real objection is the task's demand for exhaustiveness, but the Reviewer expresses it using the canned "exceeds 25 words" language from its own criteria template, because that's the only rejection vocabulary its prompt gives it for "not enough detail." **The Reviewer's stated reasoning cannot be trusted at face value in this case** — it's rationalizing a task-driven objection as a schema-driven one.

2. **The Planner sometimes tries to satisfy the task literally and blows past the word limit**, which our own `field_validator` on `draft_summary` catches directly (`FAILED VALIDATION` in the transcript, 2-3 times per run) — `ModelClient`'s internal JSON-repair retries exhaust themselves, `planner_node` catches the resulting `ModelClientError`, and the graph correctly retries rather than crashing (the retry-with-feedback mechanism built earlier is working exactly as designed). But the retry doesn't actually resolve anything, because the *next* attempt faces the exact same unresolvable instruction conflict.

The graph's control flow, validation, and turn ceiling are all behaving correctly here — the trouble isn't a bug in the pipeline, it's that an unconstrained `task` field can hand the Planner and Reviewer two simultaneously-impossible instructions, and nothing in either system prompt tells the model which one wins.

## Proposed fix

Add an explicit priority rule to both `PLANNER_SYSTEM` and `REVIEWER_SYSTEM_STRICT`/`REVIEWER_SYSTEM_LENIENT` in `code/langgraph_agent.py`, stating that the structural output limits always outrank the free-text `task`:

> "The output limits above (exactly 3 tags of 3-30 characters each, and a summary of at most 25 words) are hard requirements that always take priority over the Task instruction. If the Task asks for more detail, exhaustiveness, or additional items than these limits allow, comply with the limits anyway — summarize as concisely as possible and omit excess detail rather than violating the tag count or word limit."

This doesn't require a new state field or graph change — it's a prompt-only fix that gives the model an explicit resolution rule for exactly the conflict this adversarial case exposes, instead of leaving it to guess (and instead of letting the Reviewer keep rejecting valid output while mischaracterizing why). It's proposed but not yet implemented or re-tested against this adversarial input — doing so would need another 5-run pass (each run costs several minutes) to confirm it actually lowers the ceiling-hit rate.
