"""Grounded RAG question answering + context-engineering study (HW4 Part 4).

    python code/hw04/rag.py                    # full run: 6 questions x A/B/C + k-sweep + evaluation
    python code/hw04/rag.py --retrieval-only   # print top-k retrievals only (no LLM calls)

Pipeline
  1. Corpus: the 4 cleaned HW3 documents in data/corpus/*.txt plus 2 added in
     data/corpus/hw04/*.txt (6 documents).
  2. Index: SentenceSplitter(chunk_size=500, chunk_overlap=50) -> nodes that
     carry text, source and chunk_id -> embedded with BAAI/bge-small-en-v1.5
     (fastembed/ONNX, 512-token window, so a 500-token chunk is not
     truncated the way it would be by HW3's 256-token MiniLM) -> LlamaIndex
     VectorStoreIndex.
  3. Retrieval: top-k chunks printed with rank, score, source and chunk_id
     BEFORE the LLM is called.
  4. Three configurations per question, same local model (qwen3:8b via
     Ollama, temperature 0, seed = SEED):
       A  No RAG            - the bare question.
       B  Basic RAG         - top-3 raw chunks pasted above the question.
       C  Context-engineered - drop irrelevant chunks (absolute score floor +
                               margin below the best chunk), drop near-
                               duplicates (word 5-gram Jaccard), order by
                               score, label each survivor [Source n] with its
                               file/chunk_id, and add grounding rules (answer
                               only from context, cite [Source n], exact
                               refusal sentence when evidence is missing).
  5. k-sweep (k = 1, 3, 5) on Q2 and Q3 for B and C.
  6. Automatic evaluation (rules in evaluate()) -> tables in reports/hw04/raw/.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, List

import yaml
from fastembed import TextEmbedding
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from llama_index.core import Document, VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.utils import get_tokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hw04_config import LOCAL_MODEL, RAW_DIR, REPO_ROOT, REPORT_DIR, SEED  # noqa: E402

CORPUS_FILES = sorted((REPO_ROOT / "data" / "corpus").glob("*.txt")) + sorted(
    (REPO_ROOT / "data" / "corpus" / "hw04").glob("*.txt")
)
QUESTIONS_PATH = REPORT_DIR / "rag_questions.yaml"

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K = 3
K_SWEEP = [1, 3, 5]
K_SWEEP_QUESTIONS = ["Q2", "Q3"]
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

# Context-engineering filters (config C).
MIN_SCORE = 0.60          # absolute cosine floor: below this a chunk is treated as irrelevant
RELATIVE_MARGIN = 0.12    # also drop chunks scoring more than this below the best chunk
DUP_JACCARD = 0.50        # word 5-gram Jaccard at/above which a chunk is a near-duplicate

REFUSAL = "I cannot answer this question from the provided documents"

REFUSAL_PATTERN = re.compile(
    r"cannot answer this question from the provided documents|"
    r"(do not|don't|does not|doesn't) (contain|include|provide|mention|have)|"
    r"(not|no) (mentioned|provided|included|available|specified|found|information)|"
    r"(cannot|can't|unable to) (answer|determine|find|provide)|"
    r"no (specific )?(information|data|record)|i don't have|i do not have|not (able|possible) to (determine|answer)",
    re.I,
)

_tokenizer = get_tokenizer()


def n_tokens(text: str) -> int:
    return len(_tokenizer(text))


# ---------------------------------------------------------------- embeddings
@lru_cache(maxsize=2)
def _load_model(model_name: str) -> TextEmbedding:
    return TextEmbedding(model_name=model_name)


class BGEEmbedding(BaseEmbedding):
    """LlamaIndex embedding over fastembed; queries get bge's query prefix."""

    model_name: str = EMBED_MODEL

    @classmethod
    def class_name(cls) -> str:
        return "BGEEmbedding"

    def _get_query_embedding(self, query: str) -> List[float]:
        return list(_load_model(self.model_name).query_embed([query]))[0].tolist()

    def _get_text_embedding(self, text: str) -> List[float]:
        return self._get_text_embeddings([text])[0]

    def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        return [v.tolist() for v in _load_model(self.model_name).passage_embed(texts)]

    async def _aget_query_embedding(self, query: str) -> List[float]:
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text: str) -> List[float]:
        return self._get_text_embedding(text)


