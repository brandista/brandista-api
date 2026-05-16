"""event_bus — cross-product behavioural coordination ledger

Revision ID: 0007_event_bus
Revises: 0006_profile_facts
Create Date: 2026-05-16

Phase 4.3 schema. See
`docs/superpowers/specs/2026-05-16-phase-4-3-event-bus-design-v0-2.md`
§3 for the full design rationale.

Five tables form a pull-based event ledger (no external broker):

- `events`             — the ledger itself. event_seq BIGSERIAL is the
                         cursor key; event_id UUID is the identity /
                         signing / dedup key. Hot-path columns
                         (workout_starts_at/_ends_at, severity_rank)
                         are app-populated from Pydantic-validated
                         payload — STORED generated columns rejected
                         because text::timestamptz is STABLE, not
                         IMMUTABLE.
- `event_subscribers`  — technical access control registry; what each
                         subscriber is allowed to read. Seeded with
                         continuity-sbe-pipeline and veyra-coach-builder.
- `event_subscriber_checkpoints`
                       — per-(subscriber, user) cursor state. Global
                         cursor was rejected (would silently skip
                         events of other users — see v0.2 r2 §1).
- `event_handler_attempts`
                       — per-(event, subscriber) retry counter +
                         dead-letter timestamp.
- `event_audit`        — denormalised, retention-independent log used
                         for Sprint loppuraportti reconstruction.
                         FK ON DELETE SET NULL so audit can outlive
                         events through retention sweeps.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA, JSONB, UUID


revision = "0007_event_bus"
down_revision = "0006_profile_facts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- events ---------------------------------------------------------
    op.create_table(
        "events",
        sa.Column(
            "event_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # BIGSERIAL: cursor / ordering key. The application consumes the
        # underlying sequence via explicit nextval() *before* INSERT so
        # the envelope signature can include event_seq in the same
        # statement — see spec §5 step 5 + §7.
        sa.Column(
            "event_seq",
            sa.BigInteger,
            sa.Sequence("events_event_seq_seq"),
            unique=True,
            nullable=False,
            server_default=sa.text("nextval('events_event_seq_seq')"),
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column(
            "event_version", sa.SmallInteger, nullable=False, server_default="1"
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_product", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column(
            "occurred_at", sa.TIMESTAMP(timezone=True), nullable=False
        ),
        sa.Column(
            "received_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("envelope_sig", BYTEA, nullable=False),
        # Hot-path filter columns. Populated by the producer router from
        # the Pydantic-validated payload — NOT generated columns.
        # PostgreSQL requires STORED expressions to be IMMUTABLE; the
        # text->timestamptz cast is only STABLE (consults session
        # TimeZone for naive strings).
        sa.Column(
            "workout_starts_at", sa.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column(
            "workout_ends_at", sa.TIMESTAMP(timezone=True), nullable=True
        ),
        # severity_rank: indexed range key for health.recovery_pressure.
        # Domain ranking (mild=1, moderate=2, significant=3) — string
        # comparison on `severity` has no domain ordering. See §4.
        sa.Column("severity_rank", sa.SmallInteger, nullable=True),
        sa.UniqueConstraint(
            "source_product",
            "event_type",
            "user_id",
            "idempotency_key",
            name="uq_events_idempotency",
        ),
    )
    # Cursor scan per user (steady-state pull pattern).
    op.create_index("ix_events_user_seq", "events", ["user_id", "event_seq"])
    # Type-wide scans (Sprint loppuraportti, replay CLI by type).
    op.create_index("ix_events_type_seq", "events", ["event_type", "event_seq"])
    # Suppression-window query for continuity-sbe-pipeline (W1).
    op.create_index(
        "ix_events_workout_window",
        "events",
        ["user_id", "workout_starts_at", "workout_ends_at"],
        postgresql_where=sa.text("event_type = 'workout.scheduled'"),
    )
    # Severity range filter for veyra-coach-builder (R1 Karoliina).
    op.create_index(
        "ix_events_recovery_severity",
        "events",
        ["user_id", "severity_rank", sa.text("occurred_at DESC")],
        postgresql_where=sa.text("event_type = 'health.recovery_pressure'"),
    )

    # ---- event_subscribers ---------------------------------------------
    op.create_table(
        "event_subscribers",
        sa.Column("subscriber_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "allowed_event_types", ARRAY(sa.Text()), nullable=False
        ),
        sa.Column(
            "allowed_source_products", ARRAY(sa.Text()), nullable=False
        ),
        sa.Column(
            "allowed_scope",
            sa.String(length=16),
            nullable=False,
            server_default="user_self",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Seed v1 production subscribers. medication.taken is deliberately
    # absent from every allowed list (see spec §3).
    op.execute(
        sa.text(
            """
            INSERT INTO event_subscribers
                (subscriber_id, allowed_event_types,
                 allowed_source_products, allowed_scope)
            VALUES
                ('continuity-sbe-pipeline',
                 ARRAY['workout.scheduled','workout.completed'],
                 ARRAY['veyra'],
                 'user_self'),
                ('veyra-coach-builder',
                 ARRAY['health.recovery_pressure'],
                 ARRAY['continuity'],
                 'user_self')
            """
        )
    )

    # ---- event_subscriber_checkpoints ----------------------------------
    op.create_table(
        "event_subscriber_checkpoints",
        sa.Column(
            "subscriber_id",
            sa.String(length=64),
            sa.ForeignKey(
                "event_subscribers.subscriber_id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "last_processed_event_seq",
            sa.BigInteger,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "last_processed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint(
            "subscriber_id", "user_id", name="pk_event_subscriber_checkpoints"
        ),
    )

    # ---- event_handler_attempts ----------------------------------------
    op.create_table(
        "event_handler_attempts",
        sa.Column(
            "event_id",
            UUID(as_uuid=True),
            sa.ForeignKey("events.event_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subscriber_id",
            sa.String(length=64),
            sa.ForeignKey(
                "event_subscribers.subscriber_id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column(
            "attempts", sa.SmallInteger, nullable=False, server_default="0"
        ),
        sa.Column(
            "last_attempt_at", sa.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column(
            "dead_lettered_at", sa.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.PrimaryKeyConstraint(
            "event_id", "subscriber_id", name="pk_event_handler_attempts"
        ),
    )
    # Operational dead-letter dashboard query.
    op.create_index(
        "ix_event_handler_attempts_dead_lettered",
        "event_handler_attempts",
        ["subscriber_id", "dead_lettered_at"],
        postgresql_where=sa.text("dead_lettered_at IS NOT NULL"),
    )

    # ---- event_audit ---------------------------------------------------
    # FK ON DELETE SET NULL + denormalised columns = audit outlives the
    # event after retention sweep. Sprint loppuraportti reconstruction
    # window is the design goal.
    op.create_table(
        "event_audit",
        sa.Column(
            "id",
            sa.BigInteger,
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column(
            "event_id",
            UUID(as_uuid=True),
            sa.ForeignKey("events.event_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_seq_at_audit", sa.BigInteger, nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("source_product", sa.String(length=64), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("payload_summary", JSONB, nullable=False),
        sa.Column("actor_kind", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor_meta", JSONB, nullable=True),
        sa.Column(
            "occurred_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_event_audit_user_occurred",
        "event_audit",
        ["user_id", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_event_audit_event_id",
        "event_audit",
        ["event_id"],
        postgresql_where=sa.text("event_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_event_audit_event_id", table_name="event_audit")
    op.drop_index("ix_event_audit_user_occurred", table_name="event_audit")
    op.drop_table("event_audit")
    op.drop_index(
        "ix_event_handler_attempts_dead_lettered",
        table_name="event_handler_attempts",
    )
    op.drop_table("event_handler_attempts")
    op.drop_table("event_subscriber_checkpoints")
    op.drop_table("event_subscribers")
    op.drop_index("ix_events_recovery_severity", table_name="events")
    op.drop_index("ix_events_workout_window", table_name="events")
    op.drop_index("ix_events_type_seq", table_name="events")
    op.drop_index("ix_events_user_seq", table_name="events")
    op.drop_table("events")
    op.execute("DROP SEQUENCE IF EXISTS events_event_seq_seq")
