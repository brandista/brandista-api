"""baseline — legacy users table (pre-canonical)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-13

Captures the legacy `users` table shape that `database.py` has been
auto-creating at boot. In production, run `alembic stamp 0001_baseline`
ONCE — the table already exists; this just records that alembic now
manages it from this revision onwards. In dev/test (clean DB), running
`alembic upgrade head` creates the table from scratch with the same
shape, so canonical migration 0002 can ALTER it in-place.

Tables NOT included here (analyses, competitor_discoveries,
competitor_results, user_analysis_usage) remain managed by
`analysis_history_schema.sql` + `database.py` boot-time code. They will
move under alembic in a later cleanup; for now they're out of canonical
metadata so alembic autogenerate leaves them alone.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("username", sa.String(length=100), primary_key=True),
        sa.Column("hashed_password", sa.Text(), nullable=False),
        sa.Column(
            "role",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'user'"),
        ),
        sa.Column(
            "search_limit",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("3"),
        ),
        sa.Column(
            "searches_used",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=False),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=False),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )


def downgrade() -> None:
    op.drop_table("users")
