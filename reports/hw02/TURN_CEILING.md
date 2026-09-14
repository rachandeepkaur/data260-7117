# HW02 Turn-Ceiling Comparison

Fixed input (`reports/hw02/cases/schema_input.json`, facility: "FA0206933 - YUMMY KITCHEN"), same model settings, run through the real Supervisor/Planner/Reviewer LangGraph agent (`qwen3:8b` via Ollama) 20 times at each of MAX_TURNS=2 and MAX_TURNS=10 (40 runs total). "Completed" means the Reviewer genuinely approved before the ceiling was reached. Source data: [raw/turn_ceiling_runs.json](raw/turn_ceiling_runs.json), [raw/turn_ceiling_runs.csv](raw/turn_ceiling_runs.csv).

## Results

| MAX_TURNS | Runs | Completed | Completion rate | Mean latency (all runs) | Mean latency (completed only) |
|---|---|---|---|---|---|
| 2 | 20 | 0/20 | 0.0% | 11015.1 ms | - ms |
| 10 | 20 | 20/20 | 100.0% | 26437.8 ms | 26437.8 ms |

## Recommendation

**Pick MAX_TURNS=10 for deployment.** MAX_TURNS=2 is not a viable ceiling at all — 0/20 completion isn't a marginal or model-dependent result, it's structurally guaranteed by this graph's shape. Tracing `router_logic`: the first Supervisor visit (`turn_count=1`) routes to the Planner; the *second* Supervisor visit (`turn_count=2`) is where the ceiling check (`turn_count >= MAX_TURNS`) runs *before* the "has proposal → Reviewer" branch. With `MAX_TURNS=2`, that check is already true, so the graph ends via the ceiling at the exact moment it would otherwise have routed to the Reviewer — the Reviewer never gets to run even once. This matches the data exactly: every single ceiling=2 run terminated at `final_turn_count=2` with `approved=False`, at a uniform ~11s (one Planner call, no Reviewer call at all).

The actual minimum viable ceiling for a single non-retry round is **3**, not 2 — once the Reviewer runs and approves, `router_logic`'s approval check short-circuits before the ceiling check, so the graph can end successfully at `turn_count=2` regardless of how high `MAX_TURNS` is set, as long as it's `>= 3`. That means the choice isn't really "2 vs. 10" in practice — it's "any ceiling ≥ 3" vs. "2, which is broken by construction."

Given that, MAX_TURNS=10 vs. the bare minimum of 3 comes down to headroom: at ceiling=10, all 20 runs still converged in the minimum 2 turns (mean latency 26,437.8 ms, essentially identical to every single-run measurement taken earlier in this project at MAX_TURNS=8) — the extra ceiling above 3 was never actually used and cost nothing in the common case. It only matters as a safety margin for a harder input that needs one or more Reviewer-rejection retry rounds (each round costs +2 turns), which this particular frozen input never triggered. A ceiling of exactly 3 would be the tightest ceiling that still works, but offers no room at all for even a single retry round before abandoning — MAX_TURNS=10 (up to 4 full Planner↔Reviewer rounds) trades a small amount of theoretical worst-case latency on a pathological input for meaningfully more resilience on harder ones, at zero measured cost on this input.
