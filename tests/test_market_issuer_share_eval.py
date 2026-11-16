"""The issuer-share comparison reads two arms' registries with the rule under test.

Zero provider calls. What is under test is the wiring a paid comparison
depends on: this experiment's cases reach the shared collector, the reading
counts issuers with the pipeline's own rule, and only the cases the protocol
admits are frozen for the scored part.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

from evals.market_issuer_share_v1 import collect, compare, freeze
from evals.market_selection_v1 import collect as shared_collect

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "evals" / "market_issuer_share_v1" / "cases.json").read_text(encoding="utf-8"))

_HELIO = ('Berkeley, California--(Newsfile Corp. - February 4, 2026) - Helio Corporation (OTCID: HLEO) ("Helio" or the '
          '"Company") today reaffirmed the value of solar-powered orbital infrastructure.')


def _source(source_id: str, url: str, title: str, summary: str = "A release, described at length.") -> dict:
    return {"source_id": source_id, "url": url, "title": title, "published_date": None, "evidence_summary": summary}


HELIO = [
    _source("M1", "https://finance.yahoo.com/news/helio-sees-space-based-solar-120000176.html",
            "Helio Sees Space-Based Solar Power Gaining Urgency", _HELIO),
    _source("M2", "https://www.stocktitan.net/news/HLEO/helio-corporation-announces-strategic-entry.html",
            "Helio Corporation (HLEO) enters space-based solar power | HLEO Stock News"),
    _source("M3", "https://markets.businessinsider.com/news/stocks/helio-highlights-new-age-space-race-1035941226",
            "Helio Highlights New Age Space Race as Space Based Solar Power Moves from Prototype | Markets Insider"),
]
OTHER = _source("M3", "https://www.reuters.com/business/energy/orbital-power-startups-raise-funds",
                "Orbital power startups raise funds")
HELD = f"deferred (issuer share: 2 listed sources have its issuer): {HELIO[2]['title']!r}"
COPY = "duplicate story (same address as the copy at finance.yahoo.com): 'A release'"


def _arm(out: Path, arm: str, case: str, market: list[dict], audit: list[dict] | None = None) -> None:
    run = out / arm / case
    run.mkdir(parents=True)
    (run / "validated_sources.json").write_text(json.dumps({
        "market_sources": market, "academic_sources": [{"doi": "10.1/a"}], "patent_sources": [{"url": "https://p/1"}],
        "audit": audit or [], "failed_domains": {},
    }), encoding="utf-8")
    (run / "calls.json").write_text(json.dumps({"web[]: live": 3}), encoding="utf-8")


def test_the_cases_are_two_scored_development_topics_and_unseen_ones():
    cases = CASES["cases"]
    assert len({case["id"] for case in cases}) == len(cases) == 10
    cohort = {case["id"]: case["topic"] for case in json.loads(
        (ROOT / "evals" / "heldout_trl_v2" / "cohort.json").read_text(encoding="utf-8"))["cases"]}
    scored = [case for case in cases if case["scored"]]
    assert [case["id"] for case in scored] == ["V01", "V06"]
    assert all(cohort[case["id"]] == case["topic"] for case in scored), "Scored cases are the frozen cohort's, unchanged"
    assert all(case["id"].startswith("U") and case["id"] not in cohort for case in cases if not case["scored"])
    assert (ROOT / CASES["protocol"]).is_file()


def test_the_shared_collector_is_given_this_experiments_cases(monkeypatch):
    seen = {}
    monkeypatch.setattr(shared_collect, "main", lambda argv=None: seen.update(cases=shared_collect.CASES, argv=argv) or 0)
    monkeypatch.setattr(shared_collect, "CASES", shared_collect.CASES)       # restored after the test
    assert collect.main(["--arm", "old"]) == 0
    assert seen == {"cases": collect.CASES, "argv": ["--arm", "old"]}
    assert collect.CASES.parent.name == "market_issuer_share_v1"


def test_the_reading_counts_issuers_in_each_arm_and_lists_what_was_held(tmp_path):
    _arm(tmp_path, "old", "V06", HELIO)
    _arm(tmp_path, "new", "V06", [*HELIO[:2], OTHER],
         audit=[{"domain": "market", "query": "q", "rejected_reasons": [HELD, "evidence summary too thin (31 chars): 'x'", COPY]}])
    row = compare.compare_case(tmp_path, "V06")
    assert (row["old"]["largest_issuer_group"], row["new"]["largest_issuer_group"]) == (3, 2)
    assert (row["old"]["issuers_over_their_share"], row["new"]["issuers_over_their_share"]) == (1, 0)
    assert row["old"]["unexplained"] == 1, "The old arm has no rule: nothing explains its group of three"
    assert row["new"]["unexplained"] == 0
    assert row["new_arm_notes"] == [HELD, COPY], "The market stage's other notes are listed; a thin summary is not one"
    assert row["held_for_an_issuer"] == 1, "Only the issuer's note is counted as held for an issuer"
    assert [entry["url"] for entry in row["only_old"]] == [HELIO[2]["url"]]
    assert [entry["url"] for entry in row["only_new"]] == [OTHER["url"]]
    text = compare.render([row])
    assert "| V06 | 3 -> 3 | 3 -> 2 | 1 -> 0 | 1 | 1 -> 1 | 3 -> 3 | yes / yes |" in text
    assert "- new arm: 1 sources held for an issuer's share in 1 cases; issuers over their share with no returned " \
           "release to explain it: 0." in text
    assert f"- note: {HELD}" in text and f"- only the new arm lists: {OTHER['url']}" in text
    assert "- one issuer in the new arm:\n  - https://finance.yahoo.com/news/helio-sees" in text


def test_an_issuer_over_its_share_is_explained_only_by_a_release_that_returned_to_an_empty_slot(tmp_path):
    promoted = [{"domain": "market", "query": "[Deferred-Promotion]", "accepted_source_ids": ["M3"], "rejected_reasons": []}]
    _arm(tmp_path, "old", "V06", HELIO)
    _arm(tmp_path, "new", "V06", HELIO, audit=promoted)
    row = compare.compare_case(tmp_path, "V06")
    assert (row["new"]["issuers_over_their_share"], row["new"]["unexplained"]) == (1, 0)
    # The same list with no such record is a defect in the wiring.
    assert compare.issuer_measure({"market_sources": HELIO, "audit": []})["unexplained"] == 1
    accepted_by_a_query = [dict(promoted[0], query="space-based solar power market")]
    assert compare.issuer_measure({"market_sources": HELIO, "audit": accepted_by_a_query})["unexplained"] == 1
    other_domain = [dict(promoted[0], domain="patent")]
    assert compare.issuer_measure({"market_sources": HELIO, "audit": other_domain})["unexplained"] == 1
    assert compare.issuer_measure({"market_sources": [], "audit": []})["largest_issuer_group"] == 0


def test_a_case_one_arm_did_not_collect_is_reported_as_not_comparable(tmp_path, capsys):
    _arm(tmp_path, "old", "V06", HELIO)
    assert compare.main(["--out", str(tmp_path), "--json", str(tmp_path / "compare.json")]) == 0
    printed = capsys.readouterr().out
    assert "| V06 | not comparable: {'new': 'not collected'} |" in printed
    assert "Cases compared: 0 of 10." in printed
    assert len(json.loads((tmp_path / "compare.json").read_text(encoding="utf-8"))) == 10


def test_only_the_scored_cases_the_protocol_admits_are_frozen(tmp_path, monkeypatch, capsys):
    frozen = []
    benchmark = types.SimpleNamespace(_slug=lambda topic: topic.replace(" ", "-"))
    fixtures = types.SimpleNamespace(freeze=lambda case, slug, topic, text: frozen.append((case, slug)) or {
        "file": f"{case}.json", "sha256_16": "0" * 16, "counts": {}})
    monkeypatch.setitem(sys.modules, "benchmark", benchmark)
    monkeypatch.setitem(sys.modules, "benchmark_fixtures", fixtures)
    monkeypatch.setattr(sys, "path", list(sys.path))
    for case in ("V01", "V06", "U01"):
        _arm(tmp_path, "new", case, HELIO)
    assert freeze.main(["--arm-dir", str(tmp_path / "new"), "--only", "V06,U01"]) == 0
    assert frozen == [("V06", "space-based-solar-power")], "An unscored case is never frozen, whatever --only says"
    frozen.clear()
    assert freeze.main(["--arm-dir", str(tmp_path / "new")]) == 0
    assert [case for case, _slug in frozen] == ["V01", "V06"]
    # A scored case with no registry stops the freeze: a pair cannot be half frozen.
    assert freeze.main(["--arm-dir", str(tmp_path / "old")]) == 1
    assert "no registry under" in capsys.readouterr().out