# ---------------------------------------------------------------- corpus/index
def build_index(chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP):
    docs = []
    for path in CORPUS_FILES:
        docs.append(Document(text=path.read_text(encoding="utf-8"), metadata={"source": path.name}))
    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    nodes = []
    for doc in docs:
        doc_nodes = splitter.get_nodes_from_documents([doc])
        stem = Path(doc.metadata["source"]).stem
        for i, node in enumerate(doc_nodes):
            node.metadata["chunk_id"] = f"{stem}#{i:03d}"
            node.id_ = node.metadata["chunk_id"]
            # Embed/LLM on the chunk text only; source travels as metadata.
            node.excluded_embed_metadata_keys = ["source", "chunk_id"]
            node.excluded_llm_metadata_keys = ["source", "chunk_id"]
        nodes.extend(doc_nodes)
    index = VectorStoreIndex(nodes, embed_model=BGEEmbedding())
    return index, docs, nodes


def retrieve(index, question: str, k: int) -> list[dict]:
    results = index.as_retriever(similarity_top_k=k).retrieve(question)
    return [
        {
            "rank": rank,
            "score": round(float(r.score), 4),
            "source": r.node.metadata["source"],
            "chunk_id": r.node.metadata["chunk_id"],
            "text": r.node.get_content(),
        }
        for rank, r in enumerate(results, start=1)
    ]


def format_retrievals(qid: str, question: str, k: int, chunks: list[dict]) -> str:
    lines = [f"\n{'=' * 100}", f"[{qid}] top-{k} retrieval for: {question}"]
    for c in chunks:
        preview = re.sub(r"\s+", " ", c["text"])[:260]
        lines.append(f"  #{c['rank']}  score={c['score']:.4f}  source={c['source']}  chunk_id={c['chunk_id']}")
        lines.append(f"      {preview}...")
    return "\n".join(lines)


# ---------------------------------------------------------------- context engineering (C)
def _shingles(text: str, n: int = 5) -> set:
    words = re.findall(r"\w+", text.lower())
    return {" ".join(words[i:i + n]) for i in range(max(1, len(words) - n + 1))}


