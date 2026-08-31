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

  document.addEventListener("DOMContentLoaded", () => {
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

      // Send the submission to the FastAPI backend
      const loader = document.getElementById("loader");
      loader.hidden = false;

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
      } catch (error) {
        console.error("Agent analysis request failed:", error);
        alert("Form submitted, but the agent analysis request failed. See console for details.");
      } finally {
        loader.hidden = true;
      }
    });
  });