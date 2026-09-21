"""Loads the cleaned corpus with SimpleDirectoryReader, restricted to the
.txt files prepare_corpus.py produced - never the source PDFs, so chunking
always runs against the cleaned text, not raw PDF extraction artifacts.

    python code/hw03/load_documents.py
"""
from __future__ import annotations

from pathlib import Path

from llama_index.core import SimpleDirectoryReader

CORPUS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "corpus"


def load_corpus_documents():
    reader = SimpleDirectoryReader(input_dir=str(CORPUS_DIR), required_exts=[".txt"])
    return reader.load_data()


def main() -> None:
    documents = load_corpus_documents()
    print(f"Loaded {len(documents)} document(s) from {CORPUS_DIR}")
    for doc in documents:
        filename = doc.metadata.get("file_name", "?")
        print(f"  {filename}: {len(doc.text):,} chars")


if __name__ == "__main__":
    main()
