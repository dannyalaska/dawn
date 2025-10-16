# DAWN API Reference

## Base URL
- Development: `http://127.0.0.1:8000`
- Production: Set via `API_BASE` environment variable

## Authentication
Currently no authentication required (add in production deployment).

Provide API keys, database DSNs, and other secrets through environment variables (`.env` is ignored by git). Nothing in this repository contains live credentials.

---

## Feeds API

### POST `/feeds/ingest`
Ingest a new feed or create a new version of an existing feed.

**Content-Type:** `multipart/form-data`

**Form Parameters:**
- `identifier` (required, string, min 3 chars): Unique feed identifier (e.g., "customers", "transactions")
- `name` (required, string): Human-readable feed name
- `source_type` (optional, string, default="upload"): One of: "upload", "s3", "http"
- `data_format` (optional, string): "csv" or "excel" (auto-detected if not provided)
- `owner` (optional, string): Feed owner/team name
- `sheet` (optional, string): Excel sheet name (required for Excel files with multiple sheets)
- `s3_path` (optional, string): S3 path (e.g., "s3://bucket/path/file.csv") when source_type="s3"
- `http_url` (optional, string): HTTP URL when source_type="http"
- `file` (optional, file): File upload when source_type="upload"

**Response:**
```json
{
  "feed": {
    "identifier": "customers",
    "name": "Customer Master",
    "version": 1
  },
  "version": {
    "version": 1,
    "sha16": "a1b2c3d4e5f6...",
    "row_count": 15000,
    "column_count": 12,
    "json": {
      "text": "Customer data with 15,000 rows...",
      "columns": [...],
      "metrics": [...],
      "mermaid": "erDiagram..."
    }
  },
  "manifest": {...},
  "drift": {
    "status": "new" | "no_change" | "changed",
    "message": "...",
    "changes": {...}
  }
}
```

**Example (Upload):**
```python
import requests

files = {"file": ("customers.csv", open("customers.csv", "rb"), "text/csv")}
data = {
    "identifier": "customers",
    "name": "Customer Master",
    "source_type": "upload",
    "owner": "Data Team"
}
response = requests.post("http://127.0.0.1:8000/feeds/ingest", data=data, files=files)
```

**Example (S3):**
```python
data = {
    "identifier": "transactions",
    "name": "Daily Transactions",
    "source_type": "s3",
    "s3_path": "s3://my-bucket/data/transactions.csv",
    "owner": "Finance Team"
}
response = requests.post("http://127.0.0.1:8000/feeds/ingest", data=data)
```

---

### GET `/feeds`
List all registered feeds with their latest version metadata.

**Response:**
```json
{
  "feeds": [
    {
      "identifier": "support_tickets",
      "name": "Support Tickets",
      "owner": "Ops Enablement",
      "source_type": "upload",
      "format": "excel",
      "favorite_sheet": "Tickets",
      "latest_version": {
        "number": 1,
        "rows": 1200,
        "columns": 14,
        "sha16": "a1b2c3d4e5f6",
        "sheet": "Tickets",
        "sheet_names": ["Tickets", "Agents"],
        "summary": {...},
        "profile": {...},
        "schema": {...}
      }
    }
  ]
}
```
`summary`, `profile`, and `schema` mirror the structures returned from ingestion, including `sample_rows`, analysis plans, and column profiling.

---

### GET `/feeds/{identifier}`
Fetch all stored versions for a specific feed.

**Response:**
```json
{
  "identifier": "support_tickets",
  "name": "Support Tickets",
  "favorite_sheet": "Tickets",
  "latest_version": {
    "number": 2,
    "rows": 1500,
    "columns": 16,
    "summary": {...}
  },
  "versions": [
    {
      "number": 2,
      "rows": 1500,
      "columns": 16,
      "sha16": "aaaabbbbccccdddd",
      "created_at": "2024-05-01T10:12:55",
      "summary": {...},
      "profile": {...},
      "schema": {...}
    },
    {
      "number": 1,
      "rows": 1200,
      "columns": 14,
      "sha16": "1111222233334444",
      "created_at": "2024-04-15T08:21:12",
      "summary": {...},
      "profile": {...},
      "schema": {...}
    }
  ]
}
```

---

### POST `/feeds/{identifier}/favorite`
Persist the default worksheet to highlight in the UI.

**Request Body:**
```json
{ "sheet": "Tickets" }
```

**Response:**
Returns the updated feed payload (same shape as `GET /feeds/{identifier}`).

---

## Jobs API

### GET `/jobs`
List all jobs.

