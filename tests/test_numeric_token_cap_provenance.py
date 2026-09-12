"""Full quantity tokens and actual cap receipts must survive delivery and reuse."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from crewai import TaskOutput

from academic_agent.claim_grounding import check_report
from academic_agent.evidence import make_scoring_guardrail as legacy
from academic_agent.market_cap_audit import readable_cap
from academic_agent.run_output import save_claim_grounding, save_scores
from academic_agent.scoring_contract import make_scoring_guardrail
from tests.test_checkpoint_runtime import (
    _evidence_report, _fake_tasks, _runtime, _seed_validated_prefix,
)
from tests.test_result_detail_integrity import display
from tests.test_scoring_guardrail import _market_task, _run, _score_payload


QUANTITIES = [
    ("3%", "1e-3%", "ungrounded"),
    ("3%", "1e+3%", "ungrounded"),
    ("1e-3%", "3%", "ungrounded"),
    ("1e+3%", "3%", "ungrounded"),
    ("0.001%", "1e-3%", "grounded"),
    ("1e-3%", "0.001%", "grounded"),
    ("1000%", "1E+3 percent", "grounded"),
    ("1e+3%", "1000%", "grounded"),
    ("− 10.5%", "10.5%", "ungrounded"),
    ("10.5%", "− 10.5%", "ungrounded"),
    ("- 10.5%", "+ 10.5%", "ungrounded"),
    ("− 10.5%", "-10.50 percent", "grounded"),
    ("+ 10.5%", "10.5%", "grounded"),
    (".5%", "0.5%", "grounded"),
    ("-.5%", "0.5%", "ungrounded"),
    ("26.1 kg", "26.1 kg / m2", "unverifiable"),
    ("26.1 kg / m2", "26.1 kg", "unverifiable"),
    ("26.1 kg / m2", "26.1 kg / m2", "unverifiable"),
    ("26.1 kg ^ 2", "26.1 kg", "unverifiable"),
    ("26.1 kg · m", "26.1 kg", "unverifiable"),
    ("26.1 kg * m", "26.1 kg", "unverifiable"),
    ("26.1 Wh / kg", "26.1 Wh/kg", "grounded"),
    ("26.1 Wh/kg", "26.1 Wh / kg", "grounded"),
    ("1000 MW", "1e3 mW", "ungrounded"),
    ("1e3 MW", "1000 MW", "grounded"),
    ("1e10000%", "1e10000%", "unverifiable"),
    ("3%", "1e--3%", "unverifiable"),
    ("1e--3%", "3%", "unverifiable"),
    ("3%", "1e3.5%", "unverifiable"),
    ("3%", "1 × 10^-3%", "unverifiable"),
    ("1 × 10^-3%", "3%", "unverifiable"),
    ("1000%", "1.e3%", "grounded"),
    ("26.1 kg", "26.1 kg m^-2", "unverifiable"),
    ("1-3%", "3%", "unverifiable"),
]


@pytest.mark.parametrize("claim,source,status", QUANTITIES)
def test_whole_quantity_verdict_reaches_disk_http_and_client(tmp_path, monkeypatch, claim, source, status):
    """Do not pass by splitting an exponent/sign/unit; keep valid equivalents."""
    report = _evidence_report("A")
    report.findings = [report.findings[0]]
    report.sources = [report.sources[0]]
    report.findings[0].claim = "The measured quantity was " + claim
    report.sources[0].evidence_summary = "The measured quantity was " + source + ". " + "Supporting prose. " * 40
    report.sources[0].summary_source = "abstract"
    result = check_report(report)
    assert result.error is None
    assert len(result.checks) == 1 and result.checks[0].status == status
    summary = save_claim_grounding([SimpleNamespace(raw=report.model_dump_json())], "audit", tmp_path)
    saved = json.loads((tmp_path / "audit/claim_grounding.json").read_text(encoding="utf-8"))
    assert summary["checked"] == (status != "unverifiable")
    assert saved["ungrounded"] == (status == "ungrounded")
    assert saved["unverifiable"] == (status == "unverifiable")
    text, rows = display(saved, "grounding", tmp_path, monkeypatch)
    assert "no conclusion" not in text
    if status == "grounded":
        assert saved["findings"] == []
    else:
        assert saved["findings"][0]["status"] == status
        assert any(report.findings[0].claim in row["text"] for row in rows)


@pytest.mark.parametrize("original", [10, 30, 35, 36, 40, 50])
@pytest.mark.parametrize("triggered", [True, False])
@pytest.mark.parametrize("language", ["English", "Simplified Chinese"])
def test_real_guardrail_cap_receipt_preserves_all_legacy_fields_and_reaches_client(
    tmp_path, monkeypatch, original, triggered, language,
):
    """A triggered rule is not an actual deduction when the score is <=3.5."""
    task = _market_task("Market size USD 20 billion.", "Company funding USD 10 million.") if triggered else None
    expected_ok, expected = _run(legacy(market_task=task), market_accessibility=original)
    ok, current = _run(make_scoring_guardrail(market_task=task), market_accessibility=original,
                       market_cap_audit={"version": "invented", "deduction": 0})
    assert ok and expected_ok
    assert "market_cap_audit" in current
    assert {k: v for k, v in current.items() if k != "market_cap_audit"} == expected
    before = original / 10
    after = min(before, 3.5) if triggered else before
    receipt = current["market_cap_audit"]
    assert receipt == {
        "version": "legacy-market-cap-audit-v1",
        "pre_cap_score": before, "post_cap_score": after, "cap": 3.5,
        "triggered": triggered, "applied": after < before,
        "deduction": round(before - after, 1),
        "reason": "legacy_untyped_spread_gt_5" if triggered else "legacy_cap_not_triggered",
    }
    assert readable_cap(current) == receipt
    text, rows = display(current, "scores", tmp_path, monkeypatch, language, persist_scores=True)
    assert any(row["cls"] == "scorecard__cap-receipt" for row in rows)
    assert f"{before:g} → {after:g} / 5" in text
    assert ("not assessed" if language == "English" else "未核实") in text
    saved = json.loads(next(tmp_path.glob("*/commercialization_scores.json")).read_text(encoding="utf-8"))
    assert saved["market_cap_audit"] == receipt
    assert saved["market_comparison"]["deduction_status"] == "recorded"


@pytest.mark.parametrize("field,bad", [
    ("version", "invented"), ("pre_cap_score", None), ("pre_cap_score", True),
    ("pre_cap_score", "5"), ("pre_cap_score", 6), ("post_cap_score", 3),
    ("triggered", 1), ("triggered", False), ("applied", False), ("applied", "true"),
    ("deduction", None), ("deduction", True), ("deduction", 0), ("cap", 4),
    ("reason", "verified_same_definition"),
])
def test_bad_cap_metadata_remains_unknown_without_hiding_score(tmp_path, monkeypatch, field, bad):
    """Malformed receipts must not claim zero deduction or source agreement."""
    task = _market_task("Market USD 20 billion.", "Funding USD 10 million.")
    ok, scores = _run(make_scoring_guardrail(market_task=task), market_accessibility=50)
    assert ok
    scores["market_cap_audit"][field] = bad
    assert readable_cap(scores) is None
    text, rows = display(scores, "scores", tmp_path, monkeypatch, persist_scores=True)
    assert not any(row["cls"] == "scorecard__cap-receipt" for row in rows)
    assert "cannot be reconstructed" in text and "3.5 / 5" in text
    saved = json.loads(next(tmp_path.glob("*/commercialization_scores.json")).read_text(encoding="utf-8"))
    assert saved["market_comparison"]["deduction_status"] == "not_reconstructable"


def test_validated_receipt_survives_real_checkpoint_restore_then_delivery(tmp_path, monkeypatch):
    """Reused scorer raw bytes retain the observed original score, not a guess."""
    parent = tmp_path / "parent"
    source, digest = _seed_validated_prefix(parent, count=5)
    tasks = _fake_tasks()
    runtime = _runtime(parent, tasks=tasks, source=source, retrieval_sha256=digest, resume_directory=parent)
    assert runtime.restore_contiguous_prefix() == 5
    output = TaskOutput(description="score", agent="scorer", raw=json.dumps(_score_payload(market_accessibility=50)))
    task = _market_task("Market USD 20 billion.", "Funding USD 10 million.")
    ok, validated = make_scoring_guardrail(market_task=task)(output)
    assert ok
    runtime.install_task_callbacks()
    runtime.tasks[5].callback(validated)
    child = _runtime(tmp_path / "child", tasks=_fake_tasks(), source=source,
                     retrieval_sha256=digest, resume_directory=parent)
    assert child.restore_contiguous_prefix() == 6
    restored = child.tasks[5].output.raw
    assert restored == validated.raw
    fresh = save_scores(validated.raw, "fresh", tmp_path).read_bytes()
    assert save_scores(restored, "restored", tmp_path).read_bytes() == fresh
    text, _ = display(json.loads(restored), "scores", tmp_path, monkeypatch, persist_scores=True)
    assert "5 → 3.5 / 5" in text


def test_cap_receipt_implementation_belongs_to_recovery_identity(monkeypatch):
    """A changed producer/validator must not reuse a locally stale audit receipt."""
    from academic_agent import checkpoint_runtime
    for key in checkpoint_runtime._REVISION_ENV_VARS:
        monkeypatch.delenv(key, raising=False)
    before = checkpoint_runtime.pipeline_revision()
    read = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", lambda p: read(p) + (b"changed" if p.name == "market_cap_audit.py" else b""))
    assert checkpoint_runtime.pipeline_revision() != before


def test_guardrail_rejection_does_not_publish_a_fake_cap_receipt():
    """Only validated output may enter the post-guardrail checkpoint boundary."""
    original = _score_payload(market_accessibility=100, market_cap_audit={"applied": False})
    output = TaskOutput(description="score", agent="scorer", raw=json.dumps(deepcopy(original)))
    ok, _ = make_scoring_guardrail()(output)
    assert not ok and json.loads(output.raw) == original
