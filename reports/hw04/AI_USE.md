# AI Use

### 1. What I used an AI assistant for, and what I did myself

I used Claude Code (Anthropic) as a coding agent in VS Code. It:

- used AI to write the reports and debugging errors
- to draft sql migration queries
- wrote the seed, benchmark, EXPLAIN, metrics and the Makefile
- I was not able to install MySql directly using homebrew on my machine so took help from AI to resolve the issue and use it using Docker container

What I did myself: Wrote the code files and reviewed each and every code generated through AI. Choose the questions and verified their answers. Created the database migrations  and ran all the apis in Postman. Integrated apis to frontend and tested all the functionalities from React UI. 

### 2. One AI-produced output that was wrong, and one thing I verified independently

**Wrong:** the first `UpdateRecord.jsx` loaded the record inside `useEffect` with no cleanup.
In development, React StrictMode runs effects twice. The second, late response overwrote the name
already typed into the form, so **Update** sent the *old* name. The page still redirected to Home
with no error.

**Verified independently:** the RAG evaluator's *grounded* flag. Config C answered Q3 with "45°F".
It was marked grounded, because 45 appears in the cited chunk, but the answer was wrong. I read
chunk `retail-food-inspection-guide#039` myself. It is about the 45°F *exception* for shellfish,
eggs and milk. The 41°F cold-holding rule was in Source 3 (`abc-retail-food-inspection-guide.pdf#022`).

### 3. How I detected the problem / verified the result

•    Update bug: headless-Chromium end-to-end test (log in → create → edit → delete) failed when waiting

for the renamed row to appear; API log revealed PUT /api/records/5003 → 200, meaning backend accepted

the request; body contained original value. Two GET /api/records/5003 requests per page load were in the

API log too; the double effect.

•    Grounded vs. correct: I checked the grounded and correct_answer columns in

raw/rag_evaluation_table.csv and identified rows which were grounded but incorrect. Then I opened the

chunk text for each row in raw/rag_retrievals.txt.

•    I additionally verified the N+1 numbers in the code rather than in the table. In [verify.py](http://verify.py) there is an assertion

of exactly N+1 statements (naive) versus 2 (fixed), with equal items. EXPLAIN proves the index used correctly.

### 4. What I changed and why it works now

- Update/Delete pages: the fetch effect now sets an ignore flag locally in cleanup, and discards
- any response that arrives after cleanup is done. Only the most recent fetch can populate the form. The
- inputs are disabled until then. The same test case in Chromium passes: create → rename → delete.
- Evaluation: I did not change the automatic scores, but report the Q3 case as a known limitation.
- The grounded evaluation ensures that the facts in the answer actually exist in the context. This does
- not ensure whether the model has selected the right fact. Thus, faithfulness (100% for C) and accuracy (4/6)
- are to be considered together.
- Other suggestions I evaluated and kept:

MySQL works in Docker, since Homebrew does not include bottles anymore for Intel macOS and fails in building from source in the test stage;

bge-small-en-v1.5 is used instead of MiniLM of HW3, as it uses 512 token windows, which fit the 500 token chunk size without truncating;

CORS allows origins to be listed explicitly, as a * origin cannot be combined with credentialed (cookie) requests. 