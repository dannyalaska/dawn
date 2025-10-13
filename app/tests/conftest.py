import fnmatch
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

    def hset(self, key: str, mapping: dict[str, Any]):
        current = self._store.setdefault(key, {})
        if not isinstance(current, dict):
            current = {}
            self._store[key] = current
        for field, value in mapping.items():
            current[field] = value
        return True

    def hgetall(self, key: str) -> dict[str, Any]:
        stored = self._store.get(key)
        if isinstance(stored, dict):
            return dict(stored)
        return {}

    def hmget(self, key: str, *fields):
        stored = self._store.get(key)
        if not isinstance(stored, dict):
            return [None for _ in fields]
        return [stored.get(field) for field in fields]

    def delete(self, *keys: str):
        removed = 0
        for key in keys:
            if key in self._store:
                del self._store[key]
                removed += 1
        return removed

    def scan_iter(self, match: str | None = None):
        pattern = match or "*"
        for key in list(self._store.keys()):
            if fnmatch.fnmatch(key, pattern):
                yield key

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, client: _FakeRedis) -> None:
        self._client = client
        self._ops: list[tuple[str, str, dict[str, Any]]] = []

    def hset(self, key: str, mapping: dict[str, Any]):
        self._ops.append(("hset", key, mapping))
        return self

    def execute(self):
        for op, key, mapping in self._ops:
            if op == "hset":
                self._client.hset(key, mapping=mapping)
        self._ops.clear()
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
    import app.core.feed_ingest as feed_ingest
    import app.core.nl2sql as nl2sql
    import app.core.rag as rag_module

    api_excel.redis_sync = fake  # type: ignore[attr-defined]
    api_rag.redis_sync = fake  # type: ignore[attr-defined]
    ingestion.redis_sync = fake  # type: ignore[attr-defined]
    rag_module.redis_sync = fake  # type: ignore[attr-defined]
    feed_ingest.redis_sync = fake  # type: ignore[attr-defined]
    nl2sql.redis_sync = fake  # type: ignore[attr-defined]

    # Re-create tables for this temp DB
    from app.core.db import Base, get_engine

    eng = get_engine()
    Base.metadata.create_all(bind=eng)
    yield
    Base.metadata.drop_all(bind=eng)
