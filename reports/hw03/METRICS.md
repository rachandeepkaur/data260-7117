# HW03 Metrics — Chunking Technique Retrieval Comparison

Corpus: 4 documents in `data/corpus/` (2 California county retail-food
inspection guides, 2 individual facility inspection reports), cleaned and
chunked by `code/hw03/prepare_corpus.py` / `code/hw03/run_retrieval.py`.
Embedding model: `sentence-transformers/all-MiniLM-L6-v2` (384-dim), run
via `fastembed`/ONNXRuntime rather than `HuggingFaceEmbedding`/`torch` -
this machine's Intel x86_64 macOS + Python 3.13 has no PyTorch wheel
available at all, so `code/hw03/embeddings.py` runs an ONNX conversion of
the exact same model instead (same weights, same 384-dim output, no
`torch` dependency). 5 committed domain questions (`questions.yaml`),
top-k = 3.

## Retrieval quality comparison — Token vs. Semantic vs. Sentence-window

| Technique | Chunks | Avg chunk length (chars) | Top-1 cosine | Mean@3 cosine | Recall@3 | Mean latency (ms) |
|---|---|---|---|---|---|---|
| Token | 693 | 1002 | 0.6790 | 0.6564 | 60% (3/5) | 38.41 |
| Semantic | 243 | 2445 | 0.6353 | 0.6233 | 60% (3/5) | 22.03 |
| Sentence-window | 4749 | 125 | 0.6740 | 0.6530 | 40% (2/5) | 158.32 |

**Recall@3 definition:** A question counts as a **hit** for a technique if the literal `answer_keyword` text for that question (case-insensitive) appears anywhere in the full text of any of the top-3 chunks retrieved for that question by that technique (see `questions.yaml` and `code/hw03/compute_metrics.py`). `answer_keyword` is a short phrase copied verbatim from the source document specifically for this check - not the free-text `expected_answer` summary, which is a paraphrase and would essentially never appear verbatim in a chunk. This is a simple string-containment proxy for retrieval quality, not a human-graded correctness judgment.

Computed by `code/hw03/compute_metrics.py` from [raw/retrieval_runs.csv](raw/retrieval_runs.csv) and [raw/chunk_stats.csv](raw/chunk_stats.csv). Full console transcript: [RUN_LOG.txt](RUN_LOG.txt).

## Per-query breakdown

Full per-query, per-rank rows (technique, cosine, chunk length, latency, chunk text) are in [raw/retrieval_runs.csv](raw/retrieval_runs.csv).

One flagged case worth noting: `sentence_window`/q4/rank 1 scores a high cosine (0.78) and comes from `retail-food-inspection-guide.txt`, but is marked a Recall@3 miss - the chunk covers the 41-45°F holding exception, genuinely on-topic, but doesn't contain the literal "135°F" keyword. This shows the string-match Recall@k can undercount relevant-but-differently-worded chunks.

## Takeaway

Token chunking is the best fit here: it ties for the highest Recall@3 (60%) and has the best Top-1/Mean@3 cosine (0.679/0.656) of the three, at a latency (36 ms) far below sentence-window's (154 ms). Semantic chunking is fastest (22 ms) but its much larger chunks (avg 2445 chars) dilute relevance (lowest cosine scores). Sentence-window's tiny chunks (avg 125 chars) are the most precise to read individually but had the lowest Recall@3 (40%) and by far the highest latency, from indexing 4749 single-sentence nodes.
