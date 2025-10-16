# DAWN User Guide

## Table of Contents
1. [Getting Started](#getting-started)
2. [Feed Onboarding](#feed-onboarding)
3. [Using Quick Insight](#using-quick-insight)
4. [Working with Datafeeds](#working-with-datafeeds)
5. [Creating Transforms](#creating-transforms)
6. [Scheduling Jobs](#scheduling-jobs)
7. [Natural Language Queries](#natural-language-queries)

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

### Step 1: Select Workspace Mode
1. Open DAWN in your browser
2. Click **"Datafeed Studio"** in the sidebar
3. You'll see the Feed Wizard interface

### Step 2: Upload Your Data
**Option A: File Upload**
1. Click **"Upload files"** or drag-and-drop
2. Supports: CSV, Excel (.xlsx, .xlsm, .xls)
3. Multiple files and ZIP archives supported

**Option B: S3 Source (Coming in Sprint 2)**
1. Select "S3" as source type
2. Enter S3 path: `s3://bucket/path/file.csv`
3. Configure credentials (future)

**Option C: HTTP Source**
1. Select "HTTP" as source type
2. Enter URL to downloadable file
3. DAWN will fetch and process

### Step 3: Configure Feed Metadata
After upload, you'll see a preview:

1. **Feed Identifier**: Unique name (e.g., "customers", "transactions")
   - Use lowercase, underscores for spaces
   - Cannot be changed after creation

2. **Display Name**: Human-readable name (e.g., "Customer Master Data")

3. **Owner**: Team or person responsible

4. **Description**: Purpose and contents (auto-suggested by AI)

### Step 4: Review Schema & Profile
DAWN automatically:
- **Infers schema**: Column names, types, nullability
- **Detects primary keys**: Based on uniqueness
- **Suggests foreign keys**: Links to other feeds
- **Generates metrics**: Row counts, null percentages, value distributions

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

## Using Quick Insight

Quick Insight is for **ad-hoc analysis** without creating formal feeds.

### Upload for Analysis
1. Select **"Quick Insight"** in sidebar
2. Upload CSV/Excel file
3. Ask questions immediately

### Features
- **Instant preview**: See first 100 rows
- **Natural language queries**: "Show me records where amount > 1000"
- **Charts and visualizations**: Auto-generated
- **No persistence**: Data is temporary

### Promote to Feed
If your analysis proves valuable:
1. Click **"Promote this file to Datafeed Studio"**
2. Complete feed metadata
3. Now it's tracked with versioning and DQ

---

## Working with Datafeeds

### Viewing Feeds
1. Go to **Datafeed Studio**
2. See all registered feeds with:
   - Current version
   - Row/column counts
   - Last updated timestamp
   - Drift status
   - Sample rows, value-count cards, and the auto analysis plan
   - Favorite worksheet selector and context note history
   - One-click automation form to schedule refresh jobs

### Understanding Drift
When you upload a new version, DAWN detects:
- **Schema changes**: New/removed/renamed columns
- **Data changes**: Row count deltas, null rate changes
- **Relationship changes**: FK candidate changes

**Drift Statuses:**
- ✅ **No Change**: Identical to previous version
- 📊 **Changed**: Differences detected
- 🆕 **New**: First version

### Querying Feed Data
Click **"Open in Quick Insight"** on any feed to:
1. Jump into Quick Insight with sample rows already staged
2. Reuse the stored summary for suggested questions
3. Ask natural language questions immediately
4. Generate SQL automatically against cached metrics

### Exporting Feeds
(Coming in Sprint 2)
- Export to S3, local file, or SFTP
- Choose format: CSV, Parquet, JSON
- Schedule automated exports

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
