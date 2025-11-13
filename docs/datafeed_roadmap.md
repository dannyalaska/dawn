# DAWN Datafeed Platform — Architecture & Roadmap

## High-Level Architecture

```mermaid
graph LR
    subgraph UI
        ST[Streamlit App<br/>Workspace / Datafeed Mode]
    end

    subgraph API Layer
        FEEDS[/FastAPI `/feeds`/]
        TRANSFORMS[/FastAPI `/transforms`/]
        JOBS[/FastAPI `/jobs`/]
        NLSQL[/FastAPI `/nl/sql`/]
        RAGAPI[/FastAPI `/rag`/]
        AGENTS[/FastAPI `/agents/analyze`/]
    end

    subgraph Orchestration
        RUNNER[Run Coordinator<br/>Jobs + Schedules]
        DQ[DQ Engine<br/>Auto + Manual Rules]
        SWARM[LangGraph Agent Swarm<br/>Planner · Executor · Memory · QA]
    end

    subgraph Storage
        PG[(Postgres<br/>feeds, versions, jobs, dq)]
        REDIS[(Redis / RediSearch<br/>vectors, manifests, cache)]
        OBJ[(File Store<br/>Uploads, manifests, exports)]
    end

    subgraph Compute
        PROFILE[Pandas / DuckDB / Polars<br/>Profiling & Canonicalisation]
        LLM[Local LLM<br/>Schema summaries, NL-SQL]
        EMBED[sentence-transformers<br/>Row embeddings]
    end

    ST --> FEEDS
    ST --> TRANSFORMS
    ST --> JOBS
    ST --> NLSQL
    ST --> RAGAPI
    ST --> AGENTS

    FEEDS --> PROFILE
    PROFILE --> PG
    PROFILE --> REDIS
    PROFILE --> OBJ
    PROFILE --> DQ

    FEEDS --> LLM
    FEEDS --> EMBED
    EMBED --> REDIS

    DQ --> PG
    RUNNER --> PG
    RUNNER --> PROFILE
    RUNNER --> DQ
    RUNNER --> REDIS
    SWARM --> PG
    SWARM --> REDIS
    AGENTS --> SWARM

    TRANSFORMS --> PROFILE
    TRANSFORMS --> PG

    NLSQL --> REDIS
    NLSQL --> LLM
    RAGAPI --> SWARM
```

## Feed Onboarding Flow

```mermaid
sequenceDiagram
    participant U as User (Streamlit)
    participant UI as Datafeed Wizard
    participant API as FastAPI `/feeds/ingest`
    participant PROF as Profiling Engine
    participant DQ as DQ Rule Builder
    participant DOC as Docs & Embeddings
    participant SWARM as Agent Swarm
    participant DB as Postgres / Redis

    U->>UI: Select source + upload / link
    UI->>API: POST ingest (manifest params)
    API->>PROF: Load file(s), infer schema
    PROF->>DQ: Generate auto rules & drift metrics
    PROF->>DOC: Build markdown + ER (Mermaid)
    DOC->>DB: Persist schema, manifest, vectors
    DQ->>DB: Save dq_rules, dq_results stub
    API-->>UI: Return version summary, docs, metrics
    UI-->>U: Show progress → summary cards → next steps
    UI->>JOBS: (Optional) create schedule + job record
    UI->>SWARM: (Optional) trigger /agents/analyze for insights
    SWARM->>DB: Persist metric summaries + memory updates
```

## Run Lifecycle & Drift Intelligence

```mermaid
flowchart LR
    START((Feed Version N))
    DRIFT[Compare schema & metrics<br/>vs Version N-1]
    DQCHECK[Execute DQ rules<br/>auto + manual]
    EMBEDNew[Embed new/changed rows]
    REPORT[Generate change report<br/>Markdown + ER update]
    JOB[(Job History)]
    REDIS[(Redis Context)]
    PG[(Postgres)]

    START --> DRIFT --> DQCHECK --> REPORT
    REPORT --> PG
    REPORT --> JOB
    REPORT -->|Store timeline, manifest| REDIS
    DQCHECK --> PG
    EMBEDNew --> REDIS
    JOB --> NLQ{NL-to-SQL · Agent Swarm · Chat}
    NLQ -->|Use schema + drift summary| REDIS
```

## Roadmap by Sprint

### Sprint 1 — Schema & Validation Foundations
- [x] Simplified upload & preview workspace with manifest summary and indexing hand-off.
- [x] Profiling engine upgrades for schema inference & drift metrics.
- [x] Auto DQ rule framework (PK uniqueness, null thresholds, datetime checks).
- [x] Change summaries between versions (rows, columns, null deltas).
- [x] Persist manifest, ER diagram, and profiling stats in Redis/Postgres.

### Sprint 2 — Connectors, Scheduling & NL Querying
- [x] Row embeddings + Redis vector index per feed.
- [x] NL-to-SQL enhancements with context-aware question suggestions.
- [x] Iterate on the tabbed Streamlit experience (Upload & Preview, Context & Memory, **Agent Swarm**, Ask Dawn).
- [x] Expose multi-agent `/agents/analyze` endpoint for automated plan execution.
- [ ] Source connectors (S3, shared folder watch, Snowflake).
- [ ] Credential management + connection tests.
- [ ] Job scheduling UI (cron presets, manual runs, notifications).
- [ ] Unified data access layer (feeds + ad-hoc uploads) powering both workspaces.
- [ ] Feed export planner with manifest-driven targets (S3 + local outbox initial).
- [ ] Export configuration UI (target selection, format, schedule, notifications).
- [ ] Integrate exports into job runs with logging/alerting.

### Sprint 3 — Automation & Intelligence
- Drift timeline view & daily report cards.
- LLM “Explain this feed” + anomaly summaries.
- Watch-folder automation + manifest export/import.
- Notifications (email/Slack) for success/fail + drift anomalies.
- Optional synthetic data generator & feed templates.

### Stretch Goals
- Self-healing schema adjustments, smart merge across feeds.
- DAWN Agent for automated DQ fixes & transformation suggestions.
- Natural language SQL editor with live preview + execution sandbox.

## Sprint 1 Backlog Snapshot
- [x] Design streamlined upload→index flow with clear copy.
- [x] Upgrade profiling pipeline to capture schema drift & change metrics.
- [x] Auto-generate manifests and expose for download/edit.
- [x] Persist & display detailed summary cards (schema, PK/FK, drift, DQ).
- [x] Build DQ rule engine (auto rule persistence + evaluation hook).
- [ ] Update documentation & UX walkthrough for onboarding flow.

## Sprint 2 — In Progress

### Week 1: Scheduler & Documentation
- [ ] Polish API and user documentation
- [ ] Implement job scheduler with background worker (APScheduler)
- [ ] Add manual job trigger endpoints
- [ ] Test scheduled execution end-to-end
- [ ] Extend indexing UI with schedule configuration hooks
- [x] Document Agent Swarm workflow & monitoring in README/User Guide
