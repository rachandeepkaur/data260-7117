"""Rebuild reports/hw06/METRICS.md from the files in reports/hw06/raw/.

    make metrics-hw06

Part 3 means use the 30 conversation turns of each run (the 5 probe turns are
scored, not averaged into the cost). "Prompt tokens" are the counts Ollama
reports for the chat call; per-component counts use the Qwen3 tokenizer.
Latency is the server-side /api/chat request time (chat call + memory upkeep).
Costs: $1 / 1M input tokens, $5 / 1M output tokens, 10,000 conversations x
30 turns, shown for the chat call alone and including the memory-upkeep calls
(fact extraction + summaries) that the memory system adds.
"""
from __future__ import annotations

import json
from datetime import datetime

import pandas as pd

from hw06_config import (
    EXPERIMENT_SETTINGS,
    INPUT_PRICE_PER_M,
    N_CONVERSATIONS,
    OUTPUT_PRICE_PER_M,
    RAW_DIR,
    REPORT_DIR,
)

QUALITY_TOLERANCE = 0.5  # "best" = cheapest setting within this many points of the top probe score


def md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def part3(sections: list[str]) -> None:
    path = RAW_DIR / "memory_turns.csv"
    if not path.exists():
        sections.append("## Part 3\n\n_No experiment data yet - run `make memory-experiment-hw06`._")
        return
    df = pd.read_csv(path)
    order = [label for label, _ in EXPERIMENT_SETTINGS if label in set(df.setting)]
    conv, probes = df[df.kind == "conversation"], df[df.kind == "probe"]

    rows, comp_rows, cost_rows, probe_rows = [], [], [], []
    for s in order:
        c, p = conv[conv.setting == s], probes[probes.setting == s]
        rows.append({"Setting": s, "Mean prompt tokens/turn": round(c.prompt_tokens.mean(), 1),
                     "Mean latency (ms)": round(c.latency_ms.mean()),
                     "Probe quality (1-5)": round(p.probe_score.mean(), 2),
                     "Turns": len(c)})
        comp_rows.append({"Setting": s, "System primer": round(c.tok_system_primer.mean(), 1),
                          "Long-term summary": round(c.tok_long_term_summary.mean(), 1),
                          "Short-term window": round(c.tok_short_term_window.mean(), 1),
                          "Episodic facts": round(c.tok_episodic_facts.mean(), 1),
                          "Current message": round(c.tok_current_message.mean(), 1),
                          "Counted total": round(c.tok_counted_total.mean(), 1),
                          "Ollama prompt": round(c.prompt_tokens.mean(), 1),
                          "Mean completion": round(c.completion_tokens.mean(), 1),
                          "Model latency (ms)": round(c.model_latency_ms.mean()),
                          "Upkeep latency (ms)": round(c.aux_latency_ms.mean())})
        inp, out = c.prompt_tokens.sum(), c.completion_tokens.sum()
        ainp, aout = c.aux_prompt_tokens.sum(), c.aux_completion_tokens.sum()
        chat_cost = (inp * INPUT_PRICE_PER_M + out * OUTPUT_PRICE_PER_M) / 1e6
        total_cost = ((inp + ainp) * INPUT_PRICE_PER_M + (out + aout) * OUTPUT_PRICE_PER_M) / 1e6
        cost_rows.append({"Setting": s, "Input tok/conv": int(inp), "Output tok/conv": int(out),
                          "Upkeep in/out tok/conv": f"{int(ainp)} / {int(aout)}",
                          "Chat $/conv": f"{chat_cost:.5f}", "Chat $ x10k": f"{chat_cost * N_CONVERSATIONS:,.2f}",
                          "Incl. upkeep $ x10k": f"{total_cost * N_CONVERSATIONS:,.2f}",
                          "_total": total_cost * N_CONVERSATIONS, "_quality": p.probe_score.mean()})
        probe_rows.append({"Setting": s, **{pid: int(v) for pid, v in zip(p.probe_id, p.probe_score, strict=False)}})

    main = pd.DataFrame(rows)
    sections.append("## Part 3.3/3.4 - Short-term memory size and compression policy\n\n"
                    "Means over the 30 conversation turns of one fresh run per setting; probe quality = mean of "
                    "the 5 probe scores (rubric in `memory_probes.yaml`).\n\n" + md_table(main))
    sections.append("### Prompt composition (mean tokens per turn)\n\n" + md_table(pd.DataFrame(comp_rows)))
    sections.append("### Probe scores per question\n\n" + md_table(pd.DataFrame(probe_rows).fillna("-")))

    pol, base = "Compression policy (N=12)", "SHORT_TERM_N=12"
    if pol in order and base in order:
        b, q = main.set_index("Setting").loc[base], main.set_index("Setting").loc[pol]
        bc, qc = conv[conv.setting == base], conv[conv.setting == pol]
        saved = b["Mean prompt tokens/turn"] - q["Mean prompt tokens/turn"]
        win_saved = bc.tok_short_term_window.mean() - qc.tok_short_term_window.mean()
        ep_saved = bc.tok_episodic_facts.mean() - qc.tok_episodic_facts.mean()
        cmp = pd.DataFrame([
            {"Metric": "Mean prompt tokens/turn", base: b["Mean prompt tokens/turn"], pol: q["Mean prompt tokens/turn"],
             "Change": f"{-saved:+.1f} ({-saved / b['Mean prompt tokens/turn'] * 100:+.1f}%)"},
            {"Metric": "Short-term window tokens/turn", base: round(bc.tok_short_term_window.mean(), 1),
             pol: round(qc.tok_short_term_window.mean(), 1), "Change": f"{-win_saved:+.1f}"},
            {"Metric": "Episodic-fact tokens/turn", base: round(bc.tok_episodic_facts.mean(), 1),
             pol: round(qc.tok_episodic_facts.mean(), 1), "Change": f"{-ep_saved:+.1f}"},
            {"Metric": "Input tokens per 30-turn conversation", base: int(bc.prompt_tokens.sum()),
             pol: int(qc.prompt_tokens.sum()), "Change": f"{int(qc.prompt_tokens.sum() - bc.prompt_tokens.sum()):+d}"},
            {"Metric": "Mean latency (ms)", base: b["Mean latency (ms)"], pol: q["Mean latency (ms)"],
             "Change": f"{q['Mean latency (ms)'] - b['Mean latency (ms)']:+.0f}"},
            {"Metric": "Probe quality (1-5)", base: b["Probe quality (1-5)"], pol: q["Probe quality (1-5)"],
             "Change": f"{q['Probe quality (1-5)'] - b['Probe quality (1-5)']:+.2f}"},
        ])
        (RAW_DIR / "compression_comparison.json").write_text(cmp.to_json(orient="records", indent=2))
        sections.append("### Part 3.4 - Compression policy vs. the same window without it\n\n"
                        "Policy: keep the newest 2 messages verbatim, cut older assistant turns in the window to "
                        "their first sentence (<=160 chars), never shorten user turns, and evict episodic facts with "
                        "cosine < 0.40.\n\n" + md_table(cmp))

    cost = pd.DataFrame(cost_rows)
    top_q = cost._quality.max()
    eligible = cost[cost._quality >= top_q - QUALITY_TOLERANCE]
    best = eligible.loc[eligible._total.idxmin(), "Setting"]
    worst = cost.loc[cost._total.idxmax(), "Setting"]
    cost.insert(1, "Role", ["best" if s == best else "worst" if s == worst else "" for s in cost.Setting])
    sections.append(
        "## Part 3.5 - Memory cost estimate (10,000 x 30-turn conversations)\n\n"
        f"Pricing: ${INPUT_PRICE_PER_M:g} / 1M input, ${OUTPUT_PRICE_PER_M:g} / 1M output tokens. Token counts are the "
        "measured sums over one 30-turn run. \"Upkeep\" = the fact-extraction and summary calls the memory system "
        "adds per turn.\n\n" + md_table(cost.drop(columns=["_total", "_quality"])) +
        f"\n\n**Selection rule.** Worst = the highest total cost ({worst}). Best = the cheapest setting whose probe "
        f"quality is within {QUALITY_TOLERANCE} points of the best probe score ({top_q:.2f}) - so a setting cannot "
        f"win on price by forgetting the facts the probes test. Best: **{best}**; worst: **{worst}**.")


