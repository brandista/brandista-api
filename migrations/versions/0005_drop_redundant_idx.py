"""drop redundant explicit indexes on UNIQUE columns

Revision ID: 0005_drop_redundant_idx
Revises: 0004_apple_id
Create Date: 2026-05-15

Postgres automatically creates a btree index to back every UNIQUE
constraint. Earlier migrations (0002, 0004) additionally created
explicit `ix_*` indexes on the same columns — duplicated maintenance
overhead (every INSERT/UPDATE updates two indexes for the same
column) with no query-time benefit.

This migration drops the redundant explicit indexes. The UNIQUE
constraints (and their backing indexes) stay; ORM lookups by email /
google_id / apple_id continue to be index-scans.
"""
from __future__ import annotations

from alembic import op


revision = "0005_drop_redundant_idx"
down_revision = "0004_apple_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_google_id", table_name="users")
    op.drop_index("ix_users_apple_id", table_name="users")


def downgrade() -> None:
    op.create_index("ix_users_apple_id", "users", ["apple_id"])
    op.create_index("ix_users_google_id", "users", ["google_id"])
    op.create_index("ix_users_email", "users", ["email"])
