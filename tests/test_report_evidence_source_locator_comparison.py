"""The fixed public title-search observer must fail closed, not fabricate emptiness."""

from __future__ import annotations

from copy import deepcopy
import json
import subprocess

import pytest

from academic_agent import report_evidence_source_locator_comparison as comparison


@pytest.fixture(scope="module")
def node_observation():
    """All corrupted boundary controls start from actual unchanged Node output."""
    return comparison._run_node(comparison.prepare_manifest())


def _assert_unavailable(result):
    assert result["state"] == "unavailable"
    assert result["planned_cases"] == result["unavailable_cases"] == 6
    assert result["positive_reference_cases"] == 5 and result["no_fit_cases"] == 1
    assert result["observed_cases"] == result["paired_observations_observed"] == 0
    assert result["paired_observations_planned"] == 12
    assert result["model_lane"] == {"state": "not_run", "evaluated_cases": 0, "quality": None, "benefit": None}
    for condition, counts in result["condition_counts"].items():
        assert counts == {"planned_cases": 6, "observed_cases": 0, "unavailable_cases": 6,
                          "positive_reference_cases": 5, "no_fit_cases": 1,
                          "evaluable_positive_cases": 0, "evaluable_no_fit_cases": 0}
        for row in result["conditions"][condition]:
            for field in ("observed_ids", "candidate_count", "acceptable_intersection", "reference_coverage",
                          "unique_acceptable_hit", "no_fit_control_match"):
                assert row[field] is None


def test_fixed_comparison_uses_real_node_and_reports_six_paired_cases(monkeypatch):
    """A green observer must deliver all five positives, not merely the no-fit row."""
    native_run = comparison.subprocess.run
    calls = []

    def observe_call(args, **kwargs):
        calls.append((args, kwargs))
        return native_run(args, **kwargs)

    monkeypatch.setattr(comparison.subprocess, "run", observe_call)
    result = comparison.run_fixed_comparison()
    assert result["state"] == "available"
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == [comparison.shutil.which("node"), str(comparison.CONTRACT)]
    assert kwargs.keys() == {"input", "text", "encoding", "capture_output", "timeout", "check"}
    assert kwargs["text"] is kwargs["capture_output"] is kwargs["check"] is True
    assert kwargs["encoding"] == "utf-8" and kwargs["timeout"] == 30
    sent = json.loads(kwargs["input"])
    manifest = comparison.prepare_manifest()
    assert sent == {
        "root": str(comparison.ROOT), "payload": comparison._payload(manifest["catalog"]), "report": "",
        "actions": [action for case in manifest["cases"] for action in (
            {"search": case["question"]}, {"search": case["keyword_query"]},
        )],
    }
    assert all(set(row) == {"source_id", "title"} for group in sent["payload"].values() for row in group)
    assert result["planned_cases"] == result["observed_cases"] == 6
    assert result["unavailable_cases"] == 0
    assert result["paired_observations_planned"] == result["paired_observations_observed"] == 12
    for counts in result["condition_counts"].values():
        assert counts == {"planned_cases": 6, "observed_cases": 6, "unavailable_cases": 0,
                          "positive_reference_cases": 5, "no_fit_cases": 1,
                          "evaluable_positive_cases": 5, "evaluable_no_fit_cases": 1}
    assert result["asset_hashes_before"] == result["asset_hashes_after"] == dict(comparison.ASSETS)
    assert result["input_provenance"] == {
        "fixture_sha256": comparison.FIXTURE_SHA256,
        **{key: manifest["fixture"][key] for key in (
            "source_report", "source_report_sha256_lf", "catalog_origin", "saved_text_status",
            "keyword_origin", "reference_status",
        )},
    }
    assert result["model_lane"] == {"state": "not_run", "evaluated_cases": 0, "quality": None, "benefit": None}
    diagnostic = result["conditions"]["question_literal_diagnostic"]
    keywords = result["conditions"]["prepared_keyword_assisted"]
    assert [row["case_id"] for row in keywords] == [f"SLC0{i}" for i in range(1, 7)]
    assert [row["observed_ids"] for row in diagnostic] == [[]] * 6
    assert [row["candidate_count"] for row in diagnostic] == [0] * 6
    assert [row["reference_coverage"] for row in diagnostic] == [0] * 5 + [None]
    assert [row["observed_ids"] for row in keywords] == [["A2"], ["A4"], ["P7"], ["P5", "P8"], ["M1"], []]
    assert [row["acceptable_intersection"] for row in keywords] == [["A2"], ["A4"], ["P7"], ["P5", "P8"], ["M1"], []]
    assert [row["candidate_count"] for row in keywords] == [1, 1, 1, 2, 1, 0]
    assert [row["reference_coverage"] for row in keywords] == [1] * 5 + [None]
    assert [row["unique_acceptable_hit"] for row in keywords] == [True, True, True, False, True, False]
    for condition in (diagnostic, keywords):
        assert [row["no_fit_control_match"] for row in condition] == [None] * 5 + [True]
    assert keywords[-1]["reference_coverage"] is None


