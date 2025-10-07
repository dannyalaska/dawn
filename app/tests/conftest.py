import pathlib
import sys
from typing import Any

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))


class _FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def get(self, key: str):
        return self._store.get(key)

    def setex(self, key: str, _ttl: int, value: Any):
        self._store[key] = value
        return True

    def set(self, key: str, value: Any):
        self._store[key] = value
        return True


@pytest.fixture(autouse=True)
def isolate_env(tmp_path, monkeypatch):
    # Point DB at temp sqlite, isolate from dev DB
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite:///{tmp_path / 'test.sqlite3'}")

    # Swap redis client with fake
    from app.core import redis_client as rc

    fake = _FakeRedis()
    rc.redis_sync = fake  # type: ignore[attr-defined]

    # Patch modules that imported the client directly
    import app.api.excel as api_excel
    import app.api.rag as api_rag
    import app.core.excel.ingestion as ingestion

    api_excel.redis_sync = fake  # type: ignore[attr-defined]
    api_rag.redis_sync = fake  # type: ignore[attr-defined]
    ingestion.redis_sync = fake  # type: ignore[attr-defined]

    # Re-create tables for this temp DB
    from app.core.db import Base, get_engine

    eng = get_engine()
    Base.metadata.create_all(bind=eng)
    yield
    Base.metadata.drop_all(bind=eng)
