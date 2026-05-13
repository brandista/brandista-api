"""Alembic environment for brandista-api-git canonical platform schema.

This env.py reads `DATABASE_URL` from the runtime environment (Railway,
local docker-compose, dotenv) and points `target_metadata` at
`app.db.base.Base.metadata` so autogenerate sees the canonical models
defined in `app.db.models`.

Legacy tables (`analyses`, `competitor_*`, `user_analysis_usage`) are NOT
in the canonical metadata, so autogenerate will not try to drop or alter
them. They continue to be managed by the boot-time auto-migration code in
`database.py` until they too are migrated into alembic.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the project root importable so `from app.db.base import Base` resolves
# when alembic is invoked from any CWD.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.db.base import Base  # noqa: E402
from app.db import models  # noqa: F401,E402  — registers all models on Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _sync_dsn() -> str:
    """Return DATABASE_URL coerced to a sync psycopg2 DSN.

    Alembic itself runs migrations synchronously. We accept the same env
    var as the rest of the app (which prefers asyncpg) and rewrite it to
    a plain `postgresql://` DSN for the migration runner.
    """
    raw = os.getenv("DATABASE_URL", "")
    if not raw:
        raise RuntimeError(
            "DATABASE_URL is not set — alembic cannot connect. Set it in "
            "Railway env or your local shell before running migrations."
        )
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://") :]
    # strip any async driver suffix
    raw = raw.replace("postgresql+asyncpg://", "postgresql://", 1)
    return raw


# Inject the runtime DSN so alembic.ini doesn't need to hardcode it.
config.set_main_option("sqlalchemy.url", _sync_dsn())

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Compare types so a later String(255) → Text change shows up in
        # autogenerate. Useful as the schema evolves.
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
