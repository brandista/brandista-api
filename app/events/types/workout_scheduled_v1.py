"""workout.scheduled v1 — Veyra publishes, continuity-sbe-pipeline reads.

Schema mirrors Veyra's `WorkoutDayShape` (coach/route.ts):
  - `intensity` is the Veyra z.enum, kept verbatim (no translation).
  - No `workout_type` field — Veyra doesn't carry one.
  - `equipment_summary` is a bounded list of strings, separate from
    the `equipment.*` facts in the Phase 4.2 facts API.

Consumer use: continuity-sbe-pipeline filters
`event_type='workout.scheduled' AND workout_ends_at >= now-1h AND
workout_starts_at <= now+24h` and suppresses medication reminders
inside `[starts_at-15min, ends_at+15min]`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VeyranIntensity = Literal["kevyt", "sopiva", "raskas"]


class WorkoutScheduledV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starts_at: datetime
    ends_at: datetime
    intensity: VeyranIntensity
    title: str = Field(min_length=1, max_length=60)
    duration_descriptor: str = Field(min_length=1, max_length=40)
    equipment_summary: list[str] = Field(default_factory=list, max_length=20)
