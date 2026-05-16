"""Event-type registry — single dispatch point for v1.

Hardcoded in code (not DB-backed) per spec §2. Each registered type
contributes four things:

- `schema`        — the Pydantic v1 model class for `payload`.
- `summarize`     — extracts the `payload_summary` JSONB stored on
                    `event_audit` rows. Keeps audit storage bounded
                    and decouples retention windows (events 365 d,
                    audit 730 d).
- `hot_path`      — derives the (optional) row columns
                    `workout_starts_at`, `workout_ends_at`, and
                    `severity_rank` from the validated payload. The
                    producer router copies these onto the `events`
                    row at INSERT — see spec §3 + §5 step 5.
- `gdpr_sensitive` — flag controlling whether the defensive GDPR scan
                     runs in addition to `extra="forbid"`. All v1
                     types have it on; the flag exists so future
                     non-health event types can opt out without
                     forgetting why.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from app.events.types.health_recovery_pressure_v1 import (
    HealthRecoveryPressureV1,
)
from app.events.types.medication_taken_v1 import MedicationTakenV1
from app.events.types.workout_completed_v1 import WorkoutCompletedV1
from app.events.types.workout_scheduled_v1 import WorkoutScheduledV1


class EventTypeNotRegisteredError(Exception):
    """Raised when an unknown `event_type` reaches the producer router."""


class PayloadValidationError(Exception):
    """Raised when payload doesn't match the registered schema.

    Carries the original `pydantic.ValidationError` for the router to
    extract a structured 422 body. Never log the original payload —
    Pydantic includes input snippets in `errors()` and we don't want
    those echoed if the payload was Art-9 material.
    """

    def __init__(self, inner: ValidationError) -> None:
        super().__init__("payload_validation_failed")
        self.inner = inner


@dataclass(frozen=True)
class HotPathColumns:
    """Optional column values the producer copies onto the `events` row."""

    workout_starts_at: Any | None = None
    workout_ends_at: Any | None = None
    severity_rank: int | None = None


@dataclass(frozen=True)
class _RegistryEntry:
    schema: type[BaseModel]
    summarize: Callable[[BaseModel], dict[str, Any]]
    hot_path: Callable[[BaseModel], HotPathColumns]
    gdpr_sensitive: bool


# ---- per-type summary + hot-path extractors --------------------------------

def _summarize_workout_scheduled(m: WorkoutScheduledV1) -> dict[str, Any]:
    return {
        "starts_at": m.starts_at,
        "ends_at": m.ends_at,
        "intensity": m.intensity,
        "title": m.title,
    }


def _hot_path_workout_scheduled(m: WorkoutScheduledV1) -> HotPathColumns:
    return HotPathColumns(
        workout_starts_at=m.starts_at,
        workout_ends_at=m.ends_at,
    )


def _summarize_workout_completed(m: WorkoutCompletedV1) -> dict[str, Any]:
    return {
        "started_at": m.started_at,
        "ended_at": m.ended_at,
        "completed_exercises_count": m.completed_exercises_count,
        "perceived_exertion_1_to_10": m.perceived_exertion_1_to_10,
    }


def _hot_path_workout_completed(_: WorkoutCompletedV1) -> HotPathColumns:
    return HotPathColumns()


def _summarize_health_recovery_pressure(
    m: HealthRecoveryPressureV1,
) -> dict[str, Any]:
    return {
        "observed_at": m.observed_at,
        "severity": m.severity,
        "severity_rank": m.severity_rank,
        "hrv_drop_pct": m.hrv_drop_pct,
        "contributing_signals": list(m.contributing_signals),
    }


def _hot_path_health_recovery_pressure(
    m: HealthRecoveryPressureV1,
) -> HotPathColumns:
    return HotPathColumns(severity_rank=m.severity_rank)


def _summarize_medication_taken(m: MedicationTakenV1) -> dict[str, Any]:
    # Schema-only in v1 — the producer flow doesn't route to a
    # subscriber. Summary intentionally minimal, no clinical fields.
    return {
        "taken_at": m.taken_at,
        "scheduled_at": m.scheduled_at,
        "delta_minutes": m.delta_minutes,
    }


def _hot_path_medication_taken(_: MedicationTakenV1) -> HotPathColumns:
    return HotPathColumns()


_REGISTRY: dict[str, _RegistryEntry] = {
    "workout.scheduled": _RegistryEntry(
        schema=WorkoutScheduledV1,
        summarize=_summarize_workout_scheduled,
        hot_path=_hot_path_workout_scheduled,
        gdpr_sensitive=True,
    ),
    "workout.completed": _RegistryEntry(
        schema=WorkoutCompletedV1,
        summarize=_summarize_workout_completed,
        hot_path=_hot_path_workout_completed,
        gdpr_sensitive=True,
    ),
    "health.recovery_pressure": _RegistryEntry(
        schema=HealthRecoveryPressureV1,
        summarize=_summarize_health_recovery_pressure,
        hot_path=_hot_path_health_recovery_pressure,
        gdpr_sensitive=True,
    ),
    "medication.taken": _RegistryEntry(
        schema=MedicationTakenV1,
        summarize=_summarize_medication_taken,
        hot_path=_hot_path_medication_taken,
        gdpr_sensitive=True,
    ),
}


def known_event_types() -> frozenset[str]:
    """All registered event-type strings."""
    return frozenset(_REGISTRY.keys())


def get_payload_schema(event_type: str) -> type[BaseModel]:
    """Schema class for a registered type. Raises if unknown."""
    entry = _REGISTRY.get(event_type)
    if entry is None:
        raise EventTypeNotRegisteredError(event_type)
    return entry.schema


def validate_payload(event_type: str, payload: Any) -> BaseModel:
    """Resolve schema, parse payload, return the validated model.

    Wraps `pydantic.ValidationError` in `PayloadValidationError` so the
    router can map it to 422 without leaking the upstream class.
    """
    schema = get_payload_schema(event_type)
    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        raise PayloadValidationError(exc) from exc


def summarize_payload(event_type: str, model: BaseModel) -> dict[str, Any]:
    """Audit `payload_summary` for a validated model."""
    entry = _REGISTRY[event_type]
    return entry.summarize(model)


def hot_path_columns(event_type: str, model: BaseModel) -> HotPathColumns:
    """Indexed row-column values derived from the validated payload."""
    entry = _REGISTRY[event_type]
    return entry.hot_path(model)


def requires_gdpr_scan(event_type: str) -> bool:
    """Whether the defensive GDPR scan runs in addition to schema rules."""
    entry = _REGISTRY[event_type]
    return entry.gdpr_sensitive
