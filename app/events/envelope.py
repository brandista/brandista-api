"""On-the-wire envelope shape (GET response items).

Producer requests carry just the payload + metadata (`event_type`,
`source_product`, etc.); the server fills in `event_id`, `event_seq`,
`received_at`, and `envelope_sig`. Subscribers get the full envelope
on GET and verify the signature locally before processing.

The model is deliberately a thin DTO — it knows nothing about HMAC
internals, schema dispatch, or storage. Validation of `payload` is
the subscriber's responsibility against the appropriate
`app/events/types/*` model.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EventEnvelope(BaseModel):
    """Server → subscriber envelope.

    `envelope_sig` is bytes on the row; serialise as hex when crossing
    HTTP and decode on the subscriber side. Storing the raw bytes
    keeps `events.envelope_sig BYTEA NOT NULL` honest.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    event_seq: int = Field(ge=1)
    event_type: str = Field(min_length=1, max_length=64)
    event_version: int = Field(ge=1, le=255)
    user_id: UUID
    org_id: UUID
    source_product: str = Field(min_length=1, max_length=64)
    idempotency_key: str | None = Field(default=None, max_length=255)
    occurred_at: datetime
    received_at: datetime
    payload: dict[str, Any]
    envelope_sig_hex: str = Field(
        min_length=64, max_length=64, description="HMAC-SHA256 as 64-char hex"
    )
