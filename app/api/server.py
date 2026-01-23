from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.agents import router as agents_router
from app.api.auth import router as auth_router
from app.api.backends import router as backends_router
from app.api.demo import router as demo_router
from app.api.excel import router as excel_router
from app.api.feeds import router as feeds_router
from app.api.jobs import router as jobs_router
from app.api.lmstudio import router as lmstudio_router
from app.api.nl_sql import router as nl_router
from app.api.rag import router as rag_router
from app.api.transforms import router as transforms_router
from app.core.auth import ensure_default_user
from app.core.backend_seed import seed_backend_connections
from app.core.config import settings
from app.core.db import get_engine, init_database, session_scope
from app.core.rag import _ensure_index  # type: ignore[attr-defined]
from app.core.redis_client import redis_async, redis_sync
from app.core.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan handler that wires up shared infrastructure."""
    _require_dependencies()
    init_database()
    default_user = ensure_default_user()
    seed_backend_connections(default_user.id)
    with suppress(Exception):
        _ensure_index(redis_sync, 384)
    try:
        start_scheduler()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to start scheduler: %s", exc, exc_info=True)
    try:
        yield
    finally:
        try:
            stop_scheduler()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error stopping scheduler: %s", exc, exc_info=True)


app = FastAPI(title="DAWN API", lifespan=_lifespan)

# Dev CORS (tighten in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _check_redis() -> bool:
    try:
        pong = await redis_async.ping()
        return bool(pong)
    except Exception:
        return False


def _check_db() -> bool:
    try:
        with session_scope() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _check_llm() -> dict[str, Any]:
    provider = settings.LLM_PROVIDER.lower()
    detail: str | None = None
    ok = True
    endpoint = ""

    if provider == "stub":
        ok = True
        detail = "Stub responses active."
    elif provider == "ollama":
        endpoint = "http://127.0.0.1:11434/api/tags"
    elif provider == "lmstudio":
        base = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:1234").rstrip("/")
        endpoint = f"{base}/models"
    elif provider == "openai":
        endpoint = "https://api.openai.com/v1/models"
    elif provider == "anthropic":
        endpoint = "https://api.anthropic.com/v1/models"

    if endpoint:
        try:
            headers = {}
            if provider == "openai":
                headers["Authorization"] = f"Bearer {os.getenv('OPENAI_API_KEY', '')}"
            if provider == "anthropic":
                headers["x-api-key"] = os.getenv("ANTHROPIC_API_KEY", "")
            resp = requests.get(endpoint, timeout=2, headers=headers or None)
            resp.raise_for_status()
            detail = "Endpoint reachable"
            ok = True
        except Exception as exc:  # noqa: BLE001
            ok = False
            detail = str(exc)

    return {"provider": provider or "stub", "ok": ok, "detail": detail}


def _require_dependencies() -> None:
    errors: list[str] = []
    if settings.REQUIRE_REDIS:
        try:
            redis_sync.ping()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Redis unavailable: {exc}")

    if settings.REQUIRE_POSTGRES:
        dsn = os.getenv("POSTGRES_DSN") or settings.POSTGRES_DSN
        if not dsn:
            errors.append("POSTGRES_DSN is required when REQUIRE_POSTGRES=true.")
        else:
            engine = get_engine()
            if engine.dialect.name != "postgresql":
                errors.append("POSTGRES_DSN must point to a Postgres database.")
            else:
                try:
                    with engine.connect() as conn:
                        conn.execute(text("SELECT 1"))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"Postgres unavailable: {exc}")

    if errors:
        raise RuntimeError("Startup dependency check failed: " + "; ".join(errors))


@app.get("/health")
async def health():
    redis_ok = await _check_redis()
    db_ok = _check_db()
    llm_status = _check_llm()
    return {
        "ok": redis_ok and db_ok and bool(llm_status.get("ok", True)),
        "service": "api",
        "env": settings.ENV,
        "redis": redis_ok,
        "db": db_ok,
        "llm": llm_status,
    }


@app.get("/version")
def version():
    return {"name": settings.APP_NAME, "env": settings.ENV}


@app.get("/health/redis")
async def health_redis():
    return {"ok": await _check_redis()}


@app.get("/health/db")
def health_db():
    status = _check_db()
    return {"ok": status}


@app.get("/health/llm")
def health_llm():
    return _check_llm()


app.include_router(excel_router)
app.include_router(auth_router)
app.include_router(backends_router)
app.include_router(demo_router)
app.include_router(feeds_router)
app.include_router(rag_router)
app.include_router(transforms_router)
app.include_router(nl_router)
app.include_router(jobs_router)
app.include_router(agents_router)
app.include_router(lmstudio_router)
