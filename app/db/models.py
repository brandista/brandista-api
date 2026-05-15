"""Canonical platform identity models.

The `users` table is migrated in-place from the legacy `username PRIMARY
KEY` shape to the canonical `id UUID PRIMARY KEY` shape — see migration
`0002_canonical_platform_identity.py`. Legacy columns (`username`,
`search_limit`, `searches_used`) remain to keep Growth Engine code
paths working; they will be retired in a later cleanup once all callers
have been moved to canonical identity.

`Organization`, `Credits`, and `Entitlement` are new tables introduced
by the same migration. Each user belongs to exactly one organization;
credits and entitlements are scoped per-org, not per-user, so a team's
shared budget and feature flags follow the organization.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    users: Mapped[list[User]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    credits: Mapped[Credits | None] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
        uselist=False,
    )
    entitlements: Mapped[list[Entitlement]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class User(Base):
    __tablename__ = "users"

    # Canonical identity (the new PK after migration 0002)
    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    org_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )

    # Auth credentials — either or both may be set
    hashed_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    apple_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )

    # Profile
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="user")

    # Legacy Growth Engine columns — kept to avoid breaking existing code
    # paths in `database.py` and `main.py`. Retire in a later cleanup once
    # all callers have moved to canonical identity.
    username: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True
    )
    search_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    searches_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Status & timestamps
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    organization: Mapped[Organization] = relationship(back_populates="users")


class Credits(Base):
    __tablename__ = "credits"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    org_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    plan_monthly_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    organization: Mapped[Organization] = relationship(back_populates="credits")


class ProfileFact(Base):
    """A user-scoped semantic fact shared across Brandista products.

    One product writes (e.g. Continuity records a safety constraint),
    other products read (Veyra's coach drops impact exercises before
    plan generation). See
    `docs/superpowers/specs/2026-05-15-phase-4-2-facts-api-design.md`
    for the full design.

    `(user_id, scope, key)` is the natural key — a second write upserts
    the same row rather than creating a duplicate. `source_product`
    records which product introduced the fact, enabling per-product
    bulk delete on offboarding.
    """

    __tablename__ = "profile_facts"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "scope", "key", name="uq_profile_facts_user_scope_key"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    org_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_product: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    provenance: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[str] = mapped_column(String(8), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Entitlement(Base):
    __tablename__ = "entitlements"
    __table_args__ = (
        UniqueConstraint("org_id", "module", name="uq_entitlements_org_module"),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    org_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    module: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    organization: Mapped[Organization] = relationship(back_populates="entitlements")
