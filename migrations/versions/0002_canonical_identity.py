"""canonical platform identity — organizations, in-place users migration, credits, entitlements

Revision ID: 0002_canonical_id
Revises: 0001_baseline
Create Date: 2026-05-13

This is the heart of Phase 4.1: migrate the legacy `users` table from
`username PRIMARY KEY` to canonical `id UUID PRIMARY KEY`, and introduce
`organizations` + `credits` + `entitlements` as new platform-layer
tables that every Brandista product (Growth Engine, Continuity, Veyra,
Kirjanpito, ...) will share.

Strategy
--------
In-place migration of `users` (not parallel `platform_users` tables) —
chosen after dependency audit: no other table FK-references `users`, so
the migration risk is bounded to the auth helpers in `database.py` /
`main.py` that read `users` by `username`. Those helpers keep working
because the `username` column is preserved (just demoted from PK to a
nullable UNIQUE column).

The migration:
  1. Enables pgcrypto extension (for `gen_random_uuid()`).
  2. Adds new columns to `users`: id (UUID), org_id (UUID), google_id,
     full_name, is_active, last_login. Type changes: created_at /
     updated_at gain timezone awareness.
  3. Creates `organizations`, `credits`, `entitlements`.
  4. Backfills: one organization per existing user (named after the
     user's email or username); back-fills email from username when the
     username looks like an email; populates id with gen_random_uuid();
     wires org_id to the per-user organization; seeds credits (balance=0,
     plan_monthly_limit=0); seeds an `entitlements.growth_engine` row
     per org so existing Growth Engine flows keep working.
  5. Demotes `username` from PRIMARY KEY to a nullable UNIQUE column.
  6. Promotes `id` to PRIMARY KEY.
  7. Tightens constraints: email NOT NULL + UNIQUE, org_id NOT NULL.

Reversibility
-------------
`downgrade()` reverses every step. It will fail if any row in `users`
has a NULL `username` after the migration was created — that's
intentional: post-migration creation of email-only users (no username)
cannot be downgraded without data loss, so we refuse rather than
silently drop rows.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0002_canonical_id"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Postgres extension for gen_random_uuid()
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # 2. Add new columns to users (nullable initially — backfilled below)
    op.add_column(
        "users",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("org_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("google_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("full_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("last_login", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # 3. Create canonical platform tables
    op.create_table(
        "organizations",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
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

    op.create_table(
        "credits",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column(
            "balance", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "plan_monthly_limit",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
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

    op.create_table(
        "entitlements",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("module", sa.String(length=100), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
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
        sa.UniqueConstraint("org_id", "module", name="uq_entitlements_org_module"),
    )
    op.create_index("ix_entitlements_org_id", "entitlements", ["org_id"])

    # 4. Backfill
    # 4a. Generate id where missing (gen_random_uuid default did this for
    # new inserts after step 2, but existing rows from before the ADD
    # COLUMN never ran the default, so populate them now).
    op.execute("UPDATE users SET id = gen_random_uuid() WHERE id IS NULL")

    # 4b. Backfill email from username when username looks like an email.
    op.execute(
        "UPDATE users SET email = username "
        "WHERE email IS NULL AND username LIKE '%@%'"
    )

    # 4c. Refuse to proceed if any user still has no email — we cannot
    # build canonical identity without it. The operator must fix the
    # data and re-run.
    op.execute(
        """
        DO $$
        DECLARE n_missing INTEGER;
        BEGIN
            SELECT COUNT(*) INTO n_missing FROM users WHERE email IS NULL OR email = '';
            IF n_missing > 0 THEN
                RAISE EXCEPTION
                    'canonical migration cannot proceed: % users have no email. '
                    'Set users.email for these rows manually before re-running.',
                    n_missing;
            END IF;
        END $$;
        """
    )

    # 4d. Create one organization per user, named after their email.
    op.execute(
        """
        INSERT INTO organizations (id, name, created_at, updated_at)
        SELECT gen_random_uuid(), u.email, now(), now()
        FROM users u
        WHERE u.org_id IS NULL
        """
    )

    # 4e. Wire each user to their org.
    op.execute(
        """
        UPDATE users u
        SET org_id = o.id
        FROM organizations o
        WHERE u.org_id IS NULL AND o.name = u.email
        """
    )

    # 4f. Seed credits and a growth_engine entitlement per org.
    op.execute(
        """
        INSERT INTO credits (org_id, balance, plan_monthly_limit)
        SELECT id, 0, 0 FROM organizations
        ON CONFLICT (org_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO entitlements (org_id, module, is_active)
        SELECT id, 'growth_engine', true FROM organizations
        ON CONFLICT (org_id, module) DO NOTHING
        """
    )

    # 5. Demote username from PK to nullable UNIQUE.
    # Drop the legacy PK constraint by its conventional name.
    op.execute("ALTER TABLE users DROP CONSTRAINT users_pkey")
    op.alter_column("users", "username", existing_type=sa.String(length=100), nullable=True)
    op.create_unique_constraint("uq_users_username", "users", ["username"])

    # 6. Promote id to PK and tighten id constraints.
    op.alter_column(
        "users",
        "id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_primary_key("users_pkey", "users", ["id"])

    # 7. Tighten email + org_id + add new constraints/indexes.
    op.alter_column(
        "users", "email", existing_type=sa.String(length=255), nullable=False
    )
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.create_index("ix_users_email", "users", ["email"])

    op.alter_column(
        "users",
        "org_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_users_org_id_organizations",
        "users",
        "organizations",
        ["org_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_users_org_id", "users", ["org_id"])

    op.create_unique_constraint("uq_users_google_id", "users", ["google_id"])
    op.create_index("ix_users_google_id", "users", ["google_id"])

    # Make created_at / updated_at timezone-aware (was TIMESTAMP without tz).
    op.alter_column(
        "users",
        "created_at",
        existing_type=sa.TIMESTAMP(timezone=False),
        type_=sa.TIMESTAMP(timezone=True),
        existing_nullable=False,
        existing_server_default=sa.text("CURRENT_TIMESTAMP"),
        server_default=sa.text("now()"),
    )
    op.alter_column(
        "users",
        "updated_at",
        existing_type=sa.TIMESTAMP(timezone=False),
        type_=sa.TIMESTAMP(timezone=True),
        existing_nullable=False,
        existing_server_default=sa.text("CURRENT_TIMESTAMP"),
        server_default=sa.text("now()"),
    )


def downgrade() -> None:
    # 1. Refuse to downgrade if any user has no username — we'd lose them.
    op.execute(
        """
        DO $$
        DECLARE n_missing INTEGER;
        BEGIN
            SELECT COUNT(*) INTO n_missing FROM users WHERE username IS NULL;
            IF n_missing > 0 THEN
                RAISE EXCEPTION
                    'canonical downgrade refused: % users have no username. '
                    'Downgrade would lose them.',
                    n_missing;
            END IF;
        END $$;
        """
    )

    # 2. Reverse the indexes and constraints.
    op.drop_index("ix_users_org_id", table_name="users")
    op.drop_constraint("fk_users_org_id_organizations", "users", type_="foreignkey")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_index("ix_users_google_id", table_name="users")
    op.drop_constraint("uq_users_google_id", "users", type_="unique")
    op.drop_constraint("uq_users_username", "users", type_="unique")

    # 3. Demote id from PK, promote username back to PK.
    op.drop_constraint("users_pkey", "users", type_="primary")
    op.alter_column(
        "users", "username", existing_type=sa.String(length=100), nullable=False
    )
    op.create_primary_key("users_pkey", "users", ["username"])

    # 4. Reverse the timestamp type change.
    op.alter_column(
        "users",
        "updated_at",
        existing_type=sa.TIMESTAMP(timezone=True),
        type_=sa.TIMESTAMP(timezone=False),
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    op.alter_column(
        "users",
        "created_at",
        existing_type=sa.TIMESTAMP(timezone=True),
        type_=sa.TIMESTAMP(timezone=False),
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )

    # 4b. Restore email to nullable (it was nullable in the 0001 baseline;
    # the canonical migration tightened it to NOT NULL after backfill).
    op.alter_column(
        "users", "email", existing_type=sa.String(length=255), nullable=True
    )

    # 5. Drop the new columns.
    op.drop_column("users", "last_login")
    op.drop_column("users", "is_active")
    op.drop_column("users", "full_name")
    op.drop_column("users", "google_id")
    op.drop_column("users", "org_id")
    op.drop_column("users", "id")

    # 6. Drop the new tables.
    op.drop_table("entitlements")
    op.drop_table("credits")
    op.drop_table("organizations")
