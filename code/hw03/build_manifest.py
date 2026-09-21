"""Builds reports/hw03/CORPUS_MANIFEST.json from data/corpus/: filename,
byte size, and SHA-256 of every local corpus file (both the source PDFs
and the cleaned .txt files prepare_corpus.py produces from them).

    python code/hw03/build_manifest.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS_DIR = REPO_ROOT / "data" / "corpus"
MANIFEST_PATH = REPO_ROOT / "reports" / "hw03" / "CORPUS_MANIFEST.json"


def main() -> None:
    rows = []
    for filename in sorted(p.name for p in CORPUS_DIR.iterdir() if p.is_file()):
        data = (CORPUS_DIR / filename).read_bytes()
        rows.append({
            "file": filename,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })

    MANIFEST_PATH.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} entries to {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
