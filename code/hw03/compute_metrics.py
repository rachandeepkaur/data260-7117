"""Computes the HW03 chunking-technique comparison metrics from the raw
data run_retrieval.py wrote, and writes the filled table into
reports/hw03/METRICS.md.

    python code/hw03/compute_metrics.py

Reads (never re-runs retrieval itself):
  - reports/hw03/raw/retrieval_runs.csv  (one row per technique x question
    x rank, with cosine_similarity, latency_ms, chunk text, etc.)
  - reports/hw03/raw/chunk_stats.csv     (one row per chunk produced for
    EVERY technique, not just the ones retrieved)
  - reports/hw03/questions.yaml          (each question's answer_keyword:
    a short phrase copied verbatim from the source document)

Metrics, per technique:
  - Chunks              total chunk count for that technique (chunk_stats.csv)
  - Avg chunk length     mean chunk length in characters, across ALL
                         chunks the technique produced (not just retrieved)
  - Top-1 cosine         mean cosine_similarity of the rank=1 result,
                         averaged across the 5 questions
  - Mean@k cosine        mean cosine_similarity across every returned rank
                         (k=3 here), averaged across all (question, rank) pairs
  - Recall@k             see definition below
  - Mean latency (ms)    mean retrieval latency per question (deduplicated,
                         since the same retrieve() call's latency is
                         repeated across its k result rows)

Recall@k definition (the simple version specified for this assignment):
  A question counts as a HIT for a technique if the literal
  answer_keyword text for that question (case-insensitive) appears
  anywhere in the full text of ANY of the top-k chunks retrieved for that
  question, by that technique. Recall@k for a technique is then
  (# questions that hit) / (# questions total).
  This is a simple *string-containment* proxy for "did retrieval surface
  a chunk that could actually answer the question" - it is not a
  human-graded correctness check, and it can both under- and over-count
  (a chunk could contain the literal keyword out of context, or a
  correct chunk could paraphrase the fact without using that exact
  string). answer_keyword was chosen per-question as a short phrase
  copied verbatim from the source document (see questions.yaml), not
  from the free-text expected_answer summary, specifically so this
  check is meaningful.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = REPO_ROOT / "reports" / "hw03" / "raw"
QUESTIONS_PATH = REPO_ROOT / "reports" / "hw03" / "questions.yaml"
METRICS_PATH = REPO_ROOT / "reports" / "hw03" / "METRICS.md"

TOP_K = 3


def load_answer_keywords() -> dict[str, str]:
    data = yaml.safe_load(QUESTIONS_PATH.read_text(encoding="utf-8"))
    return {q["id"]: q["answer_keyword"] for q in data["questions"]}


def compute_recall_at_k(runs: pd.DataFrame, answer_keywords: dict[str, str]) -> pd.Series:
    """One row per (technique, question_id): 1 if any retrieved chunk's
    full text contains that question's answer_keyword, else 0."""
    hits = []
    for (technique, qid), group in runs.groupby(["technique", "question_id"]):
        keyword = answer_keywords[qid].lower()
        texts = group["text"].dropna().str.lower()
        hit = texts.str.contains(keyword, regex=False).any()
        hits.append({"technique": technique, "question_id": qid, "hit": int(hit)})
    hits_df = pd.DataFrame(hits)
    return hits_df.groupby("technique")["hit"].mean()


def main() -> None:
    runs = pd.read_csv(RAW_DIR / "retrieval_runs.csv")
    runs = runs.dropna(subset=["rank"])  # drop the "no nodes returned" placeholder rows, if any
    chunk_stats = pd.read_csv(RAW_DIR / "chunk_stats.csv")
    answer_keywords = load_answer_keywords()

    chunks_summary = chunk_stats.groupby("technique")["chunk_length"].agg(
        chunks="count", avg_chunk_length="mean"
    )

    top1_cosine = (
        runs[runs["rank"] == 1].groupby("technique")["cosine_similarity"].mean().rename("top1_cosine")
    )
    mean_at_k_cosine = runs.groupby("technique")["cosine_similarity"].mean().rename("mean_at_k_cosine")

    # latency_ms is repeated across a question's k rows (one retrieve()
    # call produces it) - drop duplicates per (technique, question) before
    # averaging, so a question with fewer returned nodes isn't overweighted.
    per_question_latency = runs.drop_duplicates(subset=["technique", "question_id"])
    mean_latency = per_question_latency.groupby("technique")["latency_ms"].mean().rename("mean_latency_ms")

    recall_at_k = compute_recall_at_k(runs, answer_keywords).rename("recall_at_k")

    summary = pd.concat(
        [chunks_summary, top1_cosine, mean_at_k_cosine, recall_at_k, mean_latency], axis=1
    )
    summary = summary.reindex(["token", "semantic", "sentence_window"])

    print(summary.to_string(float_format=lambda x: f"{x:.4f}"))

    display_names = {
        "token": "Token",
        "semantic": "Semantic",
        "sentence_window": "Sentence-window",
    }

    header = (
        "| Technique | Chunks | Avg chunk length (chars) | Top-1 cosine | "
        f"Mean@{TOP_K} cosine | Recall@{TOP_K} | Mean latency (ms) |"
    )
    separator = "|---|---|---|---|---|---|---|"
    lines = [header, separator]
    for technique, row in summary.iterrows():
        lines.append(
            f"| {display_names[technique]} "
            f"| {int(row['chunks'])} "
            f"| {row['avg_chunk_length']:.0f} "
            f"| {row['top1_cosine']:.4f} "
            f"| {row['mean_at_k_cosine']:.4f} "
            f"| {row['recall_at_k'] * 100:.0f}% ({int(round(row['recall_at_k'] * 5))}/5) "
            f"| {row['mean_latency_ms']:.2f} |"
        )
    table_md = "\n".join(lines)

    metrics_text = METRICS_PATH.read_text(encoding="utf-8")
    start_marker = "## Retrieval quality comparison — Token vs. Semantic vs. Sentence-window"
    end_marker = "## Per-query breakdown"
    start_idx = metrics_text.index(start_marker)
    end_idx = metrics_text.index(end_marker)

    recall_definition = (
        "A question counts as a **hit** for a technique if the literal `answer_keyword` "
        "text for that question (case-insensitive) appears anywhere in the full text of "
        f"any of the top-{TOP_K} chunks retrieved for that question by that technique "
        "(see `questions.yaml` and `code/hw03/compute_metrics.py`). `answer_keyword` is a "
        "short phrase copied verbatim from the source document specifically for this check "
        "- not the free-text `expected_answer` summary, which is a paraphrase and would "
        "essentially never appear verbatim in a chunk. This is a simple string-containment "
        "proxy for retrieval quality, not a human-graded correctness judgment."
    )

    new_section = (
        f"{start_marker}\n\n"
        f"{table_md}\n\n"
        f"**Recall@{TOP_K} definition:** {recall_definition}\n\n"
        f"Computed by `code/hw03/compute_metrics.py` from "
        f"[raw/retrieval_runs.csv](raw/retrieval_runs.csv) and "
        f"[raw/chunk_stats.csv](raw/chunk_stats.csv). Full console transcript: "
        f"[RUN_LOG.txt](RUN_LOG.txt).\n\n"
    )

    updated = metrics_text[:start_idx] + new_section + metrics_text[end_idx:]
    METRICS_PATH.write_text(updated, encoding="utf-8")
    print(f"\nWrote table into {METRICS_PATH}")


if __name__ == "__main__":
    main()