def engineer_context(chunks: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (kept, dropped) - each dropped chunk carries a `drop_reason`."""
    kept, dropped = [], []
    best = max((c["score"] for c in chunks), default=0.0)
    for c in sorted(chunks, key=lambda c: c["score"], reverse=True):
        if c["score"] < MIN_SCORE:
            dropped.append({**c, "drop_reason": f"irrelevant (score {c['score']:.3f} < floor {MIN_SCORE})"})
            continue
        if c["score"] < best - RELATIVE_MARGIN:
            dropped.append({**c, "drop_reason": f"irrelevant (score {c['score']:.3f} > {RELATIVE_MARGIN} below best {best:.3f})"})
            continue
        sh = _shingles(c["text"])
        dup_of = None
        for k in kept:
            ks = _shingles(k["text"])
            jac = len(sh & ks) / max(1, len(sh | ks))
            if jac >= DUP_JACCARD:
                dup_of = (k["chunk_id"], jac)
                break
        if dup_of:
            dropped.append({**c, "drop_reason": f"duplicate of {dup_of[0]} (jaccard {dup_of[1]:.2f})"})
            continue
        kept.append(c)
    return kept, dropped


GROUNDED_SYSTEM = f"""You answer questions about restaurant food-safety inspections using ONLY the numbered sources provided.
Rules:
1. Use only facts stated in the sources. Do not use outside knowledge, even if you know the answer.
2. Cite the source number in square brackets after every fact, e.g. [Source 1] or [Source 1][Source 2].
3. If the sources do not contain enough evidence to answer, reply with exactly this sentence and nothing else: "{REFUSAL}."
4. If the question is ambiguous (for example the sources describe different counties or facilities), say that it is ambiguous and answer each case separately, with citations.
5. Be concise: at most 5 sentences."""


def prompt_for(config: str, question: str, chunks: list[dict]) -> tuple[list, dict]:
    """Return (messages, context info) for configuration A, B or C."""
    if config == "A":
        return [HumanMessage(content=question)], {"context_chunks": [], "dropped": []}
    if config == "B":
        context = "\n\n".join(c["text"] for c in chunks)
        user = f"Use the following context to answer the question.\n\nContext:\n{context}\n\nQuestion: {question}\nAnswer:"
        return [HumanMessage(content=user)], {"context_chunks": chunks, "dropped": []}
    kept, dropped = engineer_context(chunks)
    blocks = [
        f"[Source {i}] (file: {c['source']}, chunk: {c['chunk_id']}, relevance: {c['score']:.2f})\n{c['text'].strip()}"
        for i, c in enumerate(kept, start=1)
    ]
    user = "Sources:\n\n" + ("\n\n".join(blocks) if blocks else "(no relevant sources)") + f"\n\nQuestion: {question}"
    return [SystemMessage(content=GROUNDED_SYSTEM), HumanMessage(content=user)], {"context_chunks": kept, "dropped": dropped}


# ---------------------------------------------------------------- LLM
_llm = ChatOllama(model=LOCAL_MODEL, temperature=0, seed=SEED, reasoning=False, num_predict=400)


def ask(messages: list) -> tuple[str, dict]:
    start = time.perf_counter()
    response = _llm.invoke(messages)
    usage = response.usage_metadata or {}
    return response.content.strip(), {
        "llm_seconds": round(time.perf_counter() - start, 2),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
    }


def run_config(config: str, question: dict, chunks: list[dict], k: int) -> dict:
    messages, ctx = prompt_for(config, question["text"], chunks)
    context_text = "\n\n".join(c["text"] for c in ctx["context_chunks"])
    if config == "C" and not ctx["context_chunks"]:
        # Nothing survived filtering: refuse deterministically, no LLM call.
        answer, meta = f"{REFUSAL}.", {"llm_seconds": 0.0, "input_tokens": 0, "output_tokens": 0, "refused_by_filter": True}
    else:
        answer, meta = ask(messages)
        meta["refused_by_filter"] = False
    row = {
        "question_id": question["id"],
        "question_type": question["type"],
        "config": config,
        "top_k": k,
        "retrieved": [{kk: c[kk] for kk in ("rank", "score", "source", "chunk_id")} for c in chunks] if config != "A" else [],
        "context_chunks": [{kk: c[kk] for kk in ("rank", "score", "source", "chunk_id")} for c in ctx["context_chunks"]],
        "dropped": [{kk: c[kk] for kk in ("rank", "score", "source", "chunk_id", "drop_reason")} for c in ctx["dropped"]],
        "context_tokens": n_tokens(context_text),
        "answer": answer,
        **meta,
    }
    row.update(evaluate(question, row, ctx["context_chunks"], context_text))
    return row


# ---------------------------------------------------------------- evaluation
def _matches(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.I | re.S) is not None


def evaluate(question: dict, row: dict, context_chunks: list[dict], context_text: str) -> dict:
    """Automatic, rule-based scoring :

    correct_retrieval  every retrieval_group regex matches some chunk placed in the prompt (n/a for A and for must-refuse questions)
    refused            answer matches REFUSAL_PATTERN
    correct_answer     must_refuse -> refused; else not refused and every answer_group matches
    grounded           refused -> True; must_refuse but answered -> False; A -> n/a (no context); else every number in the answer appears in the context, and (C only)
                       every [Source n] cited exists in the prompt
    format_compliant   exact refusal sentence, or at least one valid [Source n] citation
    refused_when_needed must_refuse -> refused; else -> not refused
    """
    answer = row["answer"]
    config = row["config"]
    refused = _matches(REFUSAL_PATTERN.pattern, answer)
    must_refuse = question["must_refuse"]

    if config == "A" or must_refuse:
        correct_retrieval = None
    else:
        correct_retrieval = all(
            any(_matches(g, c["text"]) for c in context_chunks) for g in question["retrieval_groups"]
        )

    if must_refuse:
        correct_answer = refused
    else:
        correct_answer = (not refused) and all(_matches(g, answer) for g in question["answer_groups"])

    cited = [int(n) for n in re.findall(r"\[Source (\d+)\]", answer)]
    valid_citations = bool(cited) and all(1 <= n <= len(context_chunks) for n in cited)

    if refused:
        grounded = True
    elif must_refuse:
        grounded = False
    elif config == "A":
        grounded = None
    else:
        answer_numbers = set(re.findall(r"\d+(?:\.\d+)?", re.sub(r"\[Source \d+\]", "", answer)))
        context_numbers = set(re.findall(r"\d+(?:\.\d+)?", context_text))
        grounded = answer_numbers <= context_numbers and (config != "C" or valid_citations)

    exact_refusal = answer.strip().rstrip(".").strip('"').lower() == REFUSAL.lower()
    format_compliant = exact_refusal or valid_citations

    ambiguity_flagged = None
    if question.get("ambiguity_markers"):
        ambiguity_flagged = _matches(question["ambiguity_markers"], answer)

    return {
        "correct_retrieval": correct_retrieval,
        "correct_answer": correct_answer,
        "grounded": grounded,
        "refused": refused,
        "refused_when_needed": refused if must_refuse else (not refused),
        "format_compliant": format_compliant,
        "citations": cited,
        "ambiguity_flagged": ambiguity_flagged,
    }


def rate(values: list) -> str:
    vals = [v for v in values if v is not None]
    if not vals:
        return "n/a"
    return f"{sum(bool(v) for v in vals)}/{len(vals)} ({100 * sum(bool(v) for v in vals) / len(vals):.0f}%)"


def summarize(rows: list[dict], questions: list[dict]) -> list[dict]:
    by_id = {q["id"]: q for q in questions}
    out = []
    for config in ["A", "B", "C"]:
        subset = [r for r in rows if r["config"] == config]
        robust = []
        for r in subset:
            q = by_id[r["question_id"]]
            if q["must_refuse"]:
                robust.append(r["refused"])
            elif q.get("ambiguity_markers"):
                robust.append(r["correct_answer"] and bool(r["ambiguity_flagged"]))
        out.append({
            "config": {"A": "A - No RAG", "B": "B - Basic RAG", "C": "C - Context-engineered RAG"}[config],
            "retrieval_correct": rate([r["correct_retrieval"] for r in subset]),
            "accuracy (correct answer)": rate([r["correct_answer"] for r in subset]),
            "faithfulness (grounded)": rate([r["grounded"] for r in subset]),
            "format compliance": rate([r["format_compliant"] for r in subset]),
            "robustness (Q4 flagged + Q5/Q6 refused)": rate(robust),
            "refused when needed (Q5/Q6)": rate([r["refused"] for r in subset if by_id[r["question_id"]]["must_refuse"]]),
            "false refusals (Q1-Q4)": sum(r["refused"] for r in subset if not by_id[r["question_id"]]["must_refuse"]),
            "mean context tokens": round(sum(r["context_tokens"] for r in subset) / max(1, len(subset)), 1),
            "mean LLM seconds": round(sum(r["llm_seconds"] for r in subset) / max(1, len(subset)), 1),
        })
    return out


# ---------------------------------------------------------------- output
def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in row.items()})


def flat(row: dict) -> dict:
    return {
        "question_id": row["question_id"],
        "question_type": row["question_type"],
        "config": row["config"],
        "top_k": row["top_k"],
        "retrieved_chunk_ids": ";".join(c["chunk_id"] for c in row["retrieved"]),
        "retrieved_scores": ";".join(f"{c['score']:.4f}" for c in row["retrieved"]),
        "context_chunk_ids": ";".join(c["chunk_id"] for c in row["context_chunks"]),
        "dropped": " | ".join(f"{c['chunk_id']}: {c['drop_reason']}" for c in row["dropped"]),
        "context_tokens": row["context_tokens"],
        "correct_retrieval": row["correct_retrieval"],
        "correct_answer": row["correct_answer"],
        "grounded": row["grounded"],
        "refused": row["refused"],
        "refused_when_needed": row["refused_when_needed"],
        "format_compliant": row["format_compliant"],
        "ambiguity_flagged": row["ambiguity_flagged"],
        "refused_by_filter": row["refused_by_filter"],
        "llm_seconds": row["llm_seconds"],
        "answer": row["answer"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieval-only", action="store_true", help="print retrievals, skip LLM calls")
    args = parser.parse_args()

    log_lines: list[str] = []

    def log(text: str = "") -> None:
        print(text, flush=True)
        log_lines.append(text)

    log(f"[{datetime.now(timezone.utc).isoformat()}] HW4 RAG run; model={LOCAL_MODEL}, embed={EMBED_MODEL}, "
        f"chunk_size={CHUNK_SIZE}, chunk_overlap={CHUNK_OVERLAP}, top_k={TOP_K}, seed={SEED}")
    questions = yaml.safe_load(QUESTIONS_PATH.read_text(encoding="utf-8"))["questions"]
    index, docs, nodes = build_index()
    log(f"Corpus: {len(docs)} documents -> {len(nodes)} chunks")
    for doc in docs:
        n = sum(1 for nd in nodes if nd.metadata["source"] == doc.metadata["source"])
        log(f"  {doc.metadata['source']:<45} {len(doc.text):>8,} chars  {n:>4} chunks")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(RAW_DIR / "rag_chunks.csv", [
        {"chunk_id": nd.metadata["chunk_id"], "source": nd.metadata["source"],
         "chars": len(nd.get_content()), "tokens": n_tokens(nd.get_content())}
        for nd in nodes
    ])

    retrievals: dict[tuple[str, int], list[dict]] = {}
    for q in questions:
        ks = sorted({TOP_K, *(K_SWEEP if q["id"] in K_SWEEP_QUESTIONS else [])})
        for k in ks:
            retrievals[(q["id"], k)] = retrieve(index, q["text"], k)
            log(format_retrievals(q["id"], q["text"], k, retrievals[(q["id"], k)]))
            if k == TOP_K:
                kept, dropped = engineer_context(retrievals[(q["id"], k)])
                log(f"  config C keeps {[c['chunk_id'] for c in kept]}; drops "
                    f"{[(c['chunk_id'], c['drop_reason']) for c in dropped]}")

    if args.retrieval_only:
        (RAW_DIR / "rag_retrievals.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
        return

    # --- three-configuration comparison at top_k = 3
    rows = []
    for q in questions:
        chunks = retrievals[(q["id"], TOP_K)]
        log(format_retrievals(q["id"], q["text"], TOP_K, chunks))
        for config in ["A", "B", "C"]:
            row = run_config(config, q, chunks, TOP_K)
            rows.append(row)
            log(f"\n--- {q['id']} config {config} ({row['llm_seconds']}s, context {row['context_tokens']} tokens) ---")
            if config == "C":
                log(f"    kept={[c['chunk_id'] for c in row['context_chunks']]} dropped={[(c['chunk_id'], c['drop_reason']) for c in row['dropped']]}")
            log(row["answer"])
            log(f"    -> correct_retrieval={row['correct_retrieval']} correct_answer={row['correct_answer']} "
                f"grounded={row['grounded']} refused={row['refused']} format={row['format_compliant']}")

    # --- k-sweep (reuses the k=3 rows)
    sweep = []
    for qid in K_SWEEP_QUESTIONS:
        q = next(q for q in questions if q["id"] == qid)
        for k in K_SWEEP:
            for config in ["B", "C"]:
                if k == TOP_K:
                    row = next(r for r in rows if r["question_id"] == qid and r["config"] == config)
                else:
                    row = run_config(config, q, retrievals[(qid, k)], k)
                    log(f"\n--- k-sweep {qid} k={k} config {config} ---")
                    log(row["answer"])
                relevant = [c for c in retrievals[(qid, k)]
                            if any(_matches(g, c["text"]) for g in q["retrieval_groups"])]
                sweep.append({
                    **flat(row),
                    "top_k": k,
                    "n_retrieved": len(retrievals[(qid, k)]),
                    "n_relevant_retrieved": len(relevant),
                    "n_irrelevant_retrieved": len(retrievals[(qid, k)]) - len(relevant),
                })

    summary = summarize(rows, questions)

    (RAW_DIR / "rag_retrievals.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    (RAW_DIR / "rag_three_config_comparison.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    write_csv(RAW_DIR / "rag_three_config_comparison.csv", [flat(r) for r in rows])
    write_csv(RAW_DIR / "rag_k_sweep.csv", sweep)
    write_csv(RAW_DIR / "rag_evaluation_table.csv", [
        {k: flat(r)[k] for k in ("question_id", "question_type", "config", "correct_retrieval", "correct_answer",
                                  "grounded", "refused_when_needed", "format_compliant", "ambiguity_flagged")}
        for r in rows
    ])
    write_csv(RAW_DIR / "rag_evaluation_summary.csv", summary)

    log("\n" + "=" * 100 + "\nEVALUATION SUMMARY")
    for s in summary:
        log(json.dumps(s))
    log(f"[{datetime.now(timezone.utc).isoformat()}] done")
    (RAW_DIR / "rag_retrievals.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
