"""Pydantic schemas for the profile_facts API.

See `docs/superpowers/specs/2026-05-15-phase-4-2-facts-api-design.md`
for the design rationale.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


FactScope = Literal["safety", "nutrition", "training", "general"]
FactProvenance = Literal["user_stated", "extracted", "inferred"]
FactConfidence = Literal["high", "medium", "low"]


# Lowercase_snake_case discipline. Enforced at the API layer to keep
# the `key` namespace from drifting across products.
_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,118}[a-z0-9]$")


class FactCreate(BaseModel):
    """Request body for POST /api/v1/profile/facts.

    `value` is intentionally loose (any JSON object) — producer and
    consumer agree informally per (scope, key). Server-side
    schema-enforcement is a Phase 4.2+ follow-up if drift becomes a
    problem; for now key-naming discipline is enough.

    `source_product` IS in the request but the router validates it
    against the caller's JWT `product` claim — clients can't post a
    fact tagged source_product=continuity from a Veyra token.
    """

    model_config = ConfigDict(extra="forbid")

    scope: FactScope
    key: str = Field(..., min_length=2, max_length=120)
    value: dict[str, Any]
    source_product: str = Field(..., min_length=2, max_length=64)
    provenance: FactProvenance
    confidence: FactConfidence
    expires_at: datetime | None = None

    @field_validator("key")
    @classmethod
    def _key_is_snake_case(cls, v: str) -> str:
        if not _KEY_PATTERN.fullmatch(v):
            raise ValueError(
                "key must be lowercase_snake_case, start with a letter, "
                "and use only [a-z0-9_]"
            )
        return v


class Fact(BaseModel):
    """Read shape for a single fact row. Used in 201/200 responses to
    POST and inside the FactList GET response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    user_id: UUID
    scope: FactScope
    key: str
    value: dict[str, Any]
    source_product: str
    provenance: FactProvenance
    confidence: FactConfidence
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class FactList(BaseModel):
    """GET /api/v1/profile/facts response envelope.

    Wrapping the array in an object leaves room to add pagination,
    server time, or query echo later without breaking clients.
    """

    facts: list[Fact]
    as_of: datetime