def test_observer_failure_cannot_become_an_observed_empty_result(monkeypatch):
    """An absent observer sequence must not produce six fabricated zero-hit facts."""
    monkeypatch.setattr(comparison, "_run_node", lambda _manifest: {"states": []})
    result = comparison.run_fixed_comparison()
    _assert_unavailable(result)
    assert all(len(condition) == 6 for condition in result["conditions"].values())


def test_partial_initial_delivery_is_not_complete(monkeypatch, node_observation):
    """The initial twenty-row delivery cannot be inferred from later filter hits."""
    partial = deepcopy(node_observation)
    partial["states"][0]["rows"].pop()
    monkeypatch.setattr(comparison, "_run_node", lambda _manifest: partial)
    result = comparison.run_fixed_comparison()
    assert result["state"] == "unavailable" and result["reason"] == "initial_delivery_incomplete"
    _assert_unavailable(result)


def test_two_acceptable_hits_are_valid_coverage_not_wrong():
    """Two acceptable candidates have full set coverage without forced uniqueness."""
    case = comparison.prepare_manifest()["cases"][3]
    grade = comparison._grade([case], [["P5", "P8"]])[0]
    assert grade["acceptable_intersection"] == ["P5", "P8"]
    assert grade["reference_coverage"] == 1
    assert grade["unique_acceptable_hit"] is False
    assert grade["no_fit_control_match"] is None


def test_one_acceptable_hit_has_half_coverage_not_failure():
    """One of two acceptable titles is useful location, not an incorrect answer."""
    case = comparison.prepare_manifest()["cases"][3]
    grade = comparison._grade([case], [["P5"]])[0]
    assert grade["acceptable_intersection"] == ["P5"]
    assert grade["reference_coverage"] == 0.5
    assert grade["candidate_count"] == 1 and grade["unique_acceptable_hit"] is True
    assert grade["no_fit_control_match"] is None


def test_no_fit_control_is_separate_from_positive_empty_results():
    """Zero observed hits is not unavailable, and only the no-fit control is graded as such."""
    cases = comparison.prepare_manifest()["cases"]
    positive = comparison._grade([cases[0]], [[]])[0]
    assert positive["observed_ids"] == [] and positive["candidate_count"] == 0
    assert positive["reference_coverage"] == 0 and positive["no_fit_control_match"] is None
    no_fit = comparison._grade([cases[-1]], [["A1"]])[0]
    assert no_fit["reference_coverage"] is None and no_fit["no_fit_control_match"] is False


@pytest.mark.parametrize("state_index", [0, 2, 12])
@pytest.mark.parametrize("path,value", [
    ((), None), ((), []), (("rows",), None), (("rows",), [None]),
    (("search",), None), (("search",), []), (("search", "value"), "wrong query"),
    (("search", "disabled"), True), (("search", "disabled"), 0),
    (("search", "focused"), 0), (("clear",), None),
    (("prev",), None), (("next",), None), (("prev", "disabled"), False),
    (("next", "disabled"), False), (("next", "disabled"), 1),
    (("status",), []), (("status",), ["Matching saved records: 0 / 0 locally browsable records. Showing 0–0."]),
    (("warnings",), ["partial"]), (("errors",), ["unreadable"]), (("missing",), ["missing"]),
    (("notes",), ["unexpected note"]), (("disclosure",), []),
    (("source_html_writes",), ["<b>injected</b>"]), (("forbidden_tags",), ["script"]),
    (("active_tab",), "report"), (("report_html",), "unexpected report"), (("requests",), []),
])
def test_malformed_state_returns_unavailable_not_raw_exception(monkeypatch, node_observation, state_index, path, value):
    """Initial, positive and zero-hit states require the same exact observer controls."""
    observed = deepcopy(node_observation)
    parent, key = observed["states"], state_index
    for field in path:
        parent, key = parent[key], field
    parent[key] = value
    monkeypatch.setattr(comparison, "_run_node", lambda _manifest: observed)
    result = comparison.run_fixed_comparison()
    _assert_unavailable(result)
    assert result["reason"] == ("initial_delivery_incomplete" if state_index == 0 else "filter_observation_incomplete")


@pytest.mark.parametrize("state_index", [0, 2])
@pytest.mark.parametrize("field,value", [
    ("id", "HIDDEN"), ("id", None), ("id", []), ("title", "fabricated title"),
    ("link", None), ("link", {"tag": "a", "href": "https://example.invalid", "rel": None, "target": None}),
    ("excerpt_tag", None), ("summary_tag", "div"), ("excerpts", ["fabricated text"]),
    ("excerpts", [""]), ("excerpt_children", [1]), ("excerpt_state", []),
    ("summary_source", ["abstract"]), ("faults", ["unreadable"]), ("meta", ["invented publisher"]),
    ("unexpected_field", "invented metadata"),
])
def test_title_only_row_contract_rejects_fabrication(monkeypatch, node_observation, state_index, field, value):
    """Rows cannot import unobserved saved text, links, metadata or unknown source identity."""
    observed = deepcopy(node_observation)
    observed["states"][state_index]["rows"][0][field] = value
    monkeypatch.setattr(comparison, "_run_node", lambda _manifest: observed)
    _assert_unavailable(comparison.run_fixed_comparison())


@pytest.mark.parametrize("change", ["cleared", "duplicate", "reordered", "partial_status_consistent"])
def test_row_counts_identity_and_order_must_agree(monkeypatch, node_observation, change):
    """A nonzero status cannot certify absent rows, nor may a partial initial catalog pass."""
    observed = deepcopy(node_observation)
    state = observed["states"][0 if change == "partial_status_consistent" else 8]
    if change == "cleared":
        state["rows"] = []
    elif change == "duplicate":
        state["rows"][1] = deepcopy(state["rows"][0])
    elif change == "reordered":
        state["rows"].reverse()
    else:
        state["rows"].pop()
        state["status"] = ["Matching saved records: 19 / 20 locally browsable records. Showing 1–19."]
    monkeypatch.setattr(comparison, "_run_node", lambda _manifest: observed)
    _assert_unavailable(comparison.run_fixed_comparison())


@pytest.mark.parametrize("field,value", [
    ("states", None), ("states", []), ("requests", []),
    ("storage_writes", [["unexpected", "write"]]), ("logs", [["unexpected", "log"]]),
])
def test_observation_envelope_must_be_complete(monkeypatch, node_observation, field, value):
    """No filter result survives an incomplete sequence or unexpected endpoint/side effect."""
    observed = deepcopy(node_observation)
    observed[field] = value
    monkeypatch.setattr(comparison, "_run_node", lambda _manifest: observed)
    _assert_unavailable(comparison.run_fixed_comparison())


def test_post_observation_asset_drift_discards_hits(monkeypatch):
    """Pre-dispatch asset binding alone cannot certify the observer after execution."""
    hashes = comparison._asset_hashes
    reads = 0

    def drift_after_observation():
        nonlocal reads
        reads += 1
        return hashes() if reads == 1 else {}

    monkeypatch.setattr(comparison, "_asset_hashes", drift_after_observation)
    result = comparison.run_fixed_comparison()
    _assert_unavailable(result)
    assert reads == 2 and result["reason"] == "observer_asset_drift"


@pytest.mark.parametrize("failure", ["node", "asset", "timeout", "process", "os", "decode", "json", "shape"])
def test_cli_observer_failures_are_safe_json_not_zero_hits(monkeypatch, capsys, failure):
    """Raw subprocess output, paths and exception chains must never escape the fixed JSON CLI."""
    sentinel = "PRIVATE_DIAGNOSTIC_SENTINEL"
    if failure == "node":
        monkeypatch.setattr(comparison.shutil, "which", lambda _name: None)
    elif failure == "asset":
        def unreadable(_path):
            raise OSError(sentinel)
        monkeypatch.setattr(comparison.Path, "read_bytes", unreadable)
    else:
        def failed_run(*_args, **_kwargs):
            if failure == "timeout":
                raise subprocess.TimeoutExpired(sentinel, 30, output=sentinel, stderr=sentinel)
            if failure == "process":
                raise subprocess.CalledProcessError(1, sentinel, output=sentinel, stderr=sentinel)
            if failure == "os":
                raise OSError(sentinel)
            if failure == "decode":
                raise UnicodeError(sentinel)
            return subprocess.CompletedProcess([], 0, stdout=sentinel if failure == "json" else "null")
        monkeypatch.setattr(comparison.subprocess, "run", failed_run)
    monkeypatch.setattr(comparison.sys, "argv", ["comparison"])
    comparison.main()
    captured = capsys.readouterr()
    assert captured.err == "" and sentinel not in captured.out
    result = json.loads(captured.out)
    _assert_unavailable(result)
    assert result["reason"] == {"node": "node_unavailable", "asset": "asset_unavailable",
                               "shape": "observer_parse_mismatch"}.get(failure, "observer_unavailable")


def test_cli_success_is_json_with_real_node(capsys, monkeypatch):
    """The actual module CLI exposes the observed positive sequence and title-only provenance."""
    monkeypatch.setattr(comparison.sys, "argv", ["comparison"])
    comparison.main()
    captured = capsys.readouterr()
    assert captured.err == ""
    result = json.loads(captured.out)
    assert result["state"] == "available"
    assert [row["observed_ids"] for row in result["conditions"]["prepared_keyword_assisted"]] == [
        ["A2"], ["A4"], ["P7"], ["P5", "P8"], ["M1"], [],
    ]
    assert result["input_provenance"]["saved_text_status"] == "unavailable_in_public_input"
