"""medication.taken v1 — schema only, no v1 subscriber.

The schema exists so v2 can implement opt-in publishing cleanly without
a migration. In v1 no subscriber has this type in `allowed_event_types`
and no publisher emits it — production refuses the type because the
registry filter excludes it, not because the schema is missing.

Forbidden by construction: drug name, dose, prescription id. Even the
timing alone is GDPR-Art-9, hence the registry refusal in v1.

Accepting this type into production requires both:
  1. INSERT into `event_subscribers.allowed_event_types`.
  2. INSERT into a per-user opt-in row (future
     `user_profile.medication_event_publish_enabled`).
Coupled in code review, not by schema.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MedicationTakenV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    taken_at: datetime
    scheduled_at: datetime
    delta_minutes: int
