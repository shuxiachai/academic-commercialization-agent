"""The market-query attribution audit over saved source collections."""

from __future__ import annotations

import json

from pathlib import Path

from scripts.audits.market_query_origin import entity_coverage, names_entity, query_class, summarise

TOPIC = "fusion power"
COMPONENTS = ["tokamak reactors", "superconducting magnets"]


def _collection() -> dict:
    return {
        "topic": TOPIC,
        "display_topic": TOPIC,
        "search_components": COMPONENTS,
        "market_sources": [
            {"source_id": "M1", "title": "Tokamak Market Size Report 2026"},
            {"source_id": "M2", "title": "Helion signs power purchase agreement"},
            {"source_id": "M3", "title": "Fusion Energy Market CAGR 2026-2033"},
        ],
        "audit": [
            {"domain": "academic", "query": "fusion power review journal",
             "accepted_source_ids": ["M9"]},
            {"domain": "market", "query": "tokamak reactors company product commercial deployment 2025 2026",
             "accepted_source_ids": ["M1", "M2"]},
            {"domain": "market", "query": "fusion power market size revenue commercial manufacturer 2025 2026",
             "accepted_source_ids": ["M3"]},
            {"domain": "market", "query": "[Relevance-Filter]", "accepted_source_ids": []},
        ],
    }


def test_query_classes_follow_template_wording_not_topic_length():
    """A six-word topic's short form equals the full topic; wording decides."""
    assert query_class("fusion power market size revenue commercial manufacturer 2025 2026",
                       COMPONENTS, TOPIC) == "market-size"
    assert query_class("fusion power company commercial deployment industry news",
                       COMPONENTS, TOPIC) == "topic-deployment"
    assert query_class("superconducting magnets company product commercial deployment 2025 2026",
                       COMPONENTS, TOPIC) == "component"
    assert query_class("fusion power approval authorization site:fda.gov",
                       COMPONENTS, TOPIC) == "authority"
    assert query_class("[Deferred-Promotion]", COMPONENTS, TOPIC) == "pipeline-pass"


def test_summary_attributes_sources_and_counts_queries_that_ran(tmp_path):
    run = tmp_path / "H02-fusion-power"
    run.mkdir()
    (run / "validated_sources.json").write_text(json.dumps(_collection()), encoding="utf-8")

    summary = summarise(tmp_path)

    assert summary["runs"] == 1
    assert summary["market_sources"] == 3
    assert summary["by_query_class"]["component"] == {
        "queries_run": 1, "sources": 2, "market_size_titled": 1}
    assert summary["by_query_class"]["market-size"] == {
        "queries_run": 1, "sources": 1, "market_size_titled": 1}
    assert summary["by_query_class"]["pipeline-pass"]["sources"] == 0
    assert "topic-deployment" not in summary["by_query_class"]


def test_entity_mentions_are_case_sensitive_whole_tokens():
    assert names_entity("Zipline passes 2 million deliveries", ["Zipline"])
    assert not names_entity("a zipline adventure park", ["Zipline"])
    assert not names_entity("Ziplines for sale", ["Zipline"])
    assert names_entity("经京沪干线传输", ["京沪干线"])


def test_entity_coverage_counts_each_run_against_the_cohort(tmp_path):
    cohort = tmp_path / "cohort.json"
    cohort.write_text(json.dumps({"cases": [{"id": "V10", "anchor_entities": ["AeroFarms"]}]}),
                      encoding="utf-8")
    for rep, titles in (("", ["AeroFarms opens farm", "Market size 2030"]), ("__r2", ["Indoor farm"])):
        run = tmp_path / f"V10-vertical-farming{rep}"
        run.mkdir()
        (run / "validated_sources.json").write_text(json.dumps({"market_sources": [
            {"title": t, "evidence_summary": ""} for t in titles]}), encoding="utf-8")
    assert entity_coverage(tmp_path, cohort) == {"V10": [[1, 2], [0, 1]]}


def test_every_v2_anchor_entity_is_fixed_in_its_anchor():
    """The retrieval label is anchor text (or a declared translation), set before the batch."""
    cases = json.loads(Path("evals/heldout_trl_v2/cohort.json").read_text(encoding="utf-8"))["cases"]
    assert len(cases) == 10
    for case in cases:
        assert case["anchor_entities"], case["id"]
        for entity in case["anchor_entities"]:
            assert case.get("anchor_aliases", {}).get(entity, entity) in case["anchor"], (case["id"], entity)
