### Question 1: What you used an AI assistant for vs. what you did yourself
* **AI Assistant:** I Used AI to help me understand the assignment requirements and understanding each of the concepts such as used AI to learn core Docker concepts (e.g., base images, working directory setup, copying static files, exposing ports) and process of creating agent using langchain. I took AI's help to write the documentations.

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