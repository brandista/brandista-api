"""user_email_aliases — resolve secondary emails to canonical users

Revision ID: 0008_user_email_aliases
Revises: 0007_event_bus
Create Date: 2026-05-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "0008_user_email_aliases"
down_revision = "0007_event_bus"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_email_aliases",
        sa.Column("email", sa.String(length=255), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_user_email_aliases_user_id", "user_email_aliases", ["user_id"]
    )

    # Production continuity/veyra bridge alias. Guarded so staging/test
    # databases without this user, or DBs where the alias already exists
    # as a primary address, can migrate cleanly.
    op.execute(
        sa.text(
            """
            INSERT INTO user_email_aliases (email, user_id)
            SELECT 'tuukka@brandista.eu', u.id
            FROM users u
            WHERE u.email = 'tuukka.tuomisto@brandista.eu'
              AND NOT EXISTS (
                  SELECT 1 FROM users existing
                  WHERE existing.email = 'tuukka@brandista.eu'
              )
            ON CONFLICT (email) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_user_email_aliases_user_id", table_name="user_email_aliases")
    op.drop_table("user_email_aliases")
