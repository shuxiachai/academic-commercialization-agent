"""The market retrieval development probe, offline."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from academic_agent.source_pipeline import _queries
from market_retrieval_probe import (
    ANCHOR_ALIASES,
    ANCHOR_ENTITIES,
    mentions,
    plan_variant,
    run_case,
    saved_coverage,
)

SAVED = {
    "topic": "unmanned aerial vehicle delivery of medical supplies",
    "search_components": ["unmanned aerial vehicles", "medical supply chain logistics"],
    "weight_profile": "industrial",
}


def test_acronyms_match_case_sensitively_as_whole_tokens():
    entities = ["ARC", "NuScale", "HTR-PM"]
    assert mentions("the ARC plant", entities) == {"ARC"}
    assert mentions("an arc furnace and a SEARCH page", entities) == set()
    assert mentions("nuscale power and HTR-PM units", entities) == {"NuScale", "HTR-PM"}


def test_every_label_comes_from_its_cohort_anchor():
    """Labels fixed before results: each is anchor text or a declared alias of it."""
    cohort = json.loads(Path("evals/heldout_trl_v1/cohort.json").read_text(encoding="utf-8"))
    assert set(ANCHOR_ENTITIES) == {case["id"] for case in cohort["cases"]}
    for case in cohort["cases"]:
        for entity in ANCHOR_ENTITIES[case["id"]]:
            assert ANCHOR_ALIASES.get(entity, entity) in case["anchor"], (case["id"], entity)


def test_variant_a_is_the_production_query_list():
    production = _queries(SAVED["topic"], weight_profile="industrial",
                          components=SAVED["search_components"])["market"]
    planned = plan_variant("A", SAVED)
    assert [q for q, _, _ in planned] == production
    assert {mode for _, mode, _ in planned} == {"general"}
    assert [limit for _, _, limit in planned][:2] == [1, 1]


def test_operator_variants_keep_reserved_queries_and_news_mode_is_topical_only():
    for variant in ("B", "D"):
        planned = plan_variant(variant, SAVED)
        assert len(planned) == 8
        assert planned[0][0].startswith("unmanned aerial vehicles company product")
        assert "operator deployments in service" in planned[2][0]
        modes = [mode for _, mode, _ in planned]
        assert modes[:2] == ["general", "general"]
        assert set(modes[2:]) == {"news" if variant == "D" else "general"}


def test_run_case_counts_admitted_sources_naming_an_entity():
    def search(query: str, mode: str) -> dict:
        return {"organic": [
            {"title": f"Zipline completes medical delivery milestone {i} {query[:12]}",
             "link": f"https://www.reuters.com/business/zipline-{abs(hash(query))}-{i}",
             "snippet": "Zipline drones delivered medical supplies to hospitals; commercial "
                        "deployment of unmanned aerial vehicle delivery of medical supplies "
                        "continues across several countries with confirmed customer contracts."}
            for i in range(1, 4)]}

    row = run_case("H10", "A", SAVED, search, url_checker=lambda url: (True, ""),
                   accessed=date(2026, 10, 1))
    assert row["market_sources"] == 8
    assert row["entity_sources"] == 8
    assert row["entities_admitted"] == ["Zipline"] == row["entities_in_results"]


def test_saved_coverage_reads_only_saved_runs(tmp_path):
    run = tmp_path / "H10-drone"
    run.mkdir()
    (run / "validated_sources.json").write_text(json.dumps({"market_sources": [
        {"title": "Zipline passes 1 million deliveries", "evidence_summary": "x"},
        {"title": "UAV Market Size 2033", "evidence_summary": "forecast"},
    ]}), encoding="utf-8")
    assert saved_coverage("H10", tmp_path) == [(1, 2)]
