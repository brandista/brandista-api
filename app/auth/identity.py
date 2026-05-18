"""Canonical identity lookup helpers."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, UserEmailAlias


async def resolve_user_by_email(session: AsyncSession, email: str) -> User | None:
    """Resolve a primary or alias email to the canonical user row."""
    normalized = email.strip().lower()
    if not normalized:
        return None

    primary = (
        await session.execute(select(User).where(User.email == normalized))
    ).scalar_one_or_none()
    if primary is not None:
        return primary

    return (
        await session.execute(
            select(User)
            .join(UserEmailAlias, UserEmailAlias.user_id == User.id)
            .where(UserEmailAlias.email == normalized)
        )
    ).scalar_one_or_none()
