"""chunking-technique retrieval comparison: Token vs. Semantic vs.
Sentence-window, run against the 5 committed domain questions
(reports/hw03/questions.yaml).

"""
from __future__ import annotations

import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from llama_index.core import VectorStoreIndex
from llama_index.core.node_parser import (
    SemanticSplitterNodeParser,
    SentenceWindowNodeParser,
    TokenTextSplitter,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from embeddings import FastEmbedONNXEmbedding  # noqa: E402
from load_documents import load_corpus_documents  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
QUESTIONS_PATH = REPO_ROOT / "reports" / "hw03" / "questions.yaml"
RAW_DIR = REPO_ROOT / "reports" / "hw03" / "raw"
TOP_K = 3

# Enforced per the assignment: MiniLM's own limit is 256 tokens, so a
# token chunk size above that would silently truncate at embedding time.
MAX_TOKEN_CHUNK_SIZE = 256

embed_model = FastEmbedONNXEmbedding()

# So the per-technique table prints on one line per row in a normal
# terminal width, instead of pandas wrapping/truncating it.
pd.set_option("display.max_colwidth", 160)
pd.set_option("display.width", 250)

DISPLAY_NAMES = {"token": "Token", "semantic": "Semantic", "sentence_window": "Sentence-window"}


def load_questions() -> list[dict]:
    data = yaml.safe_load(QUESTIONS_PATH.read_text(encoding="utf-8"))
    return data["questions"]


def build_indexes(docs: list) -> tuple[dict[str, VectorStoreIndex], list[dict]]:
    token_splitter = TokenTextSplitter(chunk_size=MAX_TOKEN_CHUNK_SIZE, chunk_overlap=32)
    semantic_splitter = SemanticSplitterNodeParser(
        buffer_size=1, breakpoint_percentile_threshold=95, embed_model=embed_model
    )
    window_splitter = SentenceWindowNodeParser.from_defaults(window_size=3)

    indexes: dict[str, VectorStoreIndex] = {}
    chunk_stat_rows: list[dict] = []
    for name, splitter in [
        ("token", token_splitter),
        ("semantic", semantic_splitter),
        ("sentence_window", window_splitter),
    ]:
        nodes = splitter.get_nodes_from_documents(docs)
        print(f"[{name}] {len(nodes)} nodes")
        for i, node in enumerate(nodes):
            chunk_stat_rows.append({
                "technique": name,
                "chunk_index": i,
                "chunk_length": len(node.get_content()),
            })
        index = VectorStoreIndex(nodes, embed_model=embed_model)
        print(f"[{name}] index built, {len(nodes)} nodes, vector_store={type(index.vector_store).__name__}")
        indexes[name] = index
    return indexes, chunk_stat_rows


def cosine_similarity(query_vec: np.ndarray, doc_vecs: np.ndarray) -> np.ndarray:
    if doc_vecs.shape[0] == 0:
        return np.array([])
    query_unit = query_vec / np.linalg.norm(query_vec)
    doc_units = doc_vecs / np.linalg.norm(doc_vecs, axis=1, keepdims=True)
    return doc_units @ query_unit


def retrieve(technique: str, index: VectorStoreIndex, question: dict, k: int) -> list[dict]:
    query = question["text"].strip()
    qid = question["id"]

    print(f"\n=== TECHNIQUE: {DISPLAY_NAMES[technique]} | question={qid} ===")
    print(f"Query: {query}")

    query_vec = np.array(embed_model.get_query_embedding(query), dtype=np.float32)
    print(f"Query embedding dimension: {query_vec.shape[0]}")
    print(f"First 8 values: {np.round(query_vec[:8], 4).tolist()}")

    start = time.perf_counter()
    retriever = index.as_retriever(similarity_top_k=k)
    result_nodes = retriever.retrieve(query)
    latency_ms = (time.perf_counter() - start) * 1000

    chunk_texts = [n.get_content() for n in result_nodes]
    chunk_vecs = (
        np.array(embed_model.get_text_embedding_batch(chunk_texts))
        if chunk_texts
        else np.zeros((0, query_vec.shape[0]))
    )
    print(f"query shape={query_vec.shape}, docs shape={chunk_vecs.shape}")
    print(f"latency={latency_ms:.2f} ms, {len(result_nodes)} node(s) returned\n")

    cos_sims = cosine_similarity(query_vec, chunk_vecs)

    rows = []
    table_rows = []
    for rank, (node, cos_sim) in enumerate(zip(result_nodes, cos_sims), start=1):
        text = node.get_content()
        preview = text[:160].replace("\n", " ")
        window_text = node.metadata.get("window") if technique == "sentence_window" else None
        table_rows.append({
            "rank": rank,
            "store_score": round(float(node.score), 4) if node.score is not None else None,
            "cosine_sim": round(float(cos_sim), 4),
            "chunk_len": len(text),
            "preview": preview,
        })
        rows.append({
            "technique": technique,
            "question_id": qid,
            "rank": rank,
            "store_score": float(node.score) if node.score is not None else None,
            "cosine_similarity": float(cos_sim),
            "chunk_length": len(text),
            "window_length": len(window_text) if window_text else None,
            "latency_ms": round(latency_ms, 3),
            "preview": preview,
            "text": text,
        })

    if table_rows:
        print(pd.DataFrame(table_rows).to_string(index=False))
    else:
        print("(no nodes returned)")
        rows.append({
            "technique": technique, "question_id": qid, "rank": None,
            "store_score": None, "cosine_similarity": None,
            "chunk_length": None, "window_length": None,
            "latency_ms": round(latency_ms, 3), "preview": None, "text": None,
        })

    return rows


def main() -> None:
    start_time = datetime.now(timezone.utc)
    print(f"=== RUN START: {start_time.isoformat()} ===\n")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    questions = load_questions()

    docs = load_corpus_documents()
    print(f"Loaded {len(docs)} document(s)\n")

    indexes, chunk_stat_rows = build_indexes(docs)
    print()

    all_rows: list[dict] = []
    for technique, index in indexes.items():
        for question in questions:
            all_rows.extend(retrieve(technique, index, question, TOP_K))
        print()

    jsonl_path = RAW_DIR / "retrieval_runs.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in all_rows:
            f.write(json.dumps(row) + "\n")

    csv_path = RAW_DIR / "retrieval_runs.csv"
    fieldnames = list(all_rows[0].keys())
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Wrote {len(all_rows)} rows to {jsonl_path} and {csv_path}")

    chunk_stats_path = RAW_DIR / "chunk_stats.csv"
    with chunk_stats_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["technique", "chunk_index", "chunk_length"])
        writer.writeheader()
        writer.writerows(chunk_stat_rows)

    print(f"Wrote {len(chunk_stat_rows)} rows to {chunk_stats_path}")

    end_time = datetime.now(timezone.utc)
    print(f"\n=== RUN END: {end_time.isoformat()} (elapsed {(end_time - start_time).total_seconds():.1f}s) ===")


if __name__ == "__main__":
    main()
