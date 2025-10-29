# DAWN User Guide

## Table of Contents
1. [Getting Started](#getting-started)
2. [Feed Onboarding](#feed-onboarding)
3. [Asking Questions](#asking-questions)
4. [Working with Datafeeds](#working-with-datafeeds)
5. [Creating Transforms](#creating-transforms)
6. [Scheduling Jobs](#scheduling-jobs)
7. [Natural Language Queries](#natural-language-queries)
8. [Multi-agent Runs](#multi-agent-runs)

---

## Getting Started

### What is DAWN?
DAWN (Data Awareness & Workflow Navigator) is a platform for managing, transforming, and querying data feeds. It provides:
- **Automatic schema profiling** and drift detection
- **Data quality rules** with automated monitoring
- **Natural language SQL** generation
- **Transform pipelines** with version control
- **Scheduled jobs** for automated refresh

> **Note:** All sample workbooks and transform definitions in this repo are synthetic and safe to share publicly. Bring your own data by copying `.env.example` → `.env` and pointing DAWN at your Redis/Postgres instances.

### Starting DAWN
```bash
cd /path/to/dawn
./start_dawn.sh
```

This starts:
- FastAPI backend at `http://127.0.0.1:8000`
- Streamlit UI at `http://127.0.0.1:8501`

Visit `http://127.0.0.1:8501` in your browser to access the UI.

---

## Feed Onboarding

### Step 1: Upload from “Upload & Preview”
1. Open DAWN in your browser and stay on the default **Upload & Preview** tab.
2. Drag an Excel workbook (`.xlsx`, `.xlsm`, `.xls`) into the uploader.
3. Optionally provide a sheet name; otherwise Dawn inspects the first sheet.
4. Click **Generate preview** to profile the workbook locally.

### Step 2: Inspect the profile
After the preview finishes you’ll see:
- Row/column counts and whether the preview was served from cache.
- Column-level metadata (dtype, sample values, null counts).
- The first 50 sample rows to spot obvious data issues.

If the preview looks off, update the sheet selector and rerun the preview.

### Step 3: Index it into Redis
1. Adjust note size, overlap, and retrieval `k` from the sidebar if needed.
2. Click **Index dataset** to capture context notes and push vectors into Redis.
3. When indexing completes Dawn stores a richer summary (top values, aggregates, analysis plan suggestions).
4. The app automatically switches the active context source so you can move straight to note taking or Q&A.

Review the schema cards and adjust if needed.

### Step 5: Configure Data Quality
Auto-generated DQ rules include:
- **Primary Key Uniqueness**: Ensures no duplicates
- **Null Thresholds**: Alerts if nulls exceed baseline
- **Datetime Freshness**: Checks for recent data

You can review and customize these rules in the DQ panel.

### Step 6: Schedule (Optional)
Configure when to refresh this feed:
- **Manual only**: Refresh on demand
- **Daily/Weekly/Monthly**: Automated refresh
- **Cron expression**: Custom schedule

**Note:** Sprint 1 saves preferences; Sprint 2 will activate automation.

### Step 7: Finalize
Click **"Create Feed"** to:
1. Persist schema and profile to database
2. Generate searchable documentation
3. Create vector embeddings for RAG
4. Set up DQ monitoring

---

## Asking Questions

The **Ask Dawn** tab replaces the older Quick Insight workspace. It focuses on retrieval-augmented answers grounded in the context notes you just captured.

### Run a question
1. Switch to **Ask Dawn**.
2. Pick a suggested prompt or type your own question.
3. Click **Send**. Dawn will search Redis, format the context, and produce an answer.
4. Use **Regenerate** to re-run the last prompt after refining notes or recall settings.

### Tips
- Suggestions refresh whenever you index a new workbook — they are derived from the stored summary.
- Adjust `k` from the sidebar to widen or narrow the retrieval window.
- Answers cite the freshest context; refresh the **Context & Memory** tab if you want to inspect the supporting notes.

---

## Working with Datafeeds

Once a workbook is indexed it becomes the active context source for the session.

### Reviewing indexed context
1. Switch to **Context & Memory**.
2. Click **Refresh context** to pull the live notes from Redis.
3. Expand any note to read the captured text, tweak the wording, and save it back.
4. Capture additional nuances with the note form at the bottom of the page.

### Summaries and drift
- The **Upload & Preview** tab keeps the latest profiling summary so you can revisit metrics without re-uploading the file.
- Drift detection for future uploads is surfaced via the FastAPI endpoints (`/feeds` and `/feeds/{identifier}`) and will return to the UI in a later iteration.

### Automation
Job scheduling is still available through the REST API (see `docs/API_REFERENCE.md#/jobs`). The simplified Streamlit app focuses on manual previewing, context management, and retrieval QA.

---

## Creating Transforms

Transforms are **versioned data pipelines** that clean, filter, and reshape feeds.

### Basic Transform Example
```json
{
  "name": "clean_customers",
  "feed_identifier": "customers",
  "description": "Remove test accounts and standardize",
  "steps": [
    {
      "type": "filter",
      "column": "email",
      "op": "contains",
      "value": "@example.com",
      "negate": true
    },
    {
      "type": "rename",
      "mapping": {
        "cust_id": "customer_id",
        "cust_name": "full_name"
      }
    },
    {
      "type": "cast",
      "column": "signup_date",
      "dtype": "datetime"
    }
  ]
}
```

### Available Transform Steps

**1. Rename**
```json
{"type": "rename", "mapping": {"old_name": "new_name"}}
```

**2. Filter**
```json
{
  "type": "filter",
  "column": "status",
  "op": "eq",  // eq, neq, gt, gte, lt, lte, contains
  "value": "active"
}
```

**3. Select/Drop Columns**
```json
{"type": "select", "columns": ["id", "name", "email"]}
{"type": "drop", "columns": ["internal_notes"]}
```

**4. Cast Types**
```json
{"type": "cast", "column": "age", "dtype": "int"}
```

**5. Fill Nulls**
```json
{"type": "fillna", "column": "status", "value": "unknown"}
```

**6. Clean Strings**
```json
{"type": "string_clean", "columns": ["name", "email"], "operations": ["strip", "lower"]}
```

**7. Merge Columns**
```json
{
  "type": "merge_columns",
  "columns": ["first_name", "last_name"],
  "into": "full_name",
  "separator": " "
}
```

**8. Join Feeds**
```json
{
  "type": "join",
  "right_feed": "departments",
  "left_on": ["dept_id"],
  "right_on": ["id"],
  "how": "left"
}
```

### Testing Transforms
Before saving, test with sample data:
1. Provide `sample_rows` in API request
2. Get back `dry_run` results
3. Verify output matches expectations
4. Iterate on steps

### Versioning
Each transform save creates a new version:
- Version 1, 2, 3...
- Full history preserved
- Jobs can target specific versions

---

## Scheduling Jobs

Jobs connect **feeds** → **transforms** → **schedules**.

### Creating a Job

**Via API:**
```python
import requests

job = {
    "name": "Daily Customer ETL",
    "feed_identifier": "customers",
    "feed_version": None,  # null = always use latest
    "transform_name": "clean_customers",
    "schedule": "0 2 * * *",  # 2 AM daily
    "is_active": True
}

response = requests.post("http://127.0.0.1:8000/jobs", json=job)
```

**Via UI (Sprint 2):**
1. Go to feed details
2. Click "Schedule Job"
3. Select transform (optional)
4. Choose schedule preset or custom cron
5. Enable notifications

### Cron Expressions
Format: `minute hour day month weekday`

**Common Patterns:**
- `0 2 * * *` - Every day at 2:00 AM
- `0 */4 * * *` - Every 4 hours
- `0 9 * * 1-5` - Weekdays at 9:00 AM
- `0 0 1 * *` - First day of month at midnight

### Manual Runs
Trigger job immediately (Sprint 2):
```bash
POST /jobs/{job_id}/run
```

### Monitoring Job Runs
Each execution creates a `JobRun` record:
- Start/finish timestamps
- Success/failure status
- Input/output row counts
- Logs and warnings
- DQ validation results

View in UI or query API:
```bash
GET /jobs/{job_id}
```

---

## Natural Language Queries

DAWN converts English questions to SQL using RAG and LLM.

### How It Works
1. You ask: "Show top 10 customers by revenue this year"
2. DAWN:
   - Searches feed manifests for relevant schema
   - Builds SQL context with table/column info
   - Generates SQL using local LLM
   - Validates query (no writes, valid tables)
3. Returns executable SQL

### Query Examples

**Simple Filter:**
```
Question: "Show me active customers"
SQL: SELECT * FROM customers WHERE status = 'active'
```

**Aggregation:**
```
Question: "Count orders by status"
SQL: SELECT status, COUNT(*) as count FROM orders GROUP BY status
```

**Join:**
```
Question: "Show customer names with their order totals"
SQL: SELECT c.name, SUM(o.amount) as total
     FROM customers c
     JOIN orders o ON c.id = o.customer_id
     GROUP BY c.name
```

**Time-based:**
```
Question: "Revenue last 7 days"
SQL: SELECT DATE(order_date) as day, SUM(amount) as revenue
     FROM orders
     WHERE order_date >= CURRENT_DATE - INTERVAL '7 days'
     GROUP BY day
```

### Best Practices
1. **Be specific**: Mention column names when ambiguous
2. **Specify feeds**: "from customers table" if multiple feeds
3. **Review SQL**: Always check generated query before running
4. **Iterate**: Refine question based on results

### Context Awareness
DAWN uses:
- Feed schemas and column types
- Primary/foreign key relationships
- Sample values and distributions
- Previous query patterns

---

## Multi-agent Runs

The `/agents/analyze` endpoint coordinates four cooperative agents—planner, executor, memory curator, and QA—to turn a feed summary into actionable insights.

### Kick off a run
```bash
curl -X POST http://127.0.0.1:8000/agents/analyze \
  -H "Content-Type: application/json" \
  -d '{
        "feed_identifier": "support_tickets",
        "question": "Who resolved the most tickets last month?",
        "refresh_context": true,
        "max_plan_steps": 8
      }'
```

### What you get back
- `plan`: Ordered tasks proposed by the planner agent.
- `completed`: Metric payloads generated by the executor.
- `context_updates`: Summaries written to Redis when `refresh_context` is true.
- `answer`: Optional natural-language answer grounded in the refreshed context.
- `run_log`: Per-agent breadcrumbs so you can audit every step.

Tip: Run the endpoint after each ingestion to refresh the knowledge base and keep the chat agent aligned with the latest metrics.

---

## Tips & Tricks

### Feed Best Practices
- Use consistent naming (snake_case identifiers)
- Document ownership and purpose clearly
- Set up DQ rules early to catch issues
- Review drift reports after each version

### Performance
- Large files (>1M rows): Sample during profiling
- Excel files: Specify sheet name to avoid scanning all
- S3 sources: Use folder patterns for efficiency

### Troubleshooting

**"Feed ingestion failed"**
- Check file format (CSV/Excel only)
- Verify encoding (UTF-8 recommended)
- Look for special characters in headers

**"No SQL generated"**
- Be more specific in question
- Check if feed is indexed (may take 1-2 min)
- Try simpler query first

**"Transform dry run failed"**
- Check column names exist in source feed
- Verify data types match cast operations
- Review filter conditions for typos

### Getting Help
- Check logs in terminal where DAWN is running
- Review API responses for detailed error messages
- See `docs/API_REFERENCE.md` for endpoint details

---

## What's Next?

**Sprint 2 Features (Coming Soon):**
- ✅ Automated job scheduling
- ✅ S3 and Snowflake connectors
- ✅ Row-level vector search
- ✅ Feed export destinations
- ✅ Email/Slack notifications

**Sprint 3 Features (Future):**
- Drift timeline visualization
- Anomaly detection with explanations
- Watch-folder automation
- Self-healing schema adjustments
