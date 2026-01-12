# Dawn — Local AI Data Copilot

Dawn ingests Excel workbooks, understands their schema, proposes an analysis plan, runs deterministic metrics, and then layers semantic search + LLM reasoning on top. Everything is local: profile with pandas, store knowledge in Redis/Postgres, and choose your own LLM (Ollama, LM Studio, OpenAI).

---

## Demo

<video controls width="100%">
  <source src="docs/DAWN_Demo_GitHub.mp4" type="video/mp4">
</video>

[Watch the demo video](docs/DAWN_Demo_GitHub.mp4)

---

## What makes Dawn unique

### 1. Agentic ingestion
1. Upload a workbook (sheet picker included).
2. Pandas profiles every column and builds categorical counts, numeric stats, and time-based aggregates.
3. A local LLM reviews that profile and recommends an analysis plan (e.g., “count tickets by Assigned_To”, “average Resolution_Time_Hours by Assigned_To”).
4. Dawn executes the plan, stores precise metrics in Postgres/Redis, and generates semantic context notes for citations.

### 2. Editable memory layer
- **Context tab** shows Redis-backed context notes, column roles, and the analysis plan. You can filter, edit, or add annotations (“Resolution_Time_Hours is business hours”).
- Saves go straight to `/rag/memory`, so the next ingestion run respects your overrides.
- Cached metrics live alongside embeddings: you can delete, refresh, or augment them without re-uploading the file.

### 3. Deterministic answers + semantic context
- Questions like “Who resolved the most tickets?” now pull from cached metrics first (“Alex handled 143 tickets. Next: Priya 138.”).
- If a metric doesn’t exist, Dawn falls back to those context notes and the LLM with citations.
- Chat responses combine the verified numbers with contextual snippets for explainability.

### 4. Multi-agent orchestrator
- A LangGraph-powered swarm coordinates planning, metric execution, memory curation, and QA.
- Trigger the workflow via `POST /agents/analyze` to refresh context, surface insights, and answer follow-ups cooperatively.
- Every agent logs its actions so you can audit the plan, execution steps, and guardrail warnings in one payload.

---

## Architecture

| Layer | Responsibility |
| --- | --- |
| **Next.js** | Dawn Horizon workspace for profiling Excel files, curating context, managing agents, and asking questions. |
| **FastAPI** | `/ingest/preview`, `/rag/index_excel`, `/rag/context`, `/rag/memory`, `/rag/chat`, `/jobs`, etc. |
| **pandas** | Profiling, counts, numeric stats, aggregation execution. |
| **APScheduler** | Background job scheduling and execution for automated data processing. |
| **LLM / LangChain** | LangGraph orchestrates retrieval-augmented chat and NL2SQL prompts across OpenAI, LM Studio, Ollama, or Anthropic with citation guardrails. |
| **Auth & Settings** | Local user accounts with per-user storage plus backend connector management (MySQL/Postgres/S3). |
| **Redis** | Vector store for context notes (LangChain Redis adapter) plus JSON hashes for plan/relationships/notes. |
| **Postgres** | Durable storage for uploads, jobs, and summary JSON (metrics, plan, relationships). |

### System Diagram

```mermaid
flowchart TD
    subgraph UI
        NEXT[Next.js App\nUpload · Context · Agent Swarm · Ask]
    end

    subgraph API["FastAPI Service"]
        FEEDS[/feeds · /ingest/preview/]
        RAG[/rag/*]
        AGENTS[/agents/analyze]
        JOBS[/jobs/*]
        NLSQL[/nl/sql]
    end

    subgraph Engine
        INGEST[Ingestion & Profiling\npandas · dq rules]
        CHAT[LangGraph Chat Graph\nRAG + Guardrails]
        SWARM[LangGraph Agent Swarm\nPlanner · Executor · Memory · QA]
        SCHED[APScheduler\nBackground Jobs]
    end

    subgraph Storage
        PG[(Postgres\nFeeds · Versions · Jobs)]
        RD[(Redis\nVectors · Memory · Plans)]
        FS[(File Storage / S3 Uploads)]
    end

    subgraph LLMs["LLM Providers"]
        OLLAMA[Ollama]
        LMSTUDIO[LM Studio]
        OPENAI[OpenAI]
        ANTHROPIC[Anthropic]
        STUB[Stub]
    end

    NEXT -->|REST| FEEDS
    NEXT -->|REST| RAG
    NEXT -->|REST| AGENTS
    NEXT -->|REST| NLSQL
    NEXT -->|REST| JOBS

    FEEDS --> INGEST
    RAG --> CHAT
    AGENTS --> SWARM
    NLSQL --> CHAT
    JOBS --> SCHED

    INGEST --> PG
    INGEST --> RD
    INGEST --> FS

    CHAT --> RD
    SWARM --> RD
    SWARM --> PG

    CHAT -->|tool calls| OLLAMA
    CHAT --> OPENAI
    CHAT --> LMSTUDIO
    CHAT --> ANTHROPIC
    CHAT --> STUB
    SWARM --> OLLAMA
    SWARM --> OPENAI
    SWARM --> LMSTUDIO
    SWARM --> ANTHROPIC
    SWARM --> STUB

    SCHED --> FEEDS
```

