# AI Use

> Draft — edit so every statement matches what you actually did yourself.

### 1. What I used an AI assistant for, and what I did myself

AI assistant (Claude Code, in VS Code):

- Drafted the MongoDB document API (schemas, PyMongo connection, `$jsonSchema` validators, routes),
  the chat-memory service and endpoints, the Part 3 experiment runner and metrics script, the
  file-based memory package (loading, consolidation rules, consolidator, commands), the offline tests
  and `verify.py`.
- Drafted the report skeleton, `memory_probes.yaml`, the 30-message conversation and this file.

What I did myself:

- Ran MongoDB, the API, the experiments and every `make` target on my machine, and took all
  Compass, Postman and terminal screenshots.
- Reviewed the generated code and checked the results against MongoDB and the raw files.

### 2. One AI-produced output that was wrong, and one thing I verified independently

**Wrong:** the first consolidator used a single model pass. In run 1 it left 3 of the 5 planted
contradictions (supervisor, district, report format) with *both* versions under "Facts", and the
audit did not notice, because it only reviewed resolutions the model claimed to have made.

**Verified independently:** the Part 3 latency data. The Mac went into idle sleep during the first
SHORT_TERM_N=12 run, which would have put about 6.5 hours into one turn's latency.

### 3. How I detected the problem / verified the result

The grader in `code/hw06/consolidation_test.py` compares the output with the ground truth in
`memory_consolidation/expected.yaml`. It reported `unresolved_both_kept` for three topics, and
reading `MEMORY.consolidated.md` confirmed that "Mark Chen" and "Dana Whitfield" were both current
facts. The sleep was found because the run log stopped at 03:20; `pmset -g log` showed
"Entering Sleep ... 03:20:41" and a wake at 09:49.

### 4. What I changed and why it works now

- Added a second "conflict check" pass in `code/file_memory/consolidation.py`. The model re-reads
  the consolidated facts and names contradictions that remain. Each one is moved to "Resolved
  contradictions" and audited against the newest-wins / confirmed-wins rule. Run 2 resolved 3 of 5
  correctly, and the one it got wrong (supervisor) is flagged "AUDIT: possibly incorrect" instead
  of being silent. District is still undetected, so this is improved, not solved; both runs are
  kept in the repo (`raw/consolidation_run1/`).
- Discarded the partial SHORT_TERM_N=12 run, re-ran it under `caffeinate` so the machine cannot
  sleep, and noted the interruption in `RUN_LOG.txt`.
