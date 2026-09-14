// Requirement Closure to track successful form submissions
// var countInc = 0;
const createSubmissionCounter = () => {
    let count = 0;
    return () => {
      count++;
      console.log(`Submission count (Closure): ${count}`);
      return count;
    };
  };
  
  const getSubmissionCount = createSubmissionCounter();

  // Toggles which of the three result states (empty / loading / error) is visible.
  // Pass "success" once analysisResults has been populated to hide the other two.
  const setResultState = (state) => {
    const emptyState = document.getElementById("emptyState");
    const errorState = document.getElementById("errorState");
    const loader = document.getElementById("loader");
    const loadingText = document.getElementById("loadingText");

    emptyState.hidden = state !== "empty";
    errorState.hidden = state !== "error";
    loader.hidden = state !== "loading";
    loadingText.hidden = state !== "loading";
  };

  // Renders the JSON returned by the FastAPI
  const renderAnalysis = (publish) => {
    const container = document.getElementById("analysisResults");
    if (!container) return;

    container.innerHTML = "";

    const heading = document.createElement("h2");
    heading.textContent = "Agent Analysis";
    container.appendChild(heading);

    const fields = [
      ["Title", publish.title],
      ["Tags", publish.tags.join(", ")],
      ["Summary", publish.summary],
      ["Reviewer Approved", String(publish.approved_by_reviewer)]
    ];

    fields.forEach(([label, value]) => {
      const p = document.createElement("p");
      const strong = document.createElement("strong");
      strong.textContent = `${label}: `;
      p.appendChild(strong);
      p.appendChild(document.createTextNode(value));
      container.appendChild(p);
    });
  };

  // --- Records CRUD table (Read/Update/Delete/Search) ---
  // The inspection form above is reused as the Create/Add action (see the
  // "Add to records store" block in the submit handler below); this state
  // only tracks what's needed to render and filter the table client-side.
  const recordsState = { records: [], query: "" };

  const setRecordsStatus = (message, isError = false) => {
    const status = document.getElementById("recordsStatus");
    status.textContent = message;
    status.classList.toggle("error", isError);
    status.classList.toggle("success", !isError && Boolean(message));
  };

  const renderRecordsTable = () => {
    const recordsBody = document.getElementById("recordsBody");
    const needle = recordsState.query.trim().toLowerCase();
    const filtered = needle
      ? recordsState.records.filter(
          (r) =>
            r.facility_name.toLowerCase().includes(needle) ||
            r.site_address.toLowerCase().includes(needle)
        )
      : recordsState.records;

    recordsBody.innerHTML = "";

    if (filtered.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 3;
      td.textContent = recordsState.records.length === 0 ? "No records yet." : "No records match.";
      tr.appendChild(td);
      recordsBody.appendChild(tr);
      return;
    }

    filtered.forEach((record) => {
      const tr = document.createElement("tr");
      [record.id, record.facility_name, record.site_address].forEach((value) => {
        const td = document.createElement("td");
        td.textContent = value;
        tr.appendChild(td);
      });
      recordsBody.appendChild(tr);
    });
  };

  const loadRecords = async () => {
    try {
      const response = await fetch("/api/records");
      if (!response.ok) throw new Error(`GET /api/records failed: ${response.status}`);
      recordsState.records = await response.json();
      renderRecordsTable();
    } catch (error) {
      console.error("Failed to load records:", error);
      setRecordsStatus("Failed to load records.", true);
    }
  };

  document.addEventListener("DOMContentLoaded", () => {
    loadRecords();

    document.getElementById("searchForm").addEventListener("submit", (event) => {
      event.preventDefault();
      recordsState.query = document.getElementById("searchInput").value;
      renderRecordsTable();
    });

    document.getElementById("clearSearchBtn").addEventListener("click", () => {
      document.getElementById("searchInput").value = "";
      recordsState.query = "";
      renderRecordsTable();
    });

    document.getElementById("updateForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.target;
      // NOTE: can't use form.id here - "id" collides with the built-in
      // HTMLFormElement.id (the <form id="updateForm"> attribute itself),
      // which shadows named-control lookup for the <input name="id">.
      const recordId = document.getElementById("update_id").value;
      const payload = { facility_name: document.getElementById("update_facility_name").value };

      try {
        const response = await fetch(`/api/records/${recordId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!response.ok) throw new Error(`PUT /api/records/${recordId} failed: ${response.status}`);
        form.reset();
        setRecordsStatus(`Record ${recordId} updated.`);
        await loadRecords();
      } catch (error) {
        console.error(`Failed to update record ${recordId}:`, error);
        setRecordsStatus(`Failed to update record ${recordId} (does it exist?).`, true);
      }
    });

    document.getElementById("deleteHighestBtn").addEventListener("click", async () => {
      try {
        const response = await fetch("/api/records/highest", { method: "DELETE" });
        if (!response.ok) throw new Error(`DELETE /api/records/highest failed: ${response.status}`);
        setRecordsStatus("Highest-ID record deleted.");
        await loadRecords();
      } catch (error) {
        console.error("Failed to delete highest-ID record:", error);
        setRecordsStatus("Failed to delete highest-ID record.", true);
      }
    });

    const form = document.getElementById("inspectionForm");

    // Validation using an Arrow Function
    const validateForm = (summary, isChecked) => {
      // Verify content field has strictly more than 25 characters
      if (summary.trim().length <= 25) {
        alert("Validation Error: Inspection Findings Summary must be more than 25 characters long.");
        return false;
      }
  
      // Verify terms and conditions checkbox is checked
      if (!isChecked) {
        alert("Validation Error: You must agree to the terms and conditions before submitting.");
        return false;
      }
  
      return true;
    };
  
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
  
      // Get input field values
      const facilityName = document.getElementById("facility_name").value;
      const siteAddress = document.getElementById("site_address").value;
      const inspectorEmail = document.getElementById("inspector_email").value;
      const inspectionSummary = document.getElementById("inspection_summary").value;
      const programElement = document.getElementById("program_element").value;
      const termsChecked = document.getElementById("terms").checked;
  
      // Run Arrow Function Validation — stop execution if invalid
      if (!validateForm(inspectionSummary, termsChecked)) {
        return;
      }
  
      // Convert form data into a JSON string and log output
      const formDataObj = {
        facility_name: facilityName,
        site_address: siteAddress,
        inspector_email: inspectorEmail,
        inspection_summary: inspectionSummary,
        program_element: programElement,
        agreed_to_terms: termsChecked
      };
  
      const jsonString = JSON.stringify(formDataObj);
      console.log("Form Data (JSON String):", jsonString);
  
      //Object destructuring to extract primary field and email field
      const parsedData = JSON.parse(jsonString);
      const { facility_name, inspector_email } = parsedData;
      console.log("Destructured Facility Name:", facility_name);
      console.log("Destructured Inspector Email:", inspector_email);
  
      // Spread operator to add submissionDate
      const updatedParsedData = {
        ...parsedData,
        submissionDate: new Date().toISOString()
      };
      console.log("Updated Parsed Object with Submission Date:", updatedParsedData);
  
      // IIncrement and log count via closure only upon successful submission
      const currentCount = getSubmissionCount();
      // const currentCount = countInc++;
      console.log(`Successful Submission Count: ${currentCount}`);
  
      alert(`Form submitted successfully! Total successful submissions: ${currentCount}`);

      // Add this submission to the records store (Create) so it shows up
      // in the table below, then refresh the table.
      try {
        const addResponse = await fetch("/api/records", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ facility_name: facilityName, site_address: siteAddress }),
        });
        if (!addResponse.ok) throw new Error(`POST /api/records failed: ${addResponse.status}`);
        setRecordsStatus("Record added.");
        await loadRecords();
      } catch (error) {
        console.error("Failed to add record to store:", error);
        setRecordsStatus("Failed to add record to the records table.", true);
      }

      // Send the submission to the FastAPI backend
      setResultState("loading");

      try {
        const response = await fetch("/api/analyze", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: jsonString
        });

        if (!response.ok) {
          throw new Error(`API responded with status ${response.status}`);
        }

        const publish = await response.json();
        console.log("Agent Pipeline Result:", publish);
        renderAnalysis(publish);
        setResultState("success");
      } catch (error) {
        console.error("Agent analysis request failed:", error);
        const errorState = document.getElementById("errorState");
        errorState.textContent = "Form submitted, but the agent analysis request failed. Please try again.";
        setResultState("error");
      }
    });
  });