# AI Use

> Draft: edit until every statement matches what you actually did yourself.

### 1. What I used an AI assistant for, and what I did myself

AI assistant (Claude Code, in VS Code):

- Drafted the JWT/role code (`security.py`, `routers/token_auth.py`, the role dependencies on the
  records/inspectors routes), the HW7 users migration, and the React client change to bearer tokens.
- Drafted the hand-written agent loop (`code/agent_loop/`), the native tool-call extension of the HW1
  adapter, the fixed-task verifiers, the oracle, the unsupported-claim check and the Reflexion loop.
- Drafted the Bay Wheels ReAct agent, its three MRKL tools and the `/bikeshare` UI, the scenario builder,
  the hostile fixture and threat model, the file tools and safety gate, the offline tests, `verify.py`,
  the experiment scripts and this report's skeleton.

What I did myself:

- Ran MySQL, the API, Ollama and every `make` target on my machine, and took all screenshots.
- Chose Bay Wheels, checked the pricing page and the trip-data source in a browser, and reviewed the
  generated code, the raw results and the verifier false rejections against the database.
- Did the lint/pre-commit demo commits.

### 2. One AI-produced output that was wrong, and one thing I verified independently

**Wrong:** the first draft of `is_destructive` used a short regex deny-list (`rm\s+-rf`, `^sudo`, ...) and
matched `SAFE_PREFIXES` against the start of the whole command. `ls; rm -fr ./build` was **allowed**: it
starts with the safe prefix `ls`, and `-fr` does not match `-rf`. A related bug in the next version:
`sudo rm -rf x` was flagged only for privilege escalation, because the recursion into the command after
`sudo` dropped its flags.

**Verified independently:** the Bay Wheels pricing text the agent sees. The first text extraction
flattened the page's comparison grid into a list of rates, such as "30 min free, then $0.19/min",
"45 min free, then $0.17/min" and "Free unlocks + $0.17/min", with nothing tying each rate to a plan. A
model could not tell which rate belonged to the month pass.

### 3. How I detected the problem / verified the result

- The 10-command safety-gate test (`make file-tools-hw07`) runs every command through both the first-draft
  gate and the final gate. The first draft printed `allow` for `ls; rm -fr ./build`, an expected block. I
  caught the `sudo` flag bug by running `confirm_bash` on a list of variants and checking the reported
  categories.
- For the pricing page, I compared the extracted text with the live page in a browser and then read the
  page HTML. The comparison grid is built from `<div idx="0..5">` cells (idx 0 = row label, idx k = plan
  column k), not from a `<table>`.

### 4. What I changed and why it works now

- The gate now splits compound commands (`;`, `&&`, `||`, `|`, `&`, newlines, `$(...)` and backticks)
  and checks every piece. It parses `rm` flags in any form (`-rf`, `-fr`, `-r -f`, `--recursive`), strips
  `sudo`'s own options before checking the inner command, inspects redirection and `tee` targets, and runs
  the deny-list before the allow-list. A destructive piece blocks the whole command unless
  `auto_approve=True` is passed. The same 10 commands now give 10/10, and the offline tests cover the
  variants.
- `extract_text` now rebuilds the grid as one line per plan, for example "Plan comparison - Month pass
  ($29/month): Classic bike prices: 45 min free, then $0.17/min; Ebike prices: Free unlocks + $0.17/min".
  Every rate stays attached to its plan, so `policy_retriever` returns quotable snippets that are actually
  correct. The deterministic reference check (`pricing.py`) parses the same snapshot and confirms the rates.
