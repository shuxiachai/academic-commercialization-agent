"""Pure selector checks for a fresh observer-integrity identity.

Configuration calls are in-memory only. No candidate main, guard, preparation,
provider, subprocess, Identity or Observe is run by these selector tests.
"""

from pathlib import Path

import pytest

from evals.reviewer_comparison_v3 import test_invoker as invoker


NT312 = ("nt", "cpython", (3, 12))
CASE = "e0591d8f-bb7d-4ba6-a41a-fd62d30c87e3"
CLOSED_FF_CASE = "60641bee-b8b2-4a2d-a6e7-b64c0db65f8d"


def selector_values():
    return {"REVIEWER_V3_FF_CASE": CASE, "REVIEWER_V3_FF_CONTROL_SHA256": "a" * 64}


def test_integrity_selector_accepts_only_the_exact_fresh_binding():
    """Fresh identity must retain the original FF envelope without reopening its old case."""
    assert invoker._FF_CASE == CASE and CASE != CLOSED_FF_CASE
    assert invoker._FF_INPUTS == ("REVIEWER_V3_FF_CASE", "REVIEWER_V3_FF_CONTROL_SHA256")
    assert CASE not in invoker._H6_CASES and CLOSED_FF_CASE not in invoker._H6_CASES
    assert invoker._ff_configuration({}, platform=NT312) is None
    actual = invoker._ff_configuration(selector_values(), platform=NT312)
    assert actual["case_id"] == CASE
    assert actual["diagnostic_binding"] == "explicit_ff" and actual["mode"] == "missing-control"
    assert actual["control_sha256"] == "a" * 64
    assert actual["policy_applicable"] is True and actual["platform_validation"] == "not_evaluated"
    assert invoker._FF_POLICY["case_id"] == CASE
    assert Path(__file__).name not in {Path(path).name for path in invoker.CHECK_FILES}


@pytest.mark.parametrize("defect", [
    "closed-ff", "mixed-h6-case", "mixed-h6-control", "case-value-upper",
    "case-key-lower", "control-key-lower", "duplicate-case-lower",
    "nt311", "nt313", "pypy312", "posix312",
], ids=["closed-ff", "h6-case", "h6-control", "case-upper", "case-key",
        "control-key", "duplicate-key", "wrong-cp311", "wrong-cp313", "pypy", "posix"])
def test_integrity_selector_rejects_closed_mixed_variant_and_wrong_runtime_bindings(defect):
    """The consumed FF ID and malformed fresh selectors cannot fall back to another lane."""
    values, platform = selector_values(), NT312
    case_key, control_key = invoker._FF_INPUTS
    if defect == "closed-ff":
        values[case_key] = CLOSED_FF_CASE
    elif defect == "mixed-h6-case":
        values["REVIEWER_V3_H6_CASE"] = "8788c0ac-3e50-4e99-8a0e-3e6767ad97d0"
    elif defect == "mixed-h6-control":
        values["REVIEWER_V3_H6_CONTROL_SHA256"] = "b" * 64
    elif defect == "case-value-upper":
        values[case_key] = CASE.upper()
    elif defect in {"case-key-lower", "control-key-lower"}:
        key = case_key if defect == "case-key-lower" else control_key
        values[key.lower()] = values.pop(key)
    elif defect == "duplicate-case-lower":
        values[case_key.lower()] = CASE
    else:
        platform = {"nt311": ("nt", "cpython", (3, 11)), "nt313": ("nt", "cpython", (3, 13)),
                    "pypy312": ("nt", "pypy", (3, 12)), "posix312": ("posix", "cpython", (3, 12))}[defect]
    with pytest.raises(RuntimeError, match="ff_configuration_binding_invalid"):
        invoker._ff_configuration(values, platform=platform)
