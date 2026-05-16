"""GDPR / Article-9 defensive scan tests for event payloads (Phase 4.3).

`extra="forbid"` on each schema already rejects unexpected top-level
fields. The scan defends against valid-shape fields carrying Art-9
content in their string values — the "user typed their diagnosis
into `title`" case.

Patterns reused from `app/auth/facts_safety.py`, so dose + diagnosis
wording stays in lockstep across facts and events.
"""
from __future__ import annotations

import pytest

from app.events.safety import EventGdprRejection, scan_payload_for_gdpr_violations


# ---------- dose-shaped strings ----------


@pytest.mark.parametrize(
    "value",
    [
        "metformin 500 mg",
        "B12 1000 mcg",
        "vitamin D 2000 IU",
        "ibuprofen 200mg",
        "2 tablettia/päivä",
        "12.5 mg dose",
        "Insuliini 2 tabl",
    ],
)
def test_dose_patterns_in_string_field(value):
    with pytest.raises(EventGdprRejection) as exc:
        scan_payload_for_gdpr_violations({"title": value})
    assert "dose_data_not_allowed" in str(exc.value)


def test_dose_pattern_in_nested_list_rejected():
    with pytest.raises(EventGdprRejection):
        scan_payload_for_gdpr_violations(
            {"equipment_summary": ["dumbbells", "vitamin D 2000 IU"]}
        )


def test_dose_pattern_in_nested_dict_rejected():
    with pytest.raises(EventGdprRejection):
        scan_payload_for_gdpr_violations(
            {"contributing_signals": [], "context": {"note": "metformin 500 mg"}}
        )


def test_clean_workout_passes():
    scan_payload_for_gdpr_violations(
        {
            "intensity": "sopiva",
            "title": "Zone 2 polkupyörä",
            "duration_descriptor": "45 min",
            "equipment_summary": [],
        }
    )


# ---------- diagnosis terms ----------


@pytest.mark.parametrize(
    "value",
    [
        "tyypin 2 diabetes flares up",
        "user has cancer",
        "diagnosed with depression",
        "bipolar episode",
        "potilaalla syöpä",
        "skitsofrenia",
        "HIV positive",
    ],
)
def test_diagnosis_terms_in_payload_rejected(value):
    with pytest.raises(EventGdprRejection) as exc:
        scan_payload_for_gdpr_violations({"note": value})
    assert "diagnosis_term_in_payload_not_allowed" in str(exc.value)


def test_diagnosis_term_in_nested_list_rejected():
    with pytest.raises(EventGdprRejection):
        scan_payload_for_gdpr_violations(
            {"contributing_signals": ["sleep_deficit", "tyypin 2 diabetes"]}
        )


# ---------- forbidden diagnosis keys ----------


@pytest.mark.parametrize("key", ["diabetes", "cancer", "depression", "hiv", "anorexia"])
def test_forbidden_diagnosis_keys_at_top_level(key):
    with pytest.raises(EventGdprRejection) as exc:
        scan_payload_for_gdpr_violations({key: "yes"})
    assert "raw_diagnosis_key_not_allowed" in str(exc.value)


def test_forbidden_diagnosis_key_nested():
    with pytest.raises(EventGdprRejection):
        scan_payload_for_gdpr_violations(
            {"context": {"diabetes": "type_1"}}
        )


# ---------- non-string scalars are not falsely flagged ----------


def test_pure_numeric_payload_passes():
    scan_payload_for_gdpr_violations(
        {"severity_rank": 3, "hrv_drop_pct": -27.0, "delta_minutes": 60}
    )


def test_iso_timestamps_pass():
    scan_payload_for_gdpr_violations(
        {"observed_at": "2026-05-16T06:14:00Z", "starts_at": "2026-05-16T18:00:00Z"}
    )
