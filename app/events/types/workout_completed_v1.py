"""workout.completed v1 — Veyra publishes, continuity-sbe-pipeline reads.

No `workout_type`, no `estimated_kcal` — Veyra's completion state
doesn't track them. `completed_exercises_count` is the honest proxy
for "did the workout happen"; `perceived_exertion_1_to_10` is optional
RPE.

Consumer use: ContinuityScore aggregator reads the last 7 days of
`workout.completed` via the (event_type, event_seq) index; chapter
detector flags `consecutive_training_strain` when count>5 AND
avg(RPE)>=7 in a 7-day window.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkoutCompletedV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    started_at: datetime
    ended_at: datetime
    completed_exercises_count: int = Field(ge=0, le=50)
    perceived_exertion_1_to_10: int | None = Field(default=None, ge=1, le=10)
