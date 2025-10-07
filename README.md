# DAWN – Data Assistant for Work Notes

DAWN is an **offline-first, Retrieval-Augmented Generation (RAG) assistant** for operations teams. Drop in Excel workbooks, get instant profiling, index them into Redis for semantic search, then have a local LLM walk you through the insights—no cloud required.

---

## ✨ What’s inside

- **FastAPI backend**
  - `/ingest/preview` – Excel preview + profiling (shapes, column stats, cached snapshots)
  - `/rag/index_excel` – converts worksheets into hybrid summary + row chunks and stores them in Redis
  - `/rag/query` & `/rag/answer` – classic RAG endpoints
  - `/rag/chat` – conversation-aware answers; citations and context come back each turn
- **Streamlit frontend**
  - Upload previews, auto-index, view dataset summaries & key metrics
  - “Quick question” shortcuts generated from the data
  - Conversational chat UI with expandable source citations
- **Local LLM support**
  - Works with LM Studio (OpenAI-compatible `/v1/chat/completions`)
  - Ollama fallback still available
- **Persistence**
  - Redis FT with sentence-transformer embeddings
  - Postgres stores upload metadata + JSON summaries
  - Alembic migrations (`infra/alembic`)
- **Tested workflow**
  - 13 pytest suites (~82 % coverage) covering ingest, RAG, chat, and helpers
  - Ruff, Black, Mypy via pre-commit

---

## 🚀 Quickstart

### Prerequisites

- Python 3.11
- Poetry ≥ 2
- Redis with RediSearch (redis-stack works)
- Postgres 13+
- Optional: LM Studio (or Ollama)

### 1. Clone & install

```bash
git clone https://github.com/dannyalaska/dawn.git
cd dawn

poetry install --no-interaction --no-ansi
```

> CI runs Poetry in dependency-only mode (`package-mode = false`), so installation is fast even though we’re not building a wheel.

### 2. Configure environment

```bash
cp .env.example .env
```

Update the essentials:

```dotenv
POSTGRES_DSN=postgresql+psycopg2://dawn:password@localhost:5432/dawn
REDIS_URL=redis://localhost:6379/1

# For LM Studio
LLM_PROVIDER=lmstudio
OPENAI_BASE_URL=http://127.0.0.1:1234
OPENAI_MODEL=mistral-7b-instruct-v0.3
OPENAI_API_KEY=lm-studio
```

`start_dawn.sh` autodetects Homebrew services and runs Alembic migrations for you.

### 3. Launch everything

```bash
./start_dawn.sh
```

- FastAPI: `http://127.0.0.1:8000`
- Streamlit: `http://127.0.0.1:8501`

---

## 🧪 Development

Run the full suite:

```bash
poetry run pytest app/tests
```

Format/lint manually if needed:

```bash
poetry run ruff check --fix
poetry run ruff format
poetry run black .
poetry run mypy
```

Pre-commit is wired into `.git/hooks`, but you can run it explicitly:

```bash
poetry run pre-commit run --all-files
```

---

## 🗺️ Roadmap

### v1.0 – Local Analyst (current)

- ✅ Excel ingestion, profiling, caching
- ✅ Redis RAG with dataset summaries & LM Studio chat
- ✅ Full-stack tests and start script polish

### v1.1 – Assisted Editing *(up next)*

- Natural-language commands that safely modify worksheets (`Preview → Approve → Patch`)

### v1.2 – SQL Agent

- Connect to Postgres / SQLite sources, generate SQL queries, render results inline

### v1.3 – Memory

- Persisted chat history across sessions, multi-file context management

### v1.4 – Automation

- Scheduled workbook ingestion, recurring summaries, alerting hooks

### v2.0 – Packaging & SaaS

- PyInstaller desktop bundle
- Optional managed SaaS with team workspaces and shared Redis/Postgres

---

## 🤝 Contributing

1. Fork & clone the repo.
2. Run `poetry install`.
3. Work in feature branches; keep tests green.
4. Submit a PR—CI will verify formatting, typing, and tests.

---

## 📄 License

MIT © Danny McGrory

---

> "DAWN is an offline ChatGPT for spreadsheets—fast, private, and obsessed with bringing Ops teams clarity." Enjoy! ✨
