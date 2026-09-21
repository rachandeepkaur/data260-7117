"""Extracts text from every PDF in data/corpus/ and cleans it before chunking.

    python code/hw03/prepare_corpus.py

Writes one <name>.txt per <name>.pdf, next to the source PDF (so
SimpleDirectoryReader can later be pointed at data/corpus/ with
required_exts=[".txt"] and only see the cleaned text, never the PDFs).

Two cleanup passes are applied to the raw pypdf extraction, since leaving
either in place actively hurts sentence-window chunking:

1. Hard line-wrap rejoin: pypdf's extract_text() emits one line per visual
   line on the page, so a wrapped sentence ends up split across two lines
   with no space between them. Lines are rejoined into their paragraph
   unless the line already ends in sentence-terminal punctuation or the
   next line starts a new bullet/numbered item (so real list structure is
   kept, not flattened into one run-on line).
2. Repeated header/footer/page-number removal: a line that recurs on a
   large fraction of a document's pages (a running header, a footer
   address block, a "Page X of Y" line) is dropped everywhere it appears,
   since otherwise every single chunk from that document would carry the
   same boilerplate sentence tacked onto it.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

CORPUS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "corpus"

_PAGE_NUMBER_RE = re.compile(r"^(page\s+)?\d+(\s+of\s+\d+)?$", re.IGNORECASE)
_SENTENCE_END_RE = re.compile(r"[.!?:;\"')\]]$")
_LIST_START_RE = re.compile(r"^([•\-\*]|\d+[.)]|\(\w+\))\s")

# A line is boilerplate if it's a bare page number, or if it recurs on at
# least this fraction of the document's pages (only checked for documents
# with more than a couple of pages, so a genuinely short doc isn't gutted).
_REPEAT_FRACTION_THRESHOLD = 0.4


def _extract_pages(pdf_path: Path) -> list[str]:
    reader = PdfReader(str(pdf_path))
    return [page.extract_text() or "" for page in reader.pages]


def _find_boilerplate_lines(pages: list[str]) -> set[str]:
    """Lines that repeat across a large fraction of the document's pages."""
    line_page_counts: Counter[str] = Counter()
    for page_text in pages:
        seen_on_this_page = set()
        for raw_line in page_text.split("\n"):
            line = raw_line.strip()
            if line and line not in seen_on_this_page:
                line_page_counts[line] += 1
                seen_on_this_page.add(line)

    if len(pages) <= 1:
        return set()  # nothing to repeat against

    threshold = max(2, int(len(pages) * _REPEAT_FRACTION_THRESHOLD))
    return {line for line, count in line_page_counts.items() if count >= threshold}


def _rejoin_wrapped_lines(lines: list[str]) -> list[str]:
    """Merges a hard-wrapped sentence's lines back into one line each."""
    merged: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            merged.append("")  # marks a paragraph break
            continue
        prev = merged[-1] if merged else ""
        if prev and not _SENTENCE_END_RE.search(prev) and not _LIST_START_RE.match(line):
            merged[-1] = f"{prev} {line}"
        else:
            merged.append(line)
    return merged


def clean_pdf_text(pages: list[str]) -> str:
    boilerplate = _find_boilerplate_lines(pages)

    cleaned_pages = []
    for page_text in pages:
        kept_lines = [
            line for line in page_text.split("\n")
            if line.strip() not in boilerplate and not _PAGE_NUMBER_RE.match(line.strip())
        ]
        merged = _rejoin_wrapped_lines(kept_lines)
        paragraph_text = "\n".join(line for line in merged if line)
        if paragraph_text.strip():
            cleaned_pages.append(paragraph_text)

    return "\n\n".join(cleaned_pages)


def main() -> None:
    pdf_paths = sorted(CORPUS_DIR.glob("*.pdf"))
    if not pdf_paths:
        print(f"No PDFs found in {CORPUS_DIR}")
        return

    for pdf_path in pdf_paths:
        pages = _extract_pages(pdf_path)
        cleaned_text = clean_pdf_text(pages)
        txt_path = pdf_path.with_suffix(".txt")
        txt_path.write_text(cleaned_text, encoding="utf-8")
        print(f"{pdf_path.name}: {len(pages)} pages -> {txt_path.name} ({len(cleaned_text):,} chars)")


if __name__ == "__main__":
    main()
