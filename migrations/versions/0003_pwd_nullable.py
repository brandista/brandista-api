"""Drop NOT NULL on users.hashed_password.

Migration 0002 backfilled new Google/magic-link users with an empty-string
sentinel for hashed_password because the legacy column was NOT NULL. The
SQLAlchemy model (`app/db/models.py`) has always declared it nullable, so
this migration just brings the DB schema in line with the model and lets
`provision_canonical_user` insert NULL going forward.

Existing rows with hashed_password = '' or real bcrypt hashes are not
touched. The optional backfill of '' -> NULL is intentionally NOT part of
this migration (cosmetic only; the API doesn't distinguish '' from NULL).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0003_pwd_nullable"
down_revision = "0002_canonical_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.Text(),
        nullable=True,
    )


def downgrade() -> None:
    """Restore NOT NULL on hashed_password.

    Refuses to proceed if any row has NULL hashed_password — running the
    downgrade after passwordless users have been provisioned would either
    drop them or fail the constraint application. Backfill NULLs to ''
    explicitly before downgrading.
    """
    conn = op.get_bind()
    null_count = conn.execute(
        sa.text("SELECT count(*) FROM users WHERE hashed_password IS NULL")
    ).scalar()
    if null_count and null_count > 0:
        raise RuntimeError(
            f"refuse to downgrade: {null_count} users have NULL hashed_password. "
            "Backfill these to '' (or delete the rows) before downgrading."
        )
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.Text(),
        nullable=False,
    )
