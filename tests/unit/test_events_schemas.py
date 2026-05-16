"""Per-event-type Pydantic schema tests (Phase 4.3).

Verifies the §4 wire contract: `extra="forbid"`, bounded fields,
domain-specific validators (severity_rank ↔ severity, intensity enum,
default_factory list, etc).

DB-touching router tests are separate (require docker-compose
Postgres). HMAC + canonical JSON live in test_events_hmac.py. GDPR
scan lives in test_events_safety.py.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.events.registry import (
    EventTypeNotRegisteredError,
    get_payload_schema,
    hot_path_columns,
    known_event_types,
    requires_gdpr_scan,
    summarize_payload,
    validate_payload,
)
from app.events.types.health_recovery_pressure_v1 import (
    SEVERITY_RANK,
    HealthRecoveryPressureV1,
)
from app.events.types.medication_taken_v1 import MedicationTakenV1
from app.events.types.workout_completed_v1 import WorkoutCompletedV1
from app.events.types.workout_scheduled_v1 import WorkoutScheduledV1


# ---------- registry shape ----------


def test_known_event_types_is_the_four_v1_types():
    assert known_event_types() == {
        "workout.scheduled",
        "workout.completed",
        "health.recovery_pressure",
        "medication.taken",
    }


def test_get_payload_schema_returns_class_per_type():
    assert get_payload_schema("workout.scheduled") is WorkoutScheduledV1
    assert get_payload_schema("workout.completed") is WorkoutCompletedV1
    assert get_payload_schema("health.recovery_pressure") is HealthRecoveryPressureV1
    assert get_payload_schema("medication.taken") is MedicationTakenV1


def test_get_payload_schema_unknown_type_raises():
    with pytest.raises(EventTypeNotRegisteredError):
        get_payload_schema("workout.deleted")


def test_all_v1_types_are_gdpr_sensitive():
    for t in known_event_types():
        assert requires_gdpr_scan(t) is True


# ---------- workout.scheduled ----------


def _workout_scheduled_base(**overrides) -> dict:
    base = {
        "starts_at": "2026-05-16T18:00:00Z",
        "ends_at": "2026-05-16T18:45:00Z",
        "intensity": "sopiva",
        "title": "Zone 2 polkupyörä",
        "duration_descriptor": "45 min",
        "equipment_summary": [],
    }
    base.update(overrides)
    return base


def test_workout_scheduled_accepts_each_veyra_intensity():
    for intensity in ("kevyt", "sopiva", "raskas"):
        validate_payload("workout.scheduled", _workout_scheduled_base(intensity=intensity))


def test_workout_scheduled_rejects_english_intensity():
    from app.events.registry import PayloadValidationError
    with pytest.raises(PayloadValidationError) as exc:
        validate_payload("workout.scheduled", _workout_scheduled_base(intensity="moderate"))
    locs = {tuple(e["loc"]) for e in exc.value.inner.errors()}
    assert any("intensity" in loc for loc in locs)


def test_workout_scheduled_rejects_extra_field():
    with pytest.raises(Exception):
        validate_payload(
            "workout.scheduled",
            _workout_scheduled_base(raw_hrv_ms=42),
        )


def test_workout_scheduled_default_equipment_summary_is_empty_list():
    m = validate_payload(
        "workout.scheduled",
        {k: v for k, v in _workout_scheduled_base().items() if k != "equipment_summary"},
    )
    assert m.equipment_summary == []


def test_workout_scheduled_equipment_summary_max_20():
    payload = _workout_scheduled_base(equipment_summary=[f"item_{i}" for i in range(21)])
    with pytest.raises(Exception):
        validate_payload("workout.scheduled", payload)


def test_workout_scheduled_title_max_60():
    with pytest.raises(Exception):
        validate_payload(
            "workout.scheduled",
            _workout_scheduled_base(title="x" * 61),
        )


def test_workout_scheduled_summary_keys():
    m = validate_payload("workout.scheduled", _workout_scheduled_base())
    summary = summarize_payload("workout.scheduled", m)
    assert set(summary.keys()) == {"starts_at", "ends_at", "intensity", "title"}


def test_workout_scheduled_hot_path_populates_window():
    m = validate_payload("workout.scheduled", _workout_scheduled_base())
    hot = hot_path_columns("workout.scheduled", m)
    assert hot.workout_starts_at is not None
    assert hot.workout_ends_at is not None
    assert hot.severity_rank is None


# ---------- workout.completed ----------


def test_workout_completed_optional_perceived_exertion():
    m = validate_payload(
        "workout.completed",
        {
            "started_at": "2026-05-16T17:00:00Z",
            "ended_at": "2026-05-16T17:50:00Z",
            "completed_exercises_count": 6,
        },
    )
    assert m.perceived_exertion_1_to_10 is None


def test_workout_completed_rpe_bounded_1_to_10():
    base = {
        "started_at": "2026-05-16T17:00:00Z",
        "ended_at": "2026-05-16T17:50:00Z",
        "completed_exercises_count": 6,
    }
    with pytest.raises(Exception):
        validate_payload("workout.completed", {**base, "perceived_exertion_1_to_10": 11})
    with pytest.raises(Exception):
        validate_payload("workout.completed", {**base, "perceived_exertion_1_to_10": 0})


def test_workout_completed_rejects_estimated_kcal():
    with pytest.raises(Exception):
        validate_payload(
            "workout.completed",
            {
                "started_at": "2026-05-16T17:00:00Z",
                "ended_at": "2026-05-16T17:50:00Z",
                "completed_exercises_count": 6,
                "estimated_kcal": 420,
            },
        )


def test_workout_completed_hot_path_is_empty():
    m = validate_payload(
        "workout.completed",
        {
            "started_at": "2026-05-16T17:00:00Z",
            "ended_at": "2026-05-16T17:50:00Z",
            "completed_exercises_count": 6,
        },
    )
    hot = hot_path_columns("workout.completed", m)
    assert hot.workout_starts_at is None
    assert hot.workout_ends_at is None
    assert hot.severity_rank is None


# ---------- health.recovery_pressure ----------


def _recovery_base(**overrides) -> dict:
    base = {
        "observed_at": "2026-05-16T06:14:00Z",
        "severity": "significant",
        "severity_rank": 3,
        "hrv_drop_pct": -27.0,
        "contributing_signals": ["hrv_below_baseline", "sleep_deficit"],
    }
    base.update(overrides)
    return base


def test_recovery_pressure_accepts_each_severity():
    for severity in ("mild", "moderate", "significant"):
        validate_payload(
            "health.recovery_pressure",
            _recovery_base(severity=severity, severity_rank=SEVERITY_RANK[severity]),
        )


def test_recovery_pressure_rank_mismatch_rejected():
    from app.events.registry import PayloadValidationError
    with pytest.raises(PayloadValidationError) as exc:
        validate_payload(
            "health.recovery_pressure",
            _recovery_base(severity="significant", severity_rank=1),
        )
    msg = str(exc.value.inner)
    assert "severity_rank" in msg


def test_recovery_pressure_hrv_drop_must_be_negative():
    with pytest.raises(Exception):
        validate_payload(
            "health.recovery_pressure", _recovery_base(hrv_drop_pct=5.0)
        )


def test_recovery_pressure_rejects_raw_biometric_field():
    with pytest.raises(Exception):
        validate_payload(
            "health.recovery_pressure",
            _recovery_base(raw_hrv_ms=42),
        )


def test_recovery_pressure_contributing_signals_constrained():
    with pytest.raises(Exception):
        validate_payload(
            "health.recovery_pressure",
            _recovery_base(contributing_signals=["hrv_below_baseline", "bogus"]),
        )


def test_recovery_pressure_default_signals_empty_list():
    payload = {k: v for k, v in _recovery_base().items() if k != "contributing_signals"}
    m = validate_payload("health.recovery_pressure", payload)
    assert m.contributing_signals == []


def test_recovery_pressure_hot_path_carries_severity_rank():
    m = validate_payload("health.recovery_pressure", _recovery_base())
    hot = hot_path_columns("health.recovery_pressure", m)
    assert hot.severity_rank == 3
    assert hot.workout_starts_at is None


# ---------- medication.taken ----------


def test_medication_taken_minimal_payload():
    m = validate_payload(
        "medication.taken",
        {
            "taken_at": "2026-05-16T09:00:00Z",
            "scheduled_at": "2026-05-16T08:00:00Z",
            "delta_minutes": 60,
        },
    )
    assert m.delta_minutes == 60


def test_medication_taken_rejects_drug_name_field():
    """Schema must not silently accept clinical fields even though it's
    not currently routed to any subscriber."""
    with pytest.raises(Exception):
        validate_payload(
            "medication.taken",
            {
                "taken_at": "2026-05-16T09:00:00Z",
                "scheduled_at": "2026-05-16T08:00:00Z",
                "delta_minutes": 60,
                "drug_name": "metformin",
            },
        )