def part1_2(sections: list[str]) -> None:
    p1 = RAW_DIR / "part1_doc_api_calls.json"
    if p1.exists():
        calls = json.loads(p1.read_text())
        df = pd.DataFrame([{"Case": c["label"], "Method": c["request"]["method"], "Status": c["status"],
                            "Expected": c["expected"], "OK": "yes" if c["ok"] else "NO"} for c in calls])
        sections.append(f"## Part 1 - Document API calls ({sum(c['ok'] for c in calls)}/{len(calls)} as expected)\n\n"
                        + md_table(df))
    p2 = RAW_DIR / "part2_chat_transcript.json"
    if p2.exists():
        t = json.loads(p2.read_text())
        df = pd.DataFrame([{"Turn": r["turn"], "Window msgs": r["memory_used"]["short_term_count"],
                            "Session summary": "yes" if r["memory_used"]["session_summary"] else "-",
                            "Lifetime summary": "yes" if r["memory_used"]["lifetime_summary"] else "-",
                            "Facts retrieved": len(r["memory_used"]["episodic_facts"]),
                            "Facts stored": len(r["memory_updates"]["facts_extracted"]),
                            "Summary written": ("session" if r["memory_updates"]["session_summary_updated"] else "")
                            + (" + lifetime" if r["memory_updates"]["lifetime_summary_updated"] else ""),
                            "Prompt tok": r["usage"]["prompt_tokens"], "Latency (ms)": round(r["usage"]["latency_ms"])}
                           for r in t])
        sections.append("## Part 2 - 12-message session (memory observed per turn)\n\n" + md_table(df))


