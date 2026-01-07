# Dawn AI Copilot Instructions

## Project Overview
Dawn is a local AI data copilot that ingests Excel workbooks, profiles data with pandas, and provides RAG-based Q&A with deterministic metrics. It uses LangGraph for multi-agent orchestration and supports multiple LLM backends (Ollama, LM Studio, OpenAI, Anthropic, or stub).

## Architecture

### Three-Tier Structure
```
web/          → Next.js 14 frontend (React, Tailwind, Three.js)
app/api/      → FastAPI REST endpoints (routers mount on /rag, /feeds, /agents, etc.)
app/core/     → Business logic, LangGraph graphs, DB models, Redis integration
```

### Key Data Flows
1. **Excel Ingestion**: Upload → `app/core/excel/ingestion.py` (pandas profiling) → `app/core/excel/summary.py` (LLM analysis plan) → Redis vectors + Postgres metadata
2. **RAG Chat**: Question → `app/core/chat_graph.py` (LangGraph StateGraph) → vector search + optional direct metrics → LLM response with citations
3. **Multi-Agent**: `POST /agents/analyze` → `app/core/agent_graph.py` (Planner → Executor → Memory → QA nodes)

### Database Layer
- **Postgres**: Users, Uploads, Feeds, FeedVersions, Jobs, BackendConnections (`app/core/models.py`)
- **Redis**: Vector embeddings via `redis-stack` (RediSearch), context notes, cached previews
- **SQLAlchemy**: Use `session_scope()` context manager from `app/core/db.py` for all DB access

## Development Commands

```bash
# Full lint + type check + tests
make check

# Run tests only
make test
# or: poetry run pytest

# Start API server (dev mode)
make dev-api
# or: poetry run uvicorn app.api.server:app --reload --port 8000

# Start everything (Redis, Postgres, API, Next.js)
./start_dawn.sh
```

## Testing Patterns

Tests live in `app/tests/`. The `conftest.py` auto-fixture:
- Creates an isolated SQLite DB per test
- Swaps Redis with `_FakeRedis` in-memory mock
- Sets `LLM_PROVIDER=stub` to avoid external calls
- Creates a default user via `ensure_default_user()`

When writing tests:
```python
# Use the TestClient pattern for API tests
from fastapi.testclient import TestClient
from app.api.server import app
client = TestClient(app)

# Access isolated DB via session_scope()
from app.core.db import session_scope
with session_scope() as session:
    # queries here
```

## Code Conventions

### LLM Provider Abstraction
All chat models go through `app/core/chat_models.py:get_chat_model(provider)`. Returns a LangChain `BaseChatModel`. The `StubChatModel` echoes context for testing without LLM calls.

### Authentication
- `CurrentUser` dependency in FastAPI routes (`app/core/auth.py`)
- Default user: `local@dawn.internal` (created on startup)
- User isolation: Most queries filter by `user_id`

### Redis Keys
```
dawn:rag:doc:{user_id}:{docid}  → vector documents
dawn:dev:preview:{user_id}:{hash}:{sheet}  → cached Excel previews
```

### API Router Pattern
Each `app/api/*.py` file exports a `router = APIRouter(prefix="/...", tags=[...])` that's mounted in `app/api/server.py`.

## LangGraph Graphs

### chat_graph.py
`StateGraph(ChatState)` with nodes: `retrieve` → `metrics` → conditional → `llm` or `guard`

### agent_graph.py
Multi-agent swarm: `planner` → `executor` → `memory_curator` → `qa` → `reporter`
State flows through `AgentState` TypedDict with `tasks`, `completed`, `warnings`, `run_log`.

## File Naming
- Models: `app/core/models.py` (SQLAlchemy ORM)
- API routes: `app/api/{domain}.py` (FastAPI routers)
- Core logic: `app/core/{domain}.py`
- Tests: `app/tests/test_{domain}.py`

## Environment Variables
Key settings in `.env` (see `app/core/config.py`):
- `LLM_PROVIDER`: stub | ollama | lmstudio | openai | anthropic
- `POSTGRES_DSN`: PostgreSQL connection string
- `REDIS_URL`: Redis connection (needs redis-stack for vectors)
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`: API keys when using cloud LLMs

## Common Gotchas
1. **Redis vectors require redis-stack**: Plain Redis won't support `FT.*` commands; fallback is slow local similarity
2. **Alembic migrations**: Run `poetry run alembic upgrade head` when models change
3. **User isolation**: Always filter queries by `user_id` to respect multi-tenant boundaries
4. **LLM fallback**: If provider init fails, code falls back to `StubChatModel`—check logs for silent failures
