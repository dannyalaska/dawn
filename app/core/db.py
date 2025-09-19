from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from .config import settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        dsn = settings.POSTGRES_DSN or "sqlite:///./dawn_dev.sqlite3"
        _engine = create_engine(dsn, pool_pre_ping=True, future=True)
    return _engine