def part4(sections: list[str]) -> None:
    a = RAW_DIR / "consolidation_audit.json"
    if a.exists():
        r = json.loads(a.read_text())
        df = pd.DataFrame([{"Contradiction": c["topic"], "Result": c["status"],
                            "Superseded value kept visible": "yes" if c["superseded_value_still_visible"] else "no",
                            "Audit flag": "yes" if c["audit_flagged"] else "no"} for c in r["contradictions"]])
        sections.append(
            "## Part 4.5 - Consolidation test\n\n"
            f"- Total lines: {r['total_lines_before']} -> {r['total_lines_after']} (under 40: {r['under_40_lines']})\n"
            f"- Non-empty non-comment lines: {r['non_comment_lines'][0]} -> {r['non_comment_lines'][1]}; "
            f"facts {r['facts'][0]} -> {r['facts'][1]}\n"
            f"- Duplicate topics merged: {r['duplicates_merged']}/{len(r['duplicates'])} "
            f"({r['exact_duplicates_merged_deterministically']} exact copies merged before the model call)\n"
            f"- Contradictions resolved correctly: {r['contradictions_correct']}/{len(r['contradictions'])}; "
            f"no silent deletion: {r['no_silent_deletion']}\n\n" + md_table(df))
    g = RAW_DIR / "agent_md_check.json"
    if g.exists():
        r = json.loads(g.read_text())
        df = pd.DataFrame([{"Category": c["category"], "AGENT.md rule": c["agent_md_rule"],
                            "Result": "PASS" if c["passed"] else "FAIL"} for c in r["static_checks"]])
        sections.append(f"## Part 4.4 - Generated function vs. AGENT.md\n\n{r['rules_followed']}/{r['rules_checked']} "
                        f"rules followed; behaviour tests {'pass' if r['behaviour_ok'] else 'FAIL'}.\n\n"
                        + md_table(df))


def main() -> None:
    sections = [f"# HW6 Metrics\n\nGenerated by `make metrics-hw06` on {datetime.now():%Y-%m-%d %H:%M} from "
                "`reports/hw06/raw/`. Model: qwen3:8b (Ollama, local CPU). SID4 7117, PORT_BASE 8817, "
                "SEED 7117, VERIFY_SEED 267117."]
    part1_2(sections)
    part3(sections)
    part4(sections)
    (REPORT_DIR / "METRICS.md").write_text("\n\n".join(sections) + "\n")
    print("\n\n".join(sections))
    print(f"\nwrote {REPORT_DIR / 'METRICS.md'}")


if __name__ == "__main__":
    main()
