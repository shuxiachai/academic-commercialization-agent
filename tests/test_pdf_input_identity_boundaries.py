"""Real PDF to model-prompt to HTTP/persisted coverage and locator boundaries."""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from academic_agent import pdf_extractor as extractor
from api import main, papers, runs
from tests import test_pdf_extraction as pdf_fixture

_pdf = pdf_fixture._pdf


def long_paper():
    # Each of the first three pages contains enough real text that concatenating
    # and taking 7000 characters used to remove both later result pages.
    intro = "\n".join(f"Introduction line {i}: " + "background " * 7 for i in range(40))
    return _pdf([intro, intro, intro, "RESULTS_SENTINEL measured outcomes.",
                 "LIMITATIONS_SENTINEL and CONCLUSIONS_SENTINEL."])


def fields(**extra):
    return dict(pdf_fixture.ContributionAssemblyTests._LLM_FIELDS, **extra)


def test_actual_model_input_contains_selected_tail_and_truthful_budget():
    with patch.object(extractor, "_call_llm_json", return_value=fields(
        input_coverage={"state": "recorded", "included_pages": [999]},
        locator_status="text_candidate",
    )) as model:
        contribution = extractor.extract_paper_contribution(long_paper())
    prompt = model.call_args.args[0]
    payload = json.loads(prompt.split("paper payload:\n", 1)[1])
    text = payload["paper_text"]
    assert "RESULTS_SENTINEL" in text
    assert "CONCLUSIONS_SENTINEL" in text
    assert len(text) <= 7000
    coverage = contribution.input_coverage
    assert coverage.state == "recorded"
    assert coverage.included_pages == [1, 2, 3, 4, 5]
    assert coverage.truncated_pages == [1, 2, 3]
    assert coverage.omitted_pages == []
    assert coverage.input_characters == len(text)
    assert coverage.character_budget == 7000
    assert contribution.locator_status == "no_public_candidate"


def test_paid_http_response_and_persisted_extraction_keep_every_contribution_field(tmp_path, monkeypatch):
    """An internal coverage field is useless if response_model silently drops it."""
    monkeypatch.setattr(papers, "PAPERS_ROOT", tmp_path / "papers")
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path / "runs")
    with patch.object(extractor, "_call_llm_json", return_value=fields()), TestClient(main.app) as client:
        response = client.post("/api/papers", files={"file": ("paper.pdf", long_paper().read_bytes())})
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(extractor.PaperContribution.model_fields) <= set(body)
    saved = papers.load_extraction(body["paper_id"])
    assert body["input_coverage"] == saved["input_coverage"]
    assert body["locator_status"] == saved["locator_status"] == "no_public_candidate"
    assert body["input_coverage"]["included_pages"] == [1, 2, 3, 4, 5]


def test_tiny_budget_records_omitted_pages_instead_of_claiming_complete_input():
    coverage = {}
    text = extractor.extract_pdf_text(_pdf(["one", "two", "three"]), max_chars=12, coverage=coverage)
    assert len(text) <= 12
    assert coverage["omitted_pages"]
    assert len(coverage["included_pages"]) < len(coverage["selected_pages"])


def test_blank_scanned_paper_does_not_reach_a_paid_llm():
    with patch.object(extractor, "_call_llm_json") as model:
        with pytest.raises(ValueError, match="no extractable text"):
            extractor.extract_paper_contribution(_pdf([""]))
    model.assert_not_called()


def test_model_only_locator_is_not_promoted_into_a_citable_identity():
    with patch.object(extractor, "_call_llm_json", return_value=fields(
        doi="10.1234/another-paper", url="https://doi.org/10.1234/another-paper",
    )):
        pc = extractor.extract_paper_contribution(_pdf(["No document identifier."]))
    assert pc.url is None
    assert pc.doi.startswith(extractor._PLACEHOLDER_DOI_PREFIX)
    assert pc.locator_status == "conflicting_candidates"
    checked = []
    source = extractor.paper_to_evidence_source(pc, lambda url: (checked.append(url) or True, ""))
    assert checked == []
    assert source.credibility_tier == "medium"


def test_a_reachable_bibliography_doi_is_still_only_a_candidate():
    with patch.object(extractor, "_call_llm_json", return_value=fields()):
        pc = extractor.extract_paper_contribution(_pdf(["References: 10.1234/cited-paper"]))
    source = extractor.paper_to_evidence_source(pc, lambda url: (True, ""))
    assert pc.locator_status == "text_candidate"
    assert source.credibility_tier == "medium"
    assert "document identity" in source.credibility_reason
    assert "not been independently checked" in source.credibility_reason
