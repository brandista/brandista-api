"""SQLAlchemy database layer for canonical platform schema.

This package introduces the canonical Brandista platform identity layer
(Organization, User, Credits, Entitlement) on top of the existing
psycopg2-backed legacy schema. Legacy `database.py` continues to serve
Growth Engine's per-analysis tables; this package owns the canonical
identity tables that all Brandista products share (Continuity, Veyra,
Growth Engine, etc).

Migrations are managed by Alembic (`migrations/`). The existing `users`
table is migrated in-place from `username PRIMARY KEY` to `id UUID
PRIMARY KEY` with `org_id`, `google_id`, and `full_name` columns added —
see migration `0002_canonical_platform_identity.py` for the exact
backfill steps.
"""
