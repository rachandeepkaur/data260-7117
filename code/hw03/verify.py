"""HW03 self-check script: confirms the pipeline's outputs are actually
present and internally consistent, and writes reports/hw03/verification.json.

    python code/hw03/verify.py

This does not re-run retrieval - it checks what prepare_corpus.py,
build_manifest.py, and run_retrieval.py already produced, plus a live
smoke test of the embedding backend.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS_DIR = REPO_ROOT / "data" / "corpus"
HW03_DIR = REPO_ROOT / "reports" / "hw03"
RAW_DIR = HW03_DIR / "raw"

EXPECTED_TECHNIQUES = {"token", "semantic", "sentence_window"}
EXPECTED_TOP_K = 3


def check_corpus_files() -> dict:
    pdfs = sorted(p.name for p in CORPUS_DIR.glob("*.pdf"))
    txts = sorted(p.name for p in CORPUS_DIR.glob("*.txt"))
    passed = len(pdfs) == 4 and len(txts) == 4 and len(pdfs) == len(txts)
    return {
        "name": "corpus_files_present",
        "description": "data/corpus/ has one cleaned .txt per source .pdf",
        "passed": passed,
        "evidence": f"{len(pdfs)} pdf(s): {pdfs}; {len(txts)} txt(s): {txts}",
    }


def check_manifest_hashes() -> dict:
    manifest_path = HW03_DIR / "CORPUS_MANIFEST.json"
    if not manifest_path.exists():
        return {
            "name": "corpus_manifest_hashes",
            "description": "CORPUS_MANIFEST.json's SHA-256 for every file matches the file on disk",
            "passed": False,
            "evidence": "CORPUS_MANIFEST.json not found",
        }
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mismatches = []
    for entry in manifest:
        file_path = CORPUS_DIR / entry["file"]
        if not file_path.exists():
            mismatches.append(f"{entry['file']}: missing on disk")
            continue
        actual_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if actual_hash != entry["sha256"]:
            mismatches.append(f"{entry['file']}: hash mismatch")
    passed = len(manifest) > 0 and not mismatches
    return {
        "name": "corpus_manifest_hashes",
        "description": "CORPUS_MANIFEST.json's SHA-256 for every file matches the file on disk",
        "passed": passed,
        "evidence": f"{len(manifest)} entries checked, {len(mismatches)} mismatch(es): {mismatches}",
    }


def check_questions_yaml() -> dict:
    questions_path = HW03_DIR / "questions.yaml"
    if not questions_path.exists():
        return {
            "name": "questions_yaml_complete",
            "description": "questions.yaml has 5 questions, each with an answer_keyword",
            "passed": False,
            "evidence": "questions.yaml not found",
        }
    data = yaml.safe_load(questions_path.read_text(encoding="utf-8"))
    questions = data.get("questions", [])
    missing_fields = [
        q.get("id", "?") for q in questions
        if not q.get("answer_keyword") or not q.get("expected_answer")
    ]
    passed = len(questions) == 5 and not missing_fields
    return {
        "name": "questions_yaml_complete",
        "description": "questions.yaml has 5 questions, each with an answer_keyword",
        "passed": passed,
        "evidence": f"{len(questions)} question(s); missing required fields on: {missing_fields}",
    }


def check_raw_retrieval_data() -> dict:
    runs_path = RAW_DIR / "retrieval_runs.csv"
    if not runs_path.exists():
        return {
            "name": "raw_retrieval_data_shape",
            "description": f"raw/retrieval_runs.csv has all {len(EXPECTED_TECHNIQUES)} techniques x 5 questions x top-{EXPECTED_TOP_K}",
            "passed": False,
            "evidence": "raw/retrieval_runs.csv not found",
        }
    runs = pd.read_csv(runs_path)
    techniques_seen = set(runs["technique"].unique())
    question_counts = runs.groupby("technique")["question_id"].nunique().to_dict()
    rows_per_technique = runs.groupby("technique").size().to_dict()
    passed = (
        techniques_seen == EXPECTED_TECHNIQUES
        and all(c == 5 for c in question_counts.values())
        and all(n == 5 * EXPECTED_TOP_K for n in rows_per_technique.values())
    )
    return {
        "name": "raw_retrieval_data_shape",
        "description": f"raw/retrieval_runs.csv has all {len(EXPECTED_TECHNIQUES)} techniques x 5 questions x top-{EXPECTED_TOP_K}",
        "passed": passed,
        "evidence": f"techniques={sorted(techniques_seen)}, questions_per_technique={question_counts}, rows_per_technique={rows_per_technique}",
    }


def check_chunk_stats() -> dict:
    stats_path = RAW_DIR / "chunk_stats.csv"
    if not stats_path.exists():
        return {
            "name": "chunk_stats_present",
            "description": "raw/chunk_stats.csv has a nonzero chunk count for all three techniques",
            "passed": False,
            "evidence": "raw/chunk_stats.csv not found",
        }
    stats = pd.read_csv(stats_path)
    counts = stats.groupby("technique").size().to_dict()
    passed = set(counts.keys()) == EXPECTED_TECHNIQUES and all(v > 0 for v in counts.values())
    return {
        "name": "chunk_stats_present",
        "description": "raw/chunk_stats.csv has a nonzero chunk count for all three techniques",
        "passed": passed,
        "evidence": f"chunk counts: {counts}",
    }


def check_embedding_backend() -> dict:
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from embeddings import FastEmbedONNXEmbedding

        embed = FastEmbedONNXEmbedding()
        vec = embed.get_query_embedding("test")
        passed = len(vec) == 384
        evidence = f"get_query_embedding('test') returned a {len(vec)}-dim vector"
    except Exception as exc:  # noqa: BLE001
        passed = False
        evidence = f"raised {type(exc).__name__}: {exc}"
    return {
        "name": "embedding_backend_dimension",
        "description": "FastEmbedONNXEmbedding produces 384-dim vectors (all-MiniLM-L6-v2)",
        "passed": passed,
        "evidence": evidence,
    }


def check_metrics_filled() -> dict:
    metrics_path = HW03_DIR / "METRICS.md"
    if not metrics_path.exists():
        return {
            "name": "metrics_table_filled",
            "description": "METRICS.md's results table has no leftover TODO placeholders",
            "passed": False,
            "evidence": "METRICS.md not found",
        }
    text = metrics_path.read_text(encoding="utf-8")
    passed = "TODO" not in text
    return {
        "name": "metrics_table_filled",
        "description": "METRICS.md's results table has no leftover TODO placeholders",
        "passed": passed,
        "evidence": "no 'TODO' found in METRICS.md" if passed else "'TODO' still present in METRICS.md",
    }


def get_commit_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return ""


def main() -> None:
    checks = [
        check_corpus_files(),
        check_manifest_hashes(),
        check_questions_yaml(),
        check_raw_retrieval_data(),
        check_chunk_stats(),
        check_embedding_backend(),
        check_metrics_filled(),
    ]

    for check in checks:
        status = "PASS" if check["passed"] else "FAIL"
        print(f"[{status}] {check['name']}: {check['evidence']}")

    passed_count = sum(1 for c in checks if c["passed"])
    result = {
        "homework": "HW3",
        "SID4": "7117",
        "commit_hash": get_commit_hash(),
        "commit_note": "HW03 self-check",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "summary": {
            "total_checks": len(checks),
            "passed": passed_count,
            "failed": len(checks) - passed_count,
        },
    }

    output_path = HW03_DIR / "verification.json"
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"\n{passed_count}/{len(checks)} checks passed. Wrote {output_path}")


if __name__ == "__main__":
    main()
