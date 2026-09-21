"""Prints one sample retrieved chunk per technique, for the report's
"one sample chunk from each technique" screenshot.

    python code/hw03/print_sample_chunks.py [question_id]

Defaults to q4 (shared across all three techniques' top results) so the
same topic is compared across chunking strategies, not three unrelated
chunks. Reads reports/hw03/raw/retrieval_runs.csv (already produced by
run_retrieval.py) - does not re-run retrieval.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = REPO_ROOT / "reports" / "hw03" / "raw"

TECHNIQUE_ORDER = ["token", "semantic", "sentence_window"]
DISPLAY_NAMES = {
    "token": "TOKEN",
    "semantic": "SEMANTIC",
    "sentence_window": "SENTENCE-WINDOW",
}


def main() -> None:
    question_id = sys.argv[1] if len(sys.argv) > 1 else "q4"

    runs = pd.read_csv(RAW_DIR / "retrieval_runs.csv")
    subset = runs[(runs["question_id"] == question_id) & (runs["rank"] == 1)]

    for technique in TECHNIQUE_ORDER:
        row = subset[subset["technique"] == technique]
        if row.empty:
            continue
        row = row.iloc[0]
        print("=" * 100)
        print(f"{DISPLAY_NAMES[technique]}  |  question={question_id}  |  chunk_length={int(row['chunk_length'])} chars  |  cosine={row['cosine_similarity']:.4f}")
        print("=" * 100)
        print(row["text"])
        print()


if __name__ == "__main__":
    main()
