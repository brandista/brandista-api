"""GDPR / Article-9 defensive scan for event payloads.

Direct sibling of `app/auth/facts_safety.py`. Repeated rather than
shared because the two safety surfaces have different lifecycles —
facts can be deleted by the user; events are append-only — and we
want either surface to be tightenable without touching the other.

The actual regex patterns are imported from `facts_safety` so dose
detection and diagnosis-term wording stay in sync. New rules live
there; this module composes them for the event payload shape.

Pydantic `extra="forbid"` already rejects unexpected top-level fields
(e.g. `raw_hrv_ms`); this scan defends against valid-shape fields
carrying GDPR-Art-9 content in their string values — the "user
helpfully typed their diagnosis into `title`" case.
"""
from __future__ import annotations

from typing import Any

from app.auth.facts_safety import (
    _DIAGNOSIS_TERMS_PATTERN,
    _DOSE_PATTERN,
    _FORBIDDEN_DIAGNOSIS_KEYS,
)


class EventGdprRejection(Exception):
    """Raised when an event payload contains GDPR-Art-9 material.

    The argument is a short tag the router maps to an HTTP `detail`
    string. Never includes the rejected content itself.
    """


def scan_payload_for_gdpr_violations(payload: Any) -> None:
    """Walk the payload looking for diagnosis terms or dose patterns.

    Pure function. No I/O, no logging. Same crude-favor-false-positive
    approach as the facts safety scan — better to refuse a write than
    silently store Art-9 material.
    """
    if _contains_forbidden_diagnosis_key(payload):
        raise EventGdprRejection("raw_diagnosis_key_not_allowed")
    if _contains_diagnosis_term(payload):
        raise EventGdprRejection("diagnosis_term_in_payload_not_allowed")
    if _contains_dose(payload):
        raise EventGdprRejection("dose_data_not_allowed")


def _contains_forbidden_diagnosis_key(node: Any) -> bool:
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str) and k.strip().lower() in _FORBIDDEN_DIAGNOSIS_KEYS:
                return True
            if _contains_forbidden_diagnosis_key(v):
                return True
        return False
    if isinstance(node, list):
        return any(_contains_forbidden_diagnosis_key(item) for item in node)
    return False


def _contains_diagnosis_term(node: Any) -> bool:
    if isinstance(node, str):
        return _DIAGNOSIS_TERMS_PATTERN.search(node) is not None
    if isinstance(node, dict):
        return any(_contains_diagnosis_term(v) for v in node.values())
    if isinstance(node, list):
        return any(_contains_diagnosis_term(item) for item in node)
    return False


def _contains_dose(node: Any) -> bool:
    if isinstance(node, str):
        return _DOSE_PATTERN.search(node) is not None
    if isinstance(node, dict):
        return any(_contains_dose(v) for v in node.values())
    if isinstance(node, list):
        return any(_contains_dose(item) for item in node)
    return False
