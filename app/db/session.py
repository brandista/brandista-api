"""Async SQLAlchemy session for canonical platform identity tables.

This is the SQLAlchemy-native session used by all canonical-identity code
(auth/v2 endpoints, platform user/org lookups, fact API). It coexists with
the legacy psycopg2 pool in `database.py` — the two never share connections
or transactions. Anything that touches `users`/`organizations`/`credits`/
`entitlements` goes through this session; anything that touches `analyses`/
`competitor_*` continues to use the psycopg2 helpers.
"""
from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _async_dsn() -> str:
    """Return DATABASE_URL coerced to `postgresql+asyncpg://...`.

    Railway provides `DATABASE_URL=postgres://...` or `postgresql://...`;
    asyncpg requires the explicit `+asyncpg` driver tag. We don't mutate
    the env var itself — only the value used by this engine.
    """
    raw = os.getenv("DATABASE_URL", "")
    if not raw:
        raise RuntimeError(
            "DATABASE_URL is not set — canonical platform tables cannot be "
            "reached. Set DATABASE_URL in Railway env."
        )
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://") :]
    if raw.startswith("postgresql://") and "+asyncpg" not in raw:
        raw = raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    return raw


_engine = None
_session_maker = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(_async_dsn(), pool_pre_ping=True)
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    global _session_maker
    if _session_maker is None:
        _session_maker = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_maker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for canonical-platform DB sessions."""
    async with get_session_maker()() as session:
        yield session
