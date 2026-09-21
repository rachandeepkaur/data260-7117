### 1. What I used an AI assistant for, and what I did myself

I used Claude (Anthropic) as a planning and debugging assistant. It helped me:
- break the session-management and RAG-corpus work into ordered steps;
- map HttpOnly/Secure/SameSite onto Starlette's `SessionMiddleware`;
- design the idle-timeout/logout logic (a server-side table of active sessions, keyed by a `sid` inside the signed cookie);
- identify what each downloaded PDF actually was (county, guide vs. individual inspection report) from its metadata/content;
- design a Recall@k check using a literal per-question keyword instead of the paraphrased expected answer;
- fix an install problem: PyTorch has no wheel for my Intel macOS + Python 3.13 machine, so `sentence-transformers`/`HuggingFaceEmbedding` couldn't install; it helped design a `fastembed` (ONNX) replacement with the same interface;
- tighten the wording of this section.

I did myself: sourced the corpus documents and their URLs/access dates; wrote `questions.yaml` and its expected answers from the documents, committed before any retrieval run; ran the three chunking pipelines and the metrics script; inspected flagged high-cosine misses by hand; took the screenshots. All numbers in the report come from my own runs, saved in `RUN_LOG.txt` and `raw/`.

### 2. AI output that was wrong or unsuitable, and what I independently verified

**Unsuitable (setup):** the first embedding setup followed the assignment literally (`HuggingFaceEmbedding`, needs `sentence-transformers`→`torch`). Failed: `pip install torch==2.2.2` → `ERROR: No matching distribution found for torch` - no PyTorch wheel exists for Intel x86_64 macOS on Python 3.13.

**Unsuitable (sessions):** Starlette's default `SessionMiddleware` keeps the session in a signed cookie with no server-side record, so logout only clears the *current* response's cookie - a copied old cookie still passes validation. I caught this myself: replaying a saved cookie with `curl` after logout returned `200` from `/dashboard` instead of a redirect.

**Independently verified:**
- Embedding replacement: confirmed 384-dim output (matches the `all-MiniLM-L6-v2` model card), and that two on-topic sentences score far higher (cosine 0.82) than an unrelated one (cosine 0.0006).
- Retrieval results: didn't treat cosine score as correctness - checked whether the retrieved chunk's actual text contained the answer.

### 3. How I detected the problems and verified the results

- **Install problem:** `pip install torch==2.2.2` failed with "No matching distribution found for torch"; confirmed the cause was the missing macOS x86_64 build for this Python version.
- **Session problem:** logged in with `curl -c`, saved the cookie, logged out, replayed the old cookie against `/dashboard` - before the fix: `200`; after adding the server-side `sid` table: `302 → /login`. Repeated after the idle timeout expired (temporarily set to 3s): `200` immediately after login, `302 → /login` after the timeout.
- **Retrieval quality:** Recall@3 is a string check - a hit means a literal `answer_keyword` (copied verbatim from the source document, not the paraphrased `expected_answer`) appears in any top-3 chunk's text. Used a verbatim keyword from the start, since the paraphrase would never match literally.
- **Confident-wrong retrieval:** filtered `raw/retrieval_runs.csv` for cosine ≥ 0.7 rows missing the keyword. Top example: `sentence_window`, question q4, rank 1, cosine 0.78, from `retail-food-inspection-guide.txt` - the chunk is genuinely about hot/cold holding (the 41-45°F exception) but doesn't contain the literal "135°F" keyword, so it's scored a miss despite being topically relevant.

### 4. What I changed and why it works now

- **Embeddings:** replaced `HuggingFaceEmbedding` with `FastEmbedONNXEmbedding` (`code/hw03/embeddings.py`), wrapping `fastembed`. Runs the same `all-MiniLM-L6-v2` weights on ONNXRuntime instead of PyTorch - same model, same embedding space, no `torch`. All three chunkers use it.
- **Sessions:** login creates a random `sid` stored in a server-side `_active_sessions` table with a last-seen time; `/dashboard` checks that table (not just the cookie) plus the idle timeout; logout deletes the entry. A replayed old or expired cookie now redirects to `/login`.
- **Cookie verification:** confirmed `httponly`/`samesite=lax`/`secure` directly in the raw `Set-Cookie` header via `curl -i`, and confirmed a real browser (Chromium via Playwright) actually stores and sends it - Chrome/Firefox treat `localhost` as a secure context, so a `Secure` cookie is testable there over plain HTTP.
- **Corpus cleaning:** `code/hw03/prepare_corpus.py` rejoins PDF-extracted lines hard-wrapped mid-sentence, and strips lines (headers/footers/page numbers) repeating across a threshold fraction of a document's pages.
- **Recall check:** Recall@3 defined on a verbatim `answer_keyword` per question (`questions.yaml`), computed reproducibly by `code/hw03/compute_metrics.py`.
