"""health.recovery_pressure v1 — Continuity publishes, veyra-coach-builder reads.

Schema mirrors Continuity's SBE `Severity` literal (mild / moderate /
significant). The producer maps SBE `recovery_weakening` findings 1:1
into this payload — there's no SBE-side severity reduction or
threshold change here.

`severity_rank` is in the payload AND in the row column. Two reasons:

1. PostgreSQL string ordering puts `mild < moderate < significant`
   only by coincidence; `severity >= 'moderate'` is **not** a domain
   comparison. Indexed range filters need an integer.
2. The model-validator asserts producer and rank cannot drift — a
   typo'd severity that ships a contradictory rank is refused at
   validation time, before it can be signed or stored.

Decision-branching subscriber code reads `severity` (the named
literal), not the rank — the rank exists only for indexed filtering.

No raw biometric fields (`raw_hrv_ms`, `sleep_duration_ms`, etc.) per
Foundation invariant #3 + Sprint application §3.2; `extra="forbid"`
enforces.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Continuity SBE's domain ordering. Kept local to v1 so future event
# versions can evolve independently.
Severity = Literal["mild", "moderate", "significant"]
SEVERITY_RANK: dict[Severity, int] = {"mild": 1, "moderate": 2, "significant": 3}

ContributingSignal = Literal[
    "hrv_below_baseline", "sleep_deficit", "rhythm_deviation"
]


class HealthRecoveryPressureV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_at: datetime
    severity: Severity
    severity_rank: int = Field(ge=1, le=3)
    hrv_drop_pct: float = Field(le=0.0)
    contributing_signals: list[ContributingSignal] = Field(
        default_factory=list, max_length=4
    )

    @model_validator(mode="after")
    def _rank_matches_severity(self) -> "HealthRecoveryPressureV1":
        expected = SEVERITY_RANK[self.severity]
        if self.severity_rank != expected:
            raise ValueError(
                f"severity_rank={self.severity_rank} disagrees with "
                f"severity={self.severity!r} (expected {expected})"
            )
        return self
