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
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    LargeBinary,
    PrimaryKeyConstraint,
    Sequence,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PgUUID
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
    email_aliases: Mapped[list[UserEmailAlias]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserEmailAlias(Base):
    """Secondary email addresses that resolve to one canonical user.

    The canonical user row keeps a single primary `users.email`, but
    server-to-server integrations often only know an address from their
    own local identity store. Aliases let those integrations resolve
    old or short-form addresses without creating duplicate users.
    """

    __tablename__ = "user_email_aliases"

    email: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="email_aliases")


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


# ---------------------------------------------------------------------------
# Phase 4.3 — cross-product behavioural event ledger
#
# See `docs/superpowers/specs/2026-05-16-phase-4-3-event-bus-design-v0-2.md`.
# Migration `0007_event_bus.py` owns the DDL; these models are read/write
# helpers for the producer + subscriber routers. Hot-path columns
# (`workout_starts_at`, `workout_ends_at`, `severity_rank`) are populated
# by the producer router from a Pydantic-validated payload — not by the
# database — because PostgreSQL STORED generated columns require IMMUTABLE
# expressions and `text::timestamptz` is only STABLE.
# ---------------------------------------------------------------------------


class Event(Base):
    """A single row in the pull-based ledger.

    Two keys, different jobs:
    - `event_id` (UUID) — identity, dedup, envelope-signing.
    - `event_seq` (BIGSERIAL) — cursor, ordering, checkpoint.

    Both are server-side, but the producer router consumes them
    *before* INSERT (uuid4 + `nextval('events_event_seq_seq')`) so
    `envelope_sig BYTEA NOT NULL` is populated in the same statement.
    """

    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint(
            "source_product",
            "event_type",
            "user_id",
            "idempotency_key",
            name="uq_events_idempotency",
        ),
    )

    event_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    event_seq: Mapped[int] = mapped_column(
        BigInteger,
        Sequence("events_event_seq_seq"),
        unique=True,
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1
    )
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    org_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_product: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    envelope_sig: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    workout_starts_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    workout_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    severity_rank: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)


class EventSubscriber(Base):
    """Technical access-control registry.

    Adding a subscriber, or extending an existing one's
    `allowed_event_types`, is a deliberate operational action — INSERT
    /UPDATE here is the choke point that turns "medication.taken stays
    off in v1" from a process promise into a code-enforced refusal.
    """

    __tablename__ = "event_subscribers"

    subscriber_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    allowed_event_types: Mapped[list[str]] = mapped_column(
        ARRAY(Text()), nullable=False
    )
    allowed_source_products: Mapped[list[str]] = mapped_column(
        ARRAY(Text()), nullable=False
    )
    allowed_scope: Mapped[str] = mapped_column(
        String(16), nullable=False, default="user_self"
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


class EventSubscriberCheckpoint(Base):
    """Per-(subscriber, user) cursor state.

    Global cursor was rejected (v0.2 r2 §1): pulling user A's events to
    seq=1000 would silently skip user B's events with seq < 1000.
    """

    __tablename__ = "event_subscriber_checkpoints"
    __table_args__ = (
        PrimaryKeyConstraint(
            "subscriber_id",
            "user_id",
            name="pk_event_subscriber_checkpoints",
        ),
    )

    subscriber_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("event_subscribers.subscriber_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    last_processed_event_seq: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    last_processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EventHandlerAttempt(Base):
    """Per-(event, subscriber) retry + dead-letter state.

    Counter advances on handler raise; cursor does NOT advance until
    attempts >= 5 or success. Then the row's `dead_lettered_at` is set
    and the cursor moves past.
    """

    __tablename__ = "event_handler_attempts"
    __table_args__ = (
        PrimaryKeyConstraint(
            "event_id", "subscriber_id", name="pk_event_handler_attempts"
        ),
    )

    event_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("events.event_id", ondelete="CASCADE"),
        nullable=False,
    )
    subscriber_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("event_subscribers.subscriber_id", ondelete="CASCADE"),
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class EventAudit(Base):
    """Denormalised audit log, retention-independent of `events`.

    FK is SET NULL so audit outlives events after retention sweep.
    Denormalised columns let Sprint loppuraportti reconstruct timelines
    even after the source events row has been purged.
    """

    __tablename__ = "event_audit"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), primary_key=True
    )
    event_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("events.event_id", ondelete="SET NULL"),
        nullable=True,
    )
    event_seq_at_audit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_product: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    org_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    payload_summary: Mapped[dict] = mapped_column(JSONB, nullable=False)
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