**Response:**
```json
{
  "jobs": [
    {
      "id": 1,
      "name": "Daily Customer Refresh",
      "feed": "customers",
      "feed_version": 3,
      "transform_version": null,
      "schedule": "0 2 * * *",
      "is_active": true,
      "created_at": "2025-10-13T10:00:00",
      "last_run": {
        "id": 42,
        "status": "success",
        "started_at": "2025-10-13T02:00:00",
        "finished_at": "2025-10-13T02:05:23",
        "rows_in": 15000,
        "rows_out": 15000
      }
    }
  ]
}
```

### POST `/jobs`
Create a new job.

**Request Body:**
```json
{
  "name": "Daily Customer Refresh",
  "feed_identifier": "customers",
  "feed_version": null,  // null = use latest
  "transform_name": null,  // optional transform to apply
  "transform_version": null,  // null = use latest
  "schedule": "0 2 * * *",  // cron expression or null for manual-only
  "is_active": true
}
```

**Cron Format:** Standard 5-field cron: `minute hour day month weekday`
- `0 2 * * *` - Daily at 2:00 AM
- `0 */6 * * *` - Every 6 hours
- `0 9 * * 1` - Every Monday at 9:00 AM

**Response:**
```json
{
  "id": 1,
  "name": "Daily Customer Refresh",
  "feed": "customers",
  "feed_version": 3,
  "schedule": "0 2 * * *",
  "is_active": true,
  "created_at": "2025-10-13T10:00:00",
  "last_run": null
}
```

### GET `/jobs/{job_id}`
Get job details including run history.

### POST `/jobs/{job_id}/run`
Manually trigger a job run (coming soon).

### PATCH `/jobs/{job_id}`
Update job schedule or active status (coming soon).

---

## Transforms API

### POST `/transforms`
Create or update a transform definition.

**Request Body:**
```json
{
  "definition": {
    "name": "cleaned_customers",
    "feed_identifier": "customers",
    "description": "Clean and standardize customer data",
    "steps": [
      {
        "type": "rename",
        "mapping": {"cust_id": "customer_id", "cust_name": "name"}
      },
      {
        "type": "filter",
        "column": "status",
        "op": "eq",
        "value": "active"
      },
      {
        "type": "select",
        "columns": ["customer_id", "name", "email", "created_at"]
      }
    ]
  },
  "sample_rows": [...],  // optional: test data for dry run
  "context_samples": {}  // optional: for join steps
}
```

**Supported Transform Steps:**
- `RenameStep`: Rename columns
- `FilterStep`: Filter rows by condition
- `SelectStep`: Select specific columns
- `DropStep`: Drop columns
- `CastStep`: Change column data types
- `FillNAStep`: Fill null values
- `ParseDatetimeStep`: Parse datetime columns
- `StringCleanStep`: Trim/normalize strings
- `MergeColumnsStep`: Concatenate columns
- `JoinStep`: Join with another feed

**Response:**
```json
{
  "transform_id": 1,
  "version": 1,
  "script": "# Python script...",
  "dbt_model": "-- DBT SQL...",
  "dry_run": {
    "input_rows": 100,
    "output_rows": 85,
    "output_columns": ["customer_id", "name", "email", "created_at"],
    "sample": [...]
  }
}
```

---

## NL-to-SQL API

### POST `/nl/sql`
Convert natural language question to SQL.

**Request Body:**
```json
{
  "question": "Show me the top 10 customers by revenue",
  "feed_identifiers": ["customers", "transactions"],  // optional: scope to specific feeds
  "allow_writes": false,
  "explain": true,
  "dialect": "duckdb"
}
```

**Response:**
```json
{
  "sql": "SELECT c.name, SUM(t.amount) as revenue...",
  "validation": {
    "ok": true,
    "errors": [],
    "warnings": []
  },
  "explain_plan": "Execution plan...",
  "manifest_used": [...]
}
```

---

## RAG API

### POST `/rag/search`
Search across feed documentation and metadata.

**Request Body:**
```json
{
  "query": "customer data schema",
  "top_k": 5
}
```

**Response:**
```json
{
  "results": [
    {
      "content": "Customer Master contains...",
      "score": 0.92,
      "metadata": {
        "feed": "customers",
        "type": "schema"
      }
    }
  ]
}
```

### POST `/rag/ask`
Ask questions about feeds using RAG + LLM.

**Request Body:**
```json
{
  "question": "What customer data do we have?",
  "stream": false
}
```

---

## Excel API

### POST `/excel/upload`
Upload and analyze Excel file.

### POST `/excel/preview`
Preview worksheet before ingestion.

---

## Error Responses

All endpoints return errors in this format:
```json
{
  "detail": "Error message"
}
```

**Common Status Codes:**
- `400` - Bad Request (validation errors)
- `404` - Resource Not Found
- `500` - Internal Server Error
