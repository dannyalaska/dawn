from __future__ import annotations
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

import os, sys, pathlib

# Add repo root to path so imports work when running from infra/alembic
sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))

from app.core.db import Base
from app.core.models import *  # noqa: F401,F403

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    dsn = os.getenv("POSTGRES_DSN") or "sqlite:///./dawn_dev.sqlite3"
    return dsn


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
