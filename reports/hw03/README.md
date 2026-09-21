# HW03 — Reproducible Run Instructions

Run these from the repo root, in order, on a clean checkout. No env vars or `.env` file are required.

## Setup

Embeddings run via `fastembed` (ONNXRuntime), not
`llama_index.embeddings.huggingface.HuggingFaceEmbedding`/`sentence-transformers`:
PyTorch publishes no wheel at all for Intel x86_64 macOS on Python 3.13, so
`HuggingFaceEmbedding` (which requires `sentence-transformers` -> `torch`)
can't be installed on this machine. `fastembed` runs an ONNX conversion of
the same model, `sentence-transformers/all-MiniLM-L6-v2` (confirmed
384-dim output), on ONNXRuntime instead - same model weights, same
embedding space, no `torch` dependency.

```bash
pip install -r requirements.txt
```

## Build the corpus / index

Extracts + cleans the PDFs in `data/corpus/` into `.txt` files (joins hard-wrapped lines, strips repeated headers/footers/page numbers), then hashes every file in `data/corpus/` into `CORPUS_MANIFEST.json`:

```bash
python code/hw03/prepare_corpus.py
python code/hw03/build_manifest.py
```

There's no separate "build index" command - the three chunked `VectorStoreIndex` objects (Token / Semantic / Sentence-window) are built in-memory as part of `run_retrieval.py`, below, since nothing else needs to persist them.

## Run the retrieval comparison

Runs all 3 techniques against the 5 committed questions in `questions.yaml`, logs the full console output, writes `raw/retrieval_runs.csv`/`.jsonl` and `raw/chunk_stats.csv`, then computes the results table into `METRICS.md`:

```bash
python code/hw03/run_retrieval.py 2>&1 | tee reports/hw03/RUN_LOG.txt
python code/hw03/compute_metrics.py
```

(One sample chunk per technique, for a screenshot: `python code/hw03/print_sample_chunks.py q4`.)

## Verify

Checks the corpus files/hashes, `questions.yaml`, the raw retrieval/chunk data's shape, the embedding backend's output dimension, and that `METRICS.md` has no leftover `TODO`s - then writes `verification.json`:

```bash
python code/hw03/verify.py
```
