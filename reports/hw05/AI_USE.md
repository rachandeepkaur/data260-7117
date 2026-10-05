# AI Use

### 1. What I used an AI assistant for, and what I did myself

AI assistant (Claude Code, in VS Code):

- Drafted the HW5 migration (inspectors table, FK with ON DELETE RESTRICT), the inspectors router and
the extended records router, and the Redux Toolkit slices/thunks for the React client.
- Chose the related entity (inspectors) and reviewed the safety rule (small-group suppression).
- Drafted the report skeleton, METRICS tables and this file.

What I did myself:

- Ran the migration, the API, the React client and every `make` target on my machine, and took all
Postman, database, MCP Inspector, Redux and terminal screenshots.
- Wrote the two MCP servers, the shared tool layer (envelope, retry/timeout policy, seeded fault
injection, `execute_tool`, safety rule, agent loop), the offline test runner, the experiment
scripts, `verify.py` and the Makefile targets.
- Read the generated code and checked the outputs against the database (see 2–3).



### 2. One AI-produced output that was wrong, and one thing I verified independently

**Wrong:** the Makefile pinned the MCP SDK for `mcp dev` as `--with "mcp[cli]>=1.9,<2"`. That works
with the new Inspector 2.x, but the classic Inspector (0.22, which shows inputs and output together
for screenshots) could never connect: it stayed "Disconnected" with no error in the UI.

**Verified independently:** the agent's final answers. For each scenario I compared the answer with
the tool result logged in `agent_runs.jsonl` — e.g. the detail run's "Bay BBQ, violation code 29,
score 98, inspector Elena Rivera (Alum Rock)" matches the `get_inspection` result for INS-000042.

### 3. How I detected the problem / verified the result

The Inspector proxy log showed the server being started with
`args=run,--with,mcp[cli],[object Object],=1.9,,[object Object],2,...`. The classic Inspector splits
the argument string like a shell, so `>` and `<` were parsed as redirection operators and the
version pin was destroyed before `uv` ever ran.

### 4. What I changed and why it works now

The pin is now written `mcp[cli]~=1.9`, which means the same thing (≥ 1.9 and < 2) without `<` or
`>`. Both `make mcp-*` (`mcp dev`) and `make inspector-*` (classic Inspector) now connect and run
tools; I confirmed it by running `meals_by_ingredient` (chicken) and the rejected
`search_inspections` (limit 500) call in the Inspector.