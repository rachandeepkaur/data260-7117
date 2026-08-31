# Domain Schema: Local Restaurant Inspections

## Entity Overview
This schema defines the structure for submitting local restaurant health and safety inspection records within the assigned domain (DOMAIN_ID: 5 - Local restaurant inspections).

## Entity Fields & Validation Rules

### 1. Facility Name / ID (Primary Field)
- **Field Name:** `facility_name`
- **Data Type:** String
- **Required:** Yes
- **Validation:** Must not be empty. Cursor auto-focuses on this field on page load (`autofocus`).
- **Placeholder:** `"e.g., FA0206933 - YUMMY KITCHEN"`
- **Example Value:** `FA0206933 - YUMMY KITCHEN`

### 2. Program Site Address (Secondary Field)
- **Field Name:** `site_address`
- **Data Type:** String
- **Required:** Yes
- **Validation:** Must not be empty.
- **Placeholder:** `"e.g., 1711 BRANHAM LN A9, SAN JOSE, CA 95118"`
- **Example Value:** `1711 BRANHAM LN A9, SAN JOSE, CA 95118`

### 3. Submitter Email
- **Field Name:** `inspector_email`
- **Data Type:** String (Email format)
- **Required:** Yes
- **Validation:** Must be a valid email address structure (`user@domain.com`).
- **Placeholder:** `"e.g., inspector@countyhealth.gov"`

### 4. Inspection Findings Summary (Content / Description)
- **Field Name:** `inspection_summary`
- **Data Type:** Text
- **Required:** Yes
- **Validation:** Must contain strictly more than 25 characters (`length > 25`).
- **Placeholder:** `"Describe inspection findings, violations, or compliance observations (min 26 characters)..."`

### 5. Program Element / Category
- **Field Name:** `program_element`
- **Data Type:** Enum / Dropdown Select
- **Required:** Yes
- **Allowed Category Values:**
  1. `FOOD PREP / FOOD SVC OP 0-5 EMPLOYEES RC 3 - FP11`
  2. `FOOD PREP / FOOD SVC OP 6-25 EMPLOYEES`
  3. `ROUTINE HEALTH INSPECTION`
  4. `FOLLOW-UP COMPLIANCE CHECK`

### 6. Terms and Conditions
- **Field Name:** `agreed_to_terms`
- **Data Type:** Boolean (Checkbox)
- **Required:** Yes
- **Validation:** Must be explicitly checked (`true`) upon form submission.
- **Label Text:** `"I agree to the terms and conditions."`