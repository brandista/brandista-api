"""Unit tests for the GDPR / Article-9 defensive scan used by the
profile facts API.

Pure-function module — no DB, no HTTP. Lives next to the router
because the boundary it enforces is the load-bearing safety contract
of Phase 4.2.
"""
from __future__ import annotations

import pytest

from app.auth.facts_safety import (
    FactGdprRejection,
    scan_for_gdpr_violations,
)


# ---------- dose patterns ----------

def test_accepts_payload_with_no_medical_content():
    scan_for_gdpr_violations(
        scope="training",
        key="available_equipment",
        value={"items": ["dumbbells_20kg_pair", "pull_up_bar"]},
    )
    # No exception = pass.


def test_rejects_mg_dose_string():
    with pytest.raises(FactGdprRejection) as exc:
        scan_for_gdpr_violations(
            scope="general",
            key="meds_note",
            value={"text": "ottaa 500 mg metformiinia aamulla"},
        )
    assert "dose" in str(exc.value)


def test_rejects_mcg_dose_no_space():
    with pytest.raises(FactGdprRejection):
        scan_for_gdpr_violations(
            scope="general",
            key="vitamin_note",
            value={"text": "75mcg D-vitamiinia päivittäin"},
        )


def test_rejects_iu_dose():
    with pytest.raises(FactGdprRejection):
        scan_for_gdpr_violations(
            scope="general",
            key="vitamin_note",
            value={"text": "200 IU vitamin E"},
        )


def test_rejects_dose_in_nested_array():
    """A dose hidden inside an array element must still be caught —
    the scan is recursive, not just top-level."""
    with pytest.raises(FactGdprRejection):
        scan_for_gdpr_violations(
            scope="general",
            key="notes",
            value={
                "items": [
                    {"kind": "supplement", "label": "500 mg magnesium"},
                ]
            },
        )


def test_rejects_finnish_tablet_count():
    with pytest.raises(FactGdprRejection):
        scan_for_gdpr_violations(
            scope="general",
            key="evening_routine",
            value={"text": "2 tablettia ennen unta"},
        )


def test_accepts_numbers_without_dose_units():
    """A bare number adjacent to non-dose units (kg, km, %, °C) must
    NOT be flagged — otherwise we couldn't store weights, distances,
    etc. in the training scope."""
    scan_for_gdpr_violations(
        scope="training",
        key="current_weight",
        value={"label": "75 kg", "trend_kg_30d": -1.5},
    )
    scan_for_gdpr_violations(
        scope="training",
        key="running_pace",
        value={"5km_min_sec": "24:30", "distance_km": 5},
    )


def test_dose_pattern_does_not_false_positive_on_keywords_in_other_context():
    """The literal letters 'mg' inside a longer word should not trip
    the regex — the pattern is word-bounded."""
    scan_for_gdpr_violations(
        scope="general",
        key="general_note",
        value={"text": "smgmtest is a fake word containing 'mg' inside"},
    )


# ---------- raw-diagnosis keys ----------

def test_rejects_diabetes_key():
    with pytest.raises(FactGdprRejection) as exc:
        scan_for_gdpr_violations(
            scope="safety",
            key="diabetes_type_2",
            value={"label": "Tyypin 2 diabetes"},
        )
    assert "raw_diagnosis" in str(exc.value)


def test_rejects_cancer_key():
    with pytest.raises(FactGdprRejection):
        scan_for_gdpr_violations(
            scope="safety",
            key="cancer",
            value={},
        )


def test_rejects_depression_key():
    with pytest.raises(FactGdprRejection):
        scan_for_gdpr_violations(
            scope="general",
            key="depression",
            value={},
        )


def test_diagnosis_key_check_is_case_insensitive():
    with pytest.raises(FactGdprRejection):
        scan_for_gdpr_violations(
            scope="safety",
            key="DIABETES",
            value={},
        )


def test_accepts_derived_label_for_diabetes():
    """The whole point of the diagnosis denylist: callers should use a
    derived label instead. 'carbohydrate_restriction' is fine because
    it describes the constraint, not the disease."""
    scan_for_gdpr_violations(
        scope="nutrition",
        key="carbohydrate_restriction",
        value={"label": "Pieni hiilihydraattipitoisuus, < 50g/päivä"},
    )


def test_accepts_safety_finding_with_derived_key():
    scan_for_gdpr_violations(
        scope="safety",
        key="cervical_spine_no_impact",
        value={
            "label": "Ei iskutreenejä",
            "blocked_actions": ["impact_cardio", "plyometrics"],
        },
    )
