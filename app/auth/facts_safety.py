"""GDPR / Article-9 defensive scan for profile_facts payloads.

The facts table must not become a back-door for medical data. This
module rejects writes that look like they're carrying dose values or
raw clinical diagnoses. Same defense as Continuity's FOUNDATION_STATUS
invariant #3, repeated here so brandista-api stands on its own.

Two layers:

1. **Dose patterns** in the JSONB `value` payload — a number adjacent
   to `mg`, `mcg`, `µg`, `IU`, `tabletti(a)`, etc. Refused.
2. **Raw clinical-diagnosis keys** — explicit denylist of disease
   names that callers should be derived-labeling instead (e.g. use
   `carbohydrate_restriction` rather than `diabetes_type_2`).

Continuity is the only product allowed to write `safety`-scope facts
at all; that policy lives in the router, not here. This module is
purely about value-shape sniffing — it sees keys and JSON, not auth.
"""
from __future__ import annotations

import re
from typing import Any


class FactGdprRejection(Exception):
    """Raised by `scan_for_gdpr_violations` when a payload is refused.

    The argument is a short tag suitable for use as an HTTP detail
    string. Never includes the rejected content itself — that would
    just echo the sensitive data back to the client and the logs.
    """


# Dose-shaped substrings: a digit immediately (or via a space/decimal)
# followed by a known dose unit. Catches "500 mg", "12.5mg", "200 IU",
# "2 tablettia". Case-insensitive.
_DOSE_PATTERN = re.compile(
    r"(?i)\b\d+(?:[.,]\d+)?\s*(?:mg|mcg|µg|ug|iu|kpl|tabl|tablettia|tablets?)\b"
)

# Diagnoses callers should derive-label instead of recording verbatim.
# Not a complete medical ontology — focuses on terms most likely to
# leak from a coach extraction step. New entries cheap to add.
_FORBIDDEN_DIAGNOSIS_KEYS: frozenset[str] = frozenset(
    {
        "diabetes",
        "diabetes_type_1",
        "diabetes_type_2",
        "cancer",
        "depression",
        "anxiety_disorder",
        "bipolar",
        "schizophrenia",
        "hiv",
        "hepatitis",
        "addiction",
        "alcoholism",
        "eating_disorder",
        "anorexia",
        "bulimia",
    }
)

# Word-bounded substring patterns of the same diagnoses for the
# `value` text scan. Built once from `_FORBIDDEN_DIAGNOSIS_KEYS` plus
# Finnish/English natural-language variants that callers may
# inadvertently embed in a `user_note` or similar field. The pattern
# is intentionally crude — it favors false positives (refuse the
# write) over false negatives (silently store Art-9 data). Callers
# should derive-label instead, see scan_for_gdpr_violations docstring.
_DIAGNOSIS_TERMS_PATTERN = re.compile(
    r"(?i)\b("
    r"diabetes|diabetic|tyypi[nt]\s+\d+\s+diabetes|"
    r"cancer|syöp[äa]|carcinoma|tumour|tumor|"
    r"depression|masennus|"
    r"anxiety\s+disorder|ahdistuneisuush[äa]iri[öo]|"
    r"bipolar|kaksisuuntainen\s+mielialah[äa]iri[öo]|"
    r"schizophrenia|skitsofrenia|"
    r"\bhiv\b|aids|"
    r"hepatitis|hepatiitti|"
    r"addiction|riippuvuus|"
    r"alcoholism|alkoholismi|"
    r"anorexia|anoreksia|"
    r"bulimia|bulimia"
    r")\b"
)


def scan_for_gdpr_violations(*, scope: str, key: str, value: Any) -> None:
    """Raise FactGdprRejection if the (scope, key, value) tuple carries
    GDPR-Art-9 material that the facts API refuses to store.

    Three layers, in order:
      1. Raw-diagnosis key denylist (key=="diabetes" etc).
      2. Diagnosis terms anywhere in the value text (a derived-label
         `key` doesn't help if value.user_note says "tyypin 2 diabetes").
      3. Dose patterns anywhere in the value text.

    Pure function — no I/O, no logging. The router handles HTTP
    translation and audit logging.
    """
    # 1. Raw-diagnosis key denylist.
    key_lc = key.strip().lower()
    if key_lc in _FORBIDDEN_DIAGNOSIS_KEYS:
        raise FactGdprRejection("raw_diagnosis_key_not_allowed")

    # 2. Diagnosis terms in any string anywhere in the value.
    if _contains_diagnosis_term(value):
        raise FactGdprRejection("diagnosis_term_in_value_not_allowed")

    # 3. Dose patterns in any string anywhere in the value.
    if _contains_dose(value):
        raise FactGdprRejection("dose_data_not_allowed")


def _contains_diagnosis_term(node: Any) -> bool:
    """Walk a JSON-ish structure looking for diagnosis-term-shaped strings."""
    if isinstance(node, str):
        return _DIAGNOSIS_TERMS_PATTERN.search(node) is not None
    if isinstance(node, dict):
        return any(_contains_diagnosis_term(v) for v in node.values())
    if isinstance(node, list):
        return any(_contains_diagnosis_term(item) for item in node)
    return False


def _contains_dose(node: Any) -> bool:
    """Walk a JSON-ish structure looking for dose-shaped strings."""
    if isinstance(node, str):
        return _DOSE_PATTERN.search(node) is not None
    if isinstance(node, dict):
        return any(_contains_dose(v) for v in node.values())
    if isinstance(node, list):
        return any(_contains_dose(item) for item in node)
    return False
