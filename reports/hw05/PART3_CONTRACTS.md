# Part 3 — Tool contracts under stress (Q18)

The three rejected calls below are the same intentionally invalid calls made in MCP Inspector for Part 2B (`make mcp-domain`; raw responses in `raw/mcp_inspector_outputs.json`). Every input model uses `extra="forbid"`, so unknown fields are rejected too. Validation happens in `execute_tool` *before* any storage call, so no retry is attempted and the error is returned in the shared `{ok, data, error}` envelope.

## search_inspections

**Expected input JSON Schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "query": {
      "description": "Text to match in facility name or address, or an exact inspection code",
      "maxLength": 100,
      "minLength": 2,
      "title": "Query",
      "type": "string"
    },
    "limit": {
      "default": 10,
      "description": "Max results (1-25)",
      "maximum": 25,
      "minimum": 1,
      "title": "Limit",
      "type": "integer"
    },
    "min_score": {
      "anyOf": [
        {
          "maximum": 100,
          "minimum": 0,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Only scores >= this",
      "title": "Min Score"
    }
  },
  "required": [
    "query"
  ],
  "title": "SearchInput",
  "type": "object"
}
```

**Rejected input**

```json
{"query": "golden", "limit": 500}
```

**Returned error output**

```json
{
  "ok": false,
  "data": null,
  "error": "invalid input for search_inspections: limit: Input should be less than or equal to 25"
}
```

**Why it was rejected:** `limit` is constrained to 1–25 (`maximum: 25`). 500 would turn a lookup into a bulk export of the inspection table and flood the agent's context, so the contract rejects it before any SQL runs.

## get_inspection

**Expected input JSON Schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "inspection_code": {
      "description": "Inspection code, e.g. INS-000042",
      "pattern": "^INS-\\d{6}$",
      "title": "Inspection Code",
      "type": "string"
    }
  },
  "required": [
    "inspection_code"
  ],
  "title": "DetailInput",
  "type": "object"
}
```

**Rejected input**

```json
{"inspection_code": "12345"}
```

**Returned error output**

```json
{
  "ok": false,
  "data": null,
  "error": "invalid input for get_inspection: inspection_code: String should match pattern '^INS-\\d{6}$'"
}
```

**Why it was rejected:** `inspection_code` must match `^INS-\d{6}$`. `12345` is a bare number (looks like a row id, not an inspection code), so it is rejected as a format error instead of being sent to MySQL as a lookup that can never match.

## inspection_stats

**Expected input JSON Schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "inspector_id": {
      "anyOf": [
        {
          "minimum": 1,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Only this inspector's inspections",
      "title": "Inspector Id"
    },
    "zip_code": {
      "anyOf": [
        {
          "pattern": "^\\d{5}$",
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "5-digit San Jose ZIP",
      "title": "Zip Code"
    },
    "facility_query": {
      "anyOf": [
        {
          "maxLength": 100,
          "minLength": 2,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Substring of the facility name",
      "title": "Facility Query"
    }
  },
  "title": "StatsInput",
  "type": "object"
}
```

**Rejected input**

```json
{"zip_code": "95A18"}
```

**Returned error output**

```json
{
  "ok": false,
  "data": null,
  "error": "invalid input for inspection_stats: zip_code: String should match pattern '^\\d{5}$'"
}
```

**Why it was rejected:** `zip_code` must be exactly 5 digits (`^\d{5}$`). `95A18` contains a letter; a malformed ZIP would silently match nothing and return a misleading empty aggregate, so it is rejected explicitly.
