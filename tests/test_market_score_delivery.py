"""Market-cap limitations reach disk, HTTP and the shipped DOM without rescoring."""

import json

import pytest

from academic_agent.run_output import save_scores
from tests.test_result_detail_integrity import SCORES, display

FLAG = "high (2000× spread: 0.01–20 bn USD)"
CASES = [
    ({}, "unavailable"),
    ({"market_uncertainty": None}, "not_triggered"),
    ({"market_uncertainty": FLAG}, "triggered"),
    ({"market_uncertainty": "high (71× spread: 2.7–1.9e+02 bn USD)"}, "triggered"),
    *[({"market_uncertainty": value}, "unavailable") for value in
      ("", " ", "passed", True, 0, [], {}, FLAG + "\n", "high (3× spread: ...–20 bn USD)")],
]


@pytest.mark.parametrize("extra,signal", CASES)
@pytest.mark.parametrize("persist_scores", [True, False])
@pytest.mark.parametrize("language", ["English", "Simplified Chinese"])
def test_market_disclosure_crosses_persistence_http_and_dom(
    tmp_path, monkeypatch, extra, signal, persist_scores, language,
):
    """Null/missing/malformed signals and invented verification never mean agreement.

    The non-persistence path represents legacy artifacts (including bad/model
    metadata). The persistence path also asserts code authority and every old
    field's preservation. Neither path is allowed to rewrite historical files
    on GET or silently hide valid numeric neighbours.
    """
    payload = {**SCORES, **extra, "score_formula": "frozen formula",
               "market_rationale": "Market score is provisional.",
               "market_comparison": {"comparability_status": "verified", "legacy_cap_signal": "passed"}}
    text, rows = display(payload, "scores", tmp_path, monkeypatch, language, persist_scores=persist_scores)
    expected = {
        "English": {"triggered": "A legacy spread flag is recorded", "not_triggered": "No legacy spread flag is recorded",
                    "unavailable": "legacy spread record is missing or unreadable"},
        "Simplified Chinese": {"triggered": "记录中存在旧版金额差异标记", "not_triggered": "记录中没有旧版金额差异标记",
                               "unavailable": "旧版金额差异记录缺失或不可读"},
    }
    assert expected[language][signal] in text
    assert ("Market comparison: not assessed" if language == "English" else "市场估值可比性：未核实") in text
    assert any(row["cls"] == "notes scorecard__market-caveat" for row in rows)
    assert "65.0" in text and "3 / 5" in text
    assert FLAG not in text  # Its untyped amounts must not be rendered as USD truth.
    saved = json.loads(next(tmp_path.glob("*/commercialization_scores.json")).read_text(encoding="utf-8"))
    if persist_scores:
        disclosure = saved.pop("market_comparison")
        assert disclosure == {
            "version": "market-comparison-disclosure-v1",
            "comparability_status": "not_assessed", "legacy_cap_signal": signal,
            "score_policy": "legacy_cap_unchanged", "deduction_status": "not_reconstructable",
            "limitation": (
                "Same-definition market estimates were not verified. The legacy amount-spread "
                "flag does not establish currency, metric, year, geography, scope or method "
                "comparability. Its amounts are not verified USD estimates. Neither an absent "
                "flag nor a score at 3.5 proves agreement or an actual deduction."
            ),
        }
        assert saved == {k: v for k, v in payload.items() if k != "market_comparison"}
    else:
        assert saved == payload  # Read-only delivery must not migrate the archive.


def test_funding_false_comparison_keeps_calibration_but_discloses_limit(tmp_path, monkeypatch):
    """The actual production guardrail still caps mixed market/funding amounts.

    This deliberately records an open scoring-policy limitation instead of
    pretending that disclosure fixes it. The offline diagnostic is not called.
    """
    from academic_agent import market_metric_audit
    from academic_agent.scoring_contract import make_scoring_guardrail
    from tests.test_scoring_guardrail import _market_task, _run

    def forbidden(*_args, **_kwargs):
        raise AssertionError("offline diagnostic became production scoring")

    monkeypatch.setattr(market_metric_audit, "analyze_report", forbidden)
    task = _market_task("Market size is USD 20 billion in 2025.", "Company funding was USD 10 million in 2025.")
    ok, scores = _run(make_scoring_guardrail(market_task=task), market_accessibility=50)
    assert ok and scores["market_accessibility"] == 3.5
    text, _ = display(scores, "scores", tmp_path, monkeypatch, persist_scores=True)
    assert "3.5 / 5" in text and "not assessed" in text
    saved = json.loads(next(tmp_path.glob("*/commercialization_scores.json")).read_text(encoding="utf-8"))
    assert saved.pop("market_comparison")["deduction_status"] == "recorded"
    assert saved["market_cap_audit"]["pre_cap_score"] == 5
    assert saved["market_cap_audit"]["deduction"] == 1.5
    assert saved == scores


@pytest.mark.parametrize("raw", ['{"overall_score":65}', "[]", "null", '"wrong"', "{broken"])
def test_sparse_or_invalid_diagnostic_bytes_are_not_a_fake_score(tmp_path, raw):
    """Disclosure must not turn diagnostic objects into repaired scorecards."""
    assert save_scores(raw, "fixture", tmp_path).read_text(encoding="utf-8") == raw


def test_restored_score_disclosure_is_reasserted_and_idempotent(tmp_path):
    """Restored node metadata cannot bypass today's code-owned limitation."""
    raw = json.dumps({**SCORES, "market_uncertainty": None, "market_comparison": "verified"})
    first = save_scores(raw, "fresh", tmp_path).read_text(encoding="utf-8")
    restored = save_scores(first, "restored", tmp_path).read_text(encoding="utf-8")
    assert restored == first
    assert json.loads(restored)["market_comparison"]["comparability_status"] == "not_assessed"