---

## Quickstart

### Prerequisites
- Python 3.11
- Poetry ≥ 2
- Redis (redis-stack with RediSearch)
- Postgres 13+
- Node.js 18.18+
- Optional: LM Studio or Ollama

### Start dependencies
The repo ships with a local docker-compose stack:

```bash
docker compose -f infra/docker-compose.dev.yml up -d
```

This brings up Redis + Postgres with development credentials that should never be used in production. Point your `.env` at whichever Redis/Postgres instance you prefer; SQLite artifacts are intentionally excluded from version control.

### Install
```bash
git clone https://github.com/dannyalaska/dawn.git
cd dawn
poetry install --no-interaction --no-ansi
```

### Configure
```bash
cp .env.example .env
# edit Postgres, Redis, and LLM settings to match your machine
```

### Run
```bash
./start_dawn.sh
```
- API → `http://127.0.0.1:8000`
- Next.js UI → `http://127.0.0.1:3000` (override with `DAWN_NEXT_PORT`)

The startup script launches the cinematic **Dawn Horizon** Next.js workspace. It keeps the FastAPI
process running, ensures the `web/` dependencies are installed, and boots `npm run dev` so you get hot reload,
Three.js telemetry, animated agent cards, and the upload/auth widgets.

### Working on the Next.js UI

`web/` contains the experience built with Next 14, Tailwind, SWR, and `@react-three/fiber`. It requires Node.js 18.18+.

```bash
cd web
npm install
npm run dev   # http://localhost:3000
```

Env hints:

- `NEXT_PUBLIC_DAWN_API` — URL for the FastAPI backend (defaults to `http://127.0.0.1:8000`)
- `DAWN_NEXT_PORT=4000` — change the Next dev server port

Key features:
- **Upload & Preview** – profile an Excel workbook and review sample rows.
- **Context & Memory** – inspect the captured context notes and add your own guidance.
- **Ask Dawn** – run retrieval-augmented questions with instant suggestions.
- **Backend Settings** – configure Postgres, Snowflake, MySQL, or S3 connectors per account and lock agents to explicit schema grants.
- **Materialized Tables** – every upload becomes a local SQL table so agents and NL2SQL can query the full dataset later.
- **Auto-Seeded Postgres** – if your `.env` supplies `POSTGRES_DSN` (or `BACKEND_AUTO_CONNECTIONS`), Dawn automatically registers that database as a backend connection for the default user so agents can query it immediately.

Authentication is local-first: the app boots with a default account (`local@dawn.internal`). Use the **Account** panel to register new users, sign in, or manage tokens—each user keeps an isolated Redis/Postgres namespace.

## Development commands

```bash
poetry run ruff check
poetry run mypy app
poetry run pytest
python -m app.cli runner stats
```

Pre-commit is configured (`poetry run pre-commit run --all-files`).

### Docker

Build the app container:

```bash
docker build -t dawn .
```

Then run it, pointing Dawn at your own Postgres/Redis via `.env` (or explicit env vars):

```bash
docker run --env-file .env -p 8000:8000 -p 3000:3000 dawn
```

The entrypoint runs migrations and starts both FastAPI (`:8000`) and Next.js (`:3000`). Provide database/redis credentials via environment so the container can reuse your existing infrastructure.

---

## Security & privacy
- `.env` and any other credential files are ignored by git. Copy from `.env.example` and keep secrets out of commits.
- Local SQLite databases (`*.sqlite3`, `*.db`) are ignored to prevent leaking run history. Run `poetry run alembic upgrade head` against your configured Postgres instance instead.
- Configure LLM access keys via environment variables at runtime (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.). They are never baked into source.
- Sample data and docs contain only synthetic names and values so you can share the repo publicly.

---

## Roadmap snapshots
- **Campus (now)** – Excel intelligence with editable memory, deterministic answers, semantic context, and automated job scheduling.
- **Next** – Assisted workbook editing (approve patches), SQL ingestion, and multi-workbook memory.

---





## Contributing

1. Fork & clone the repo.
2. `poetry install`
3. Create a branch, keep tests green.
4. Submit a PR; CI runs lint, type, and pytest.

---

## License

MIT © Danny McGrory — fast, private, and obsessed with bringing ops teams clarity. Enjoy! ✨
