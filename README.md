# Dawn — Local AI Data Copilot

Dawn ingests Excel workbooks, understands their schema, proposes an analysis plan, runs deterministic metrics, and then layers semantic search + LLM reasoning on top. Everything is local: profile with pandas, store knowledge in Redis/Postgres, and choose your own LLM (Ollama, LM Studio, OpenAI).

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

---

## Architecture

| Layer | Responsibility |
| --- | --- |
| **Streamlit** | Three-tab workspace (Upload & Preview, Context & Memory, Ask Dawn) for profiling Excel files, curating context, and asking questions. |
| **FastAPI** | `/ingest/preview`, `/rag/index_excel`, `/rag/context`, `/rag/memory`, `/rag/chat`, `/jobs`, etc. |
| **pandas** | Profiling, counts, numeric stats, aggregation execution. |
| **APScheduler** | Background job scheduling and execution for automated data processing. |
| **LLM** | Generates analysis plan + assists with narrative answers when metrics aren't enough. |
| **Redis** | Vector store for context notes plus JSON hashes for plan/relationships/notes. |
| **Postgres** | Durable storage for uploads, jobs, and summary JSON (metrics, plan, relationships). |

---

## Quickstart

### Prerequisites
- Python 3.11
- Poetry ≥ 2
- Redis (redis-stack with RediSearch)
- Postgres 13+
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
- Streamlit → `http://127.0.0.1:8501`

Open the Streamlit app and you’ll land on a simplified workspace:
- **Upload & Preview** – profile an Excel workbook and review sample rows.
- **Context & Memory** – inspect the captured context notes and add your own guidance.
- **Ask Dawn** – run retrieval-augmented questions with instant suggestions.

### Sample data
- `demo_assets/support_copilot_demo.xlsx` — synthetic support tickets with agents + KPIs.
- `demo_assets/support_transform.json` — example transform definition + sample rows.

Feel free to delete these files if you do not want demo content in your fork. They never contain real customer or company data.

## Development commands

```bash
poetry run ruff check
poetry run mypy app
poetry run pytest
```

Pre-commit is configured (`poetry run pre-commit run --all-files`).

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
