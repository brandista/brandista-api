"""profile_facts — cross-product semantic facts

Revision ID: 0006_profile_facts
Revises: 0005_drop_redundant_idx
Create Date: 2026-05-15

Phase 4.2 schema. See
`docs/superpowers/specs/2026-05-15-phase-4-2-facts-api-design.md` §3.

A user-scoped store of discrete, long-lived semantic facts shared
across Brandista products. One product writes (e.g. Continuity records
a safety constraint), other products read (Veyra's coach drops impact
exercises). Aimed at facts that hold for weeks/months — aggregate /
time-series data lives elsewhere (Phase 4.3 event bus).

GDPR-sensitivity boundary is enforced at the API layer (dose patterns,
raw-diagnosis keys refused), not the schema layer. The schema is
deliberately liberal so the boundary can be tightened without DDL
churn.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "0006_profile_facts"
down_revision = "0005_drop_redundant_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profile_facts",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value", JSONB, nullable=False),
        sa.Column("source_product", sa.String(length=64), nullable=False),
        sa.Column("provenance", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.String(length=8), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
        sa.UniqueConstraint(
            "user_id", "scope", "key", name="uq_profile_facts_user_scope_key"
        ),
    )
    # Most common read: GET facts for the current user, optionally filtered to a scope set.
    op.create_index(
        "ix_profile_facts_user_id_scope", "profile_facts", ["user_id", "scope"]
    )
    # Admin / GDPR-purge by org.
    op.create_index("ix_profile_facts_org_id", "profile_facts", ["org_id"])
    # Bulk delete on product offboarding.
    op.create_index(
        "ix_profile_facts_source_product", "profile_facts", ["source_product"]
    )


def downgrade() -> None:
    op.drop_index("ix_profile_facts_source_product", table_name="profile_facts")
    op.drop_index("ix_profile_facts_org_id", table_name="profile_facts")
    op.drop_index("ix_profile_facts_user_id_scope", table_name="profile_facts")
    op.drop_table("profile_facts")
