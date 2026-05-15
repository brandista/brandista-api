"""apple_id — Apple sign-in stable identifier

Revision ID: 0004_apple_id
Revises: 0003_pwd_nullable
Create Date: 2026-05-15

Adds `users.apple_id text UNIQUE NULL`. Apple's `sub` claim is the
stable user identifier across all sign-ins; we need to store it because:

  - Apple may hide the email behind a private-relay address that can
    rotate (the user can disable email forwarding and re-enable it,
    landing them on a new relay address).
  - `sub` is the only Apple-side guarantee of identity persistence
    across sign-ins.

The column is nullable so it can be backfilled lazily on a user's next
canonical sign-in. UNIQUE so the same Apple identity can't be bridged
to two canonical users.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0004_apple_id"
down_revision = "0003_pwd_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("apple_id", sa.String(length=255), nullable=True),
    )
    op.create_unique_constraint("uq_users_apple_id", "users", ["apple_id"])
    op.create_index("ix_users_apple_id", "users", ["apple_id"])


def downgrade() -> None:
    op.drop_index("ix_users_apple_id", table_name="users")
    op.drop_constraint("uq_users_apple_id", "users", type_="unique")
    op.drop_column("users", "apple_id")
