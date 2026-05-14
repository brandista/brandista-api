"""Declarative base for all canonical platform SQLAlchemy models."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Single declarative base for canonical platform tables.

    All models in `app.db.models` inherit from this. Alembic's
    `target_metadata` in `migrations/env.py` points to `Base.metadata`,
    so autogenerate sees only canonical tables — legacy psycopg2-managed
    tables (`analyses`, `competitor_*`, etc) are left untouched.
    """
