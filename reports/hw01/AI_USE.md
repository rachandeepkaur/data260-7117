### Question 1: What you used an AI assistant for vs. what you did yourself
* **AI Assistant:** I Used AI to help me understand the assignment requirements and understanding each of the concepts such as used AI to learn core Docker concepts (e.g., base images, working directory setup, copying static files, exposing ports) and process of creating agent using langchain. I took AI's help to write the documentations. 
Amazon Q - AI helped identify and resolve port mapping and network access timeouts when deploying the Fargate service. Specifically, it diagnosed the initial page loading timeout (3.21.156.185 took too long to respond) as an issue caused by an missing inbound HTTP (Port 80) rule on the ECS task’s assigned Security Group (my-web-app-sg).

* **Self Effort:** Write the HTML, css and Javascript code creating the inspection form. Created and authored the `Dockerfile` manually, built the container image (`docker build -t data260-hw1 .`), and ran the container locally on port 8817 to verify app availability. Follow the provided documentation for deploying the docker image on aws ECR and obtaining the Public IP.

### Question 2: One AI-produced output that was wrong/unsuitable, or one issue you independently verified / resolved with AI
* **Issue Encountered:** Diagnosed a local browser error (`net::ERR_ACCESS_DENIED`) and page reloads when submitting the form under the `file://` protocol.
* **AI Assistance:** Used AI to explain how serving static files over an HTTP web server prevents browser access restrictions and properly enables JavaScript form intercepting.

### Question 3: How you detected the problem or verified the result
* **Detection:** Observed `file:///` errors and URL parameter appending in the browser console upon form submission.
* **Verification:** Built and started the Docker container mapping container port 80 to host port 8817 (`docker run -d -p 8817:80 data260-hw1`), opened `http://localhost:8817/HW01-RachandeepKaur.html`, and verified successful submission without console errors or page reloads.

### Question 4: What you changed and why it works now
* **Changes Made:** Packaged the HTML and JS assets into a Docker container served by Nginx and accessed the app via `http://localhost:8817/`.
* **Why It Works:** Serving the static site over HTTP via Nginx inside Docker eliminates local filesystem security blocks (`file://`), allowing `event.preventDefault()` and local scripts to run cleanly.

## Agent Pipeline (Planner / Reviewer / Publish)

### Question 1: What you used an AI assistant for vs. what you did yourself
* **AI Assistant:** Used AI to connect the form submission (`InspectionSubmission`) into `build_document()` to translate raw form fields into the title/content pair the agents consume, hooked the pipeline into `app.py`, and ran `python code/agents_demo.py` locally against `qwen3:8b` to validate the end-to-end flow with the domain fields defined in `DOMAIN_SCHEMA.md`. Also used AI to write the Planner/Reviewer system prompts that force raw-JSON-only responses, and to understand how `ChatOllama`'s `format="json"` option combined with LangChain's `bind_tools`/`invoke` works in `model_client.py`.
* **Self Effort:**  I have worked on designing the multi-agent architecture (Planner → Reviewer → Publish) in `agents_demo.py`, including how to structure the Pydantic models (`PlannerOutput`, `ReviewerOutput`, `RevisedOutput`, `PublishOutput`) so each stage's output is strictly typed and validated. Also used I write the Planner/Reviewer system prompts that force raw-JSON-only responses, and to understand how `ChatOllama`'s `format="json"` option combined with LangChain's `bind_tools`/`invoke` works in `model_client.py`.

### Question 2: One AI-produced output that was wrong/unsuitable, or one issue you independently verified / resolved with AI
* **Issue Encountered:** The Reviewer system prompt instructs that when `approved: true`, it should "populate `revised_output` with the planner's original data" verbatim. In practice, even on approved runs the model paraphrased the Planner's `draft_summary` in `revised_output.summary` instead of copying it unchanged (e.g., "faced issues with" → "had", "missing handwashing signs" reworded, "within 48 hours" → "48-hour corrective actions").
* **AI Assistance:** Discussed whether this was a genuine bug or acceptable behavior — concluded it's a soft-instruction-following gap: the model treats "populate with original data" as "keep it semantically the same" rather than "copy the string exactly," which the JSON schema itself doesn't enforce.

### Question 3: How you detected the problem or verified the result
* **Detection:** Ran the pipeline via `python code/agents_demo.py` and diffed the Planner's `draft_summary` against the Reviewer's `revised_output.summary` in the printed JSON output — despite `approved: true`, the two strings weren't identical.
* **Verification:** Re-ran the pipeline multiple times to confirm the tags (`health inspection`, `food safety`, `facility compliance`) stayed stable across Planner and Reviewer, while only the summary wording shifted slightly, confirming the pipeline's outputs were still schema-valid and factually consistent, just not byte-identical.

### Question 4: What you changed and why it works now
* **Changes Made:** Left the Reviewer prompt as-is rather than forcing exact string equality, since the retry/validation logic in `ModelClient.call()` (`model_client.py`) already guards the thing that actually matters: schema validity (exactly 3 tags, ≤25-word summary) via `output_format.model_validate()` with up to 3 retry attempts on `json.JSONDecodeError`/`ValidationError`.
* **Why It Works:** The pipeline's real correctness contract is the Pydantic schema (3 tags, word count, factuality), not verbatim text reuse between stages — so a Reviewer that "rewrites but still validates" is a feature of it acting as a genuine QA gate, not a bug to suppress.