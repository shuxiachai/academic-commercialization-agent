"""Typed offline comparisons must never masquerade as a scoring repair."""

from copy import deepcopy
import hashlib
import json
import subprocess
import sys

import pytest

from academic_agent import market_metric_audit as audit


def report(*claims):
    return {
        "topic": "batteries",
        "findings": [{"claim": text, "source_ids": [f"M{i}"]} for i, text in enumerate(claims, 1)],
        "sources": [{"source_id": f"M{i}", "evidence_summary": "Public source abstract."}
                    for i in range(1, len(claims) + 1)],
    }


LOW = "The global battery market is valued at USD 2 billion in 2025."
HIGH = "The global battery market is valued at USD 20 billion in 2025."


def test_market_and_funding_reproducer_never_becomes_a_comparable_spread():
    """The old 2000x signal is real; calling its two metrics inconsistent is not."""
    value = audit.analyze_report(report(HIGH, "The company raised USD 10 million in 2025."))
    assert value["legacy_untyped"] == {"positive_occurrences": 2, "ratio": "2000.0", "above_five": True}
    assert value["metric_counts"] == {"funding": 1, "market_size": 1}
    assert value["comparison"]["verdict"] == "not_assessed"
    assert value["comparison"]["pairs"] == []
    assert value["production_effect"] == "none"


@pytest.mark.parametrize("other,reason", [
    (HIGH.replace("USD", "EUR"), "currency"),
    (HIGH.replace("2025", "2035"), "year"),
    (HIGH.replace("global", "China"), "geography"),
    (HIGH.replace("battery", "EV battery"), "market_scope"),
])
def test_known_different_denominators_are_not_compared(other, reason):
    value = audit.analyze_report(report(LOW, other))
    assert value["comparison"]["eligible_occurrences"] == 2
    assert value["comparison"]["verdict"] == "not_assessed"
    assert value["comparison"]["skipped_pair_reasons"][reason] == 1


@pytest.mark.parametrize("low,high,reason", [
    (LOW.replace("USD", "$"), HIGH.replace("USD", "$"), "currency_unknown_or_conflicting"),
    (LOW.replace("global ", ""), HIGH.replace("global ", ""), "geography_unknown_or_multiple"),
    (LOW.replace(" in 2025", ""), HIGH.replace(" in 2025", ""), "period_unknown_or_multiple"),
    (LOW + " Forecast grows in 2035.", HIGH, "period_unknown_or_multiple"),
    (LOW.replace("2025", "Q1 2025"), HIGH, "period_unknown_or_multiple"),
    (LOW.replace("2025", "January 2025"), HIGH, "period_unknown_or_multiple"),
    (LOW.replace("2025", "2025-26"), HIGH, "period_unknown_or_multiple"),
    (LOW + " North America leads.", HIGH, "geography_unknown_or_multiple"),
    (LOW + " The company raised USD 10 million.", HIGH, "metric_unknown_or_mixed"),
    (LOW.replace("valued at", "funded with"), HIGH, "metric_unknown_or_mixed"),
    (LOW.replace("USD 2 billion", "USD 2 billion EUR"), HIGH, "currency_unknown_or_conflicting"),
])
def test_unknown_or_mixed_dimensions_cannot_match_each_other(low, high, reason):
    """None==None and shared report topics must not become evidence of sameness."""
    value = audit.analyze_report(report(low, high))
    assert value["comparison"]["verdict"] == "not_assessed"
    assert reason in value["observations"][0]["reasons"]


@pytest.mark.parametrize("text,metric", [
    ("The firm received US$145 million funding.", "funding"),
    ("The firm invested EUR 3 billion.", "funding"),
    ("Acquisition of a company for USD 74 billion.", "acquisition"),
    ("Company revenue was USD 5 billion.", "revenue"),
    ("Factory costs were USD 40 million.", "cost"),
    ("Its valuation was USD 40 billion.", "valuation"),
    ("Captured 2 million metric tons of CO2.", "non_monetary"),
    ("Screened 100 million molecules.", "non_monetary"),
    ("The market includes 2 million vehicles.", "non_monetary"),
    ("It reached 40 million.", "unknown"),
])
def test_named_non_market_quantities_are_excluded_but_keep_provenance(text, metric):
    value = audit.analyze_report(report(text))
    row = value["observations"][0]
    assert row["metric"] == metric
    assert not row["eligible"]
    assert text[row["start"]:row["end"]] == row["raw"]
    assert row["path"] == "findings[0].claim"
    assert value["comparison"]["verdict"] == "not_assessed"


@pytest.mark.parametrize("currency,expected", [("USD", "USD"), ("US $", "USD"), ("EUR", "EUR"),
                                              ("GBP", "GBP"), ("C$", "CAD"), ("AUD", "AUD"),
                                              ("RMB", "CNY"), ("JPY", "JPY")])
def test_explicit_currency_survives_the_actual_pair_result(currency, expected):
    value = audit.analyze_report(report(LOW.replace("USD", currency), HIGH.replace("USD", currency)))
    assert value["observations"][0]["currency"] == expected
    assert value["comparison"]["pairs"] == [{"left": 0, "right": 1, "ratio": "10", "above_five": True}]
    assert value["comparison"]["verdict"] == "spread_candidate"


@pytest.mark.parametrize("amount,above", [("10 billion", False), ("10.01 billion", True), ("2,000 million", False)])
def test_exact_decimal_threshold_and_scale_only_apply_to_comparable_pairs(amount, above):
    value = audit.analyze_report(report(LOW, HIGH.replace("20 billion", amount)))
    assert value["comparison"]["pairs"][0]["above_five"] == above
    assert value["comparison"]["verdict"] == ("spread_candidate" if above else "no_spread_in_checked_pairs")


@pytest.mark.parametrize("amount", ["0 billion", "-2 billion", "−2 billion", "+2 billion"])
def test_legacy_unsigned_grammar_does_not_make_signed_amounts_eligible(amount):
    value = audit.analyze_report(report(LOW.replace("2 billion", amount), HIGH))
    assert "nonpositive_or_range_or_signed_amount" in value["observations"][0]["reasons"]
    assert value["comparison"]["verdict"] == "not_assessed"


def test_source_summary_and_limitations_are_not_independent_estimates():
    data = report(LOW)
    data["findings"][0]["limitations"] = HIGH
    data["sources"][0]["evidence_summary"] = HIGH
    value = audit.analyze_report(data)
    assert value["legacy_untyped"]["above_five"]
    assert value["comparison"]["eligible_occurrences"] == 1
    assert value["comparison"]["pairs"] == []
    assert value["comparison"]["excluded_occurrences"] == 2


@pytest.mark.parametrize("text,reason", [
    (LOW.replace("USD 2", "over USD 2"), "bound_not_point_estimate"),
    (LOW.replace("USD 2", "up to USD 2"), "bound_not_point_estimate"),
    (LOW.replace("2 billion", "2 billion to USD 4 billion"), "multiple_amounts_unattributed"),
])
def test_bounds_and_unattributed_multiple_amounts_are_not_point_estimates(text, reason):
    value = audit.analyze_report(report(text, HIGH))
    assert value["comparison"]["verdict"] == "not_assessed"
    assert reason in value["observations"][0]["reasons"]


@pytest.mark.parametrize("ids", [["M1"], ["M999"], ["M1", "M2"], []])
def test_same_unregistered_or_multi_source_claim_cannot_supply_a_second_vote(ids):
    data = report(LOW, HIGH)
    data["findings"][1]["source_ids"] = ids
    assert audit.analyze_report(data)["comparison"]["verdict"] == "not_assessed"


def test_duplicate_quotations_do_not_inflate_pair_count():
    data = report(LOW, HIGH)
    data["findings"].append(deepcopy(data["findings"][0]))
    data["findings"][-1]["claim"] = LOW.replace("2 billion", "2.00 billion")
    value = audit.analyze_report(data)
    assert value["legacy_untyped"]["positive_occurrences"] == 3
    assert len(value["comparison"]["pairs"]) == 1


def test_unrecognised_language_and_amount_format_is_unassessed_not_agreement():
    value = audit.analyze_report(report("市场规模是200亿美元，公司融资1000万美元。"))
    assert value["legacy_untyped"]["positive_occurrences"] == 0
    assert value["comparison"]["verdict"] == "not_assessed"


def test_legacy_extraction_replay_is_exact_without_loading_a_provider():
    """Test the old/new extraction seam, not two copies of the same regex."""
    from academic_agent.evidence import _extract_market_size_billions
    from tests.test_scoring_guardrail import _market_task

    task = _market_task(HIGH, "Funding of USD 10 million. Captured 100 million tonnes.",
                        "Values span 2 bn to 5 billion with 3 mn, 78.6 million and 0 million.")
    original = task.output.pydantic.model_dump()
    value = audit.analyze_report(original)
    expected = _extract_market_size_billions(task)
    actual = [audit._legacy_value(row) for row in value["observations"] if audit._legacy_value(row) > 0]
    assert sorted(actual) == sorted(expected)
    assert value["legacy_untyped"]["ratio"] == str(max(expected) / min(expected))
    assert original == task.output.pydantic.model_dump()


def test_diagnostic_cannot_change_production_guardrail_or_frozen_scores(monkeypatch):
    """Observe the production scoring call while the diagnostic is unusable."""
    from academic_agent.evidence import make_scoring_guardrail as legacy
    from academic_agent.scoring_contract import make_scoring_guardrail as current
    from tests.test_scoring_guardrail import _market_task, _run

    task = _market_task(HIGH, "The company raised USD 10 million in 2025.")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("offline diagnostic reached production")

    monkeypatch.setattr(audit, "analyze_report", forbidden)
    before = _run(legacy(market_task=task), market_accessibility=50)
    after = _run(current(market_task=task), market_accessibility=50)
    # The current wrapper adds a pre/post arithmetic receipt; every original
    # field (not only numeric scores) must still equal the frozen factory.
    assert before == (after[0], {k: v for k, v in after[1].items() if k != "market_cap_audit"})
    assert after[1]["market_cap_audit"]["pre_cap_score"] == 5
    assert after[1]["market_cap_audit"]["deduction"] == 1.5
    assert after[0] and after[1]["market_accessibility"] == 3.5


def write_unit(root, name="unit", *, mode="live", score=3.5):
    unit = root / name
    unit.mkdir(parents=True)
    (unit / "market_evidence.json").write_text(json.dumps(report(LOW, HIGH)), encoding="utf-8")
    (unit / "meta.json").write_text(json.dumps({"evidence_mode": mode, "num": "01", "rep": 1}), encoding="utf-8")
    (unit / "commercialization_scores.json").write_text(json.dumps({"market_accessibility": score}), encoding="utf-8")
    return unit


def run_cli(root, output):
    return subprocess.run([sys.executable, "-m", "academic_agent.market_metric_audit", "--input", str(root),
                           "--output", str(output)], capture_output=True, text=True, timeout=20, check=False)


def test_cli_delivers_manifest_counts_and_unknown_cap_effect_without_rewriting_inputs(tmp_path):
    """A computed diagnostic must reach its exported JSON, not just stdout."""
    root, output = tmp_path / "inputs", tmp_path / "result"
    write_unit(root)
    write_unit(root, "second", mode="fixture")
    (root / "benchmark_summary.csv").write_text("case_num,rep,evidence_mode\n01,1,live\n", encoding="utf-8")
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    process = run_cli(root, output)
    assert process.returncode == 0, process.stderr
    result = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    assert json.loads(process.stdout) == result["summary"]
    assert result["summary"]["meta_modes"] == {"fixture": 1, "live": 1}
    assert result["archived_csv_modes"] == {"live": 1}
    assert result["archived_csv_mode_mismatches"] == ["second"]
    assert result["historical_identity"] == "not_established_by_matching_csv_labels"
    assert result["summary"]["verdicts"] == {"spread_candidate": 2}
    assert result["execution"] == "offline_only" and result["production_effect"] == "none"
    for row in result["units"]:
        for name, digest in row["input_sha256"].items():
            assert digest == hashlib.sha256(before[root / row["unit"] / name]).hexdigest()
        assert row["score"]["cap_effect"] == "not_reconstructable_without_pre_cap_score"
        assert row["audit"]["comparison"]["pairs"][0]["above_five"]
    assert result["archived_csv_sha256"] == hashlib.sha256(before[root / "benchmark_summary.csv"]).hexdigest()
    assert before == {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert str(tmp_path) not in (output / "audit.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("defect", ["missing", "corrupt", "shape", "bad_source", "text", "too_large"])
def test_incomplete_unit_stays_in_cli_denominator_and_returns_nonzero(tmp_path, defect):
    root, output = tmp_path / "inputs", tmp_path / "result"
    unit = write_unit(root)
    path = unit / "market_evidence.json"
    if defect == "missing":
        path.unlink()
    elif defect == "corrupt":
        path.write_text("PRIVATE-BROKEN-CONTENT", encoding="utf-8")
    elif defect == "shape":
        path.write_text("[]", encoding="utf-8")
    elif defect in {"bad_source", "text"}:
        data = report(LOW)
        if defect == "bad_source":
            data["sources"].append(deepcopy(data["sources"][0]))
        else:
            data["findings"][0]["claim"] = None
        path.write_text(json.dumps(data), encoding="utf-8")
    else:
        path.write_bytes(b"x" * (audit._MAX_BYTES + 1))
    process = run_cli(root, output)
    assert process.returncode == 2
    text = (output / "audit.json").read_text(encoding="utf-8")
    value = json.loads(text)
    assert value["summary"]["units"] == value["summary"]["unavailable"] == 1
    assert value["summary"]["verdicts"] == {}
    assert "PRIVATE-BROKEN-CONTENT" not in text + process.stdout + process.stderr


def test_empty_input_is_not_a_successful_audit(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    result = run_cli(root, tmp_path / "result")
    assert result.returncode == 2
    assert json.loads(result.stdout)["units"] == 0


@pytest.mark.parametrize("target", ["existing", "inside_input", "same_input", "missing_input"])
def test_cli_refuses_overwrite_and_input_mutation(tmp_path, target):
    root, output = tmp_path / "inputs", tmp_path / "result"
    write_unit(root)
    if target == "existing":
        output.mkdir()
        (output / "audit.json").write_text("keep", encoding="utf-8")
    elif target == "inside_input":
        output = root / "new"
    elif target == "same_input":
        output = root
    else:
        root = tmp_path / "absent"
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    process = run_cli(root, output)
    assert process.returncode == 2
    assert json.loads(process.stdout)["status"] == "unavailable"
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("saved", [None, "3.5", True, float("nan"), float("inf"), 0, 50])
def test_malformed_saved_score_does_not_become_a_zero_or_an_estimated_penalty(tmp_path, saved):
    root = tmp_path / "inputs"
    write_unit(root, score=saved)
    value = audit.audit_directory(root)
    assert value["summary"]["score_states"] == {"unavailable": 1}
    assert value["units"][0]["score"]["market_accessibility"] is None


def test_missing_metadata_and_scores_are_separate_from_successful_text_inspection(tmp_path):
    unit = write_unit(tmp_path / "inputs")
    (unit / "meta.json").unlink()
    (unit / "commercialization_scores.json").unlink()
    value = audit.audit_directory(unit.parent)
    assert value["summary"]["available"] == 1
    assert value["summary"]["meta_modes"] == {"unavailable": 1}
    assert value["summary"]["score_states"] == {"unavailable": 1}
