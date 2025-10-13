from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

if TYPE_CHECKING:
    from . import models as _models  # noqa: F401


class Base(DeclarativeBase):
    """Typed SQLAlchemy declarative base."""


_engine: Engine | None = None
_engine_dsn: str | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _resolve_dsn() -> str:
    env_dsn = os.getenv("POSTGRES_DSN")
    if env_dsn:
        return env_dsn
    if settings.POSTGRES_DSN:
        return settings.POSTGRES_DSN
    return "sqlite:///./dawn_dev.sqlite3"


def get_engine():
    global _engine, _engine_dsn, _SessionLocal
    dsn = _resolve_dsn()
    if _engine is None or dsn != _engine_dsn:
        _engine = create_engine(dsn, pool_pre_ping=True, future=True)
        _engine_dsn = dsn
        _SessionLocal = None  # reset session maker when engine changes
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(), autoflush=False, autocommit=False, future=True
        )
    return _SessionLocal


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_database() -> None:
    """Ensure core tables exist before serving requests."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
