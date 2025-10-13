# Dawn — Local AI Data Copilot

Dawn ingests Excel workbooks, understands their schema, proposes an analysis plan, runs deterministic metrics, and then layers semantic search + LLM reasoning on top. Everything is local: profile with pandas, store knowledge in Redis/Postgres, and choose your own LLM (Ollama, LM Studio, OpenAI).

---

## What makes Dawn unique

### 1. Agentic ingestion
1. Upload a workbook (sheet picker included).
2. Pandas profiles every column and builds categorical counts, numeric stats, and time-based aggregates.
3. A local LLM reviews that profile and recommends an analysis plan (e.g., “count tickets by Assigned_To”, “average Resolution_Time_Hours by Assigned_To”).
4. Dawn executes the plan, stores precise metrics in Postgres/Redis, and generates semantic chunks for citations.

### 2. Editable memory layer
- **Context tab** shows Redis chunks, column roles, and the analysis plan. You can filter, edit, or add notes (“Resolution_Time_Hours is business hours”).
- Saves go straight to `/rag/memory`, so the next ingestion run respects your overrides.
- Cached metrics live alongside embeddings: you can delete, refresh, or augment them without re-uploading the file.

### 3. Deterministic answers + semantic context
- Questions like “Who resolved the most tickets?” now pull from cached metrics first (“Alex handled 143 tickets. Next: Priya 138.”).
- If a metric doesn’t exist, Dawn falls back to semantic chunks and the LLM with citations.
- Chat responses combine the verified numbers with contextual snippets for explainability.

---

## Architecture

| Layer | Responsibility |
| --- | --- |
| **Streamlit** | Upload + sheet picker, dataset overview, expandable column & aggregate panels, context editor, chat workspace. |
| **FastAPI** | `/ingest/preview`, `/rag/index_excel`, `/rag/context`, `/rag/memory`, `/rag/chat`, etc. |
| **pandas** | Profiling, counts, numeric stats, aggregation execution. |
| **LLM** | Generates analysis plan + assists with narrative answers when metrics aren’t enough. |
| **Redis** | Vector store for chunks, JSON hashes for plan/relationships/notes. |
| **Postgres** | Durable storage for uploads and summary JSON (metrics, plan, relationships). |

---

## Quickstart

### Prerequisites
- Python 3.11
- Poetry ≥ 2
- Redis (redis-stack with RediSearch)
- Postgres 13+
- Optional: LM Studio or Ollama

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

## Development commands

```bash
poetry run ruff check
poetry run mypy app
poetry run pytest
```

Pre-commit is configured (`poetry run pre-commit run --all-files`).

---

## Roadmap snapshots
- **Campus (now)** – Excel intelligence with editable memory, deterministic answers, and semantic context.
- **Next** – Assisted workbook editing (approve patches), SQL ingestion, multi-workbook memory, and scheduled runs.

---

## Contributing

1. Fork & clone the repo.
2. `poetry install`
3. Create a branch, keep tests green.
4. Submit a PR; CI runs lint, type, and pytest.

---

## License

MIT © Danny McGrory — fast, private, and obsessed with bringing ops teams clarity. Enjoy! ✨
