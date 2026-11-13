"""The saved-run audit counts each run once and replays the pipeline's own rules."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.audits import market_evidence_audit as audit

_TEXT = ("HOUSTON, Oct. 27, 2025 /PRNewswire/ -- The two companies today announced a partnership "
         "to accelerate integrated geothermal assets, including a pilot of enhanced geothermal systems.")


def _source(source_id: str, url: str, title: str, *, kind: str = "reputable_news",
            published: str | None = None, summary: str = _TEXT) -> dict:
    return {"source_id": source_id, "url": url, "title": title, "source_type": kind,
            "published_date": published, "evidence_summary": summary}


def _write(root: Path, name: str, market: list[dict], *, collected: str = "2026-11-02T03:00:00Z",
           audit_rows: list[dict] | None = None, scorecard: dict | None = None) -> Path:
    run = root / name
    run.mkdir(parents=True)
    (run / audit.REGISTRY).write_text(json.dumps({
        "collected_at": collected, "market_sources": market, "audit": audit_rows or [],
    }), encoding="utf-8")
    if scorecard is not None:
        (run / audit.SCORECARD).write_text(json.dumps(scorecard), encoding="utf-8")
    return run


RELEASE = "SLB and Ormat Partner to Accelerate Integrated Geothermal Asset Development"
MARKET = [
    _source("M1", "https://finance.yahoo.com/news/slb-ormat-partner-accelerate-integrated-130000995.html", RELEASE),
    _source("M2", "https://uk.finance.yahoo.com/news/slb-ormat-partner-accelerate-integrated-130000995.html", RELEASE),
    _source("M3", "https://www.prnewswire.com/news-releases/slb-and-ormat-partner-302000001.html", RELEASE,
            kind="company_disclosure"),
    _source("M4", "https://en.wikipedia.org/wiki/Enhanced_geothermal_system", "Enhanced geothermal system - Wikipedia",
            kind="other"),
    _source("M5", "https://finance.yahoo.com/news/geothermal-developer-raises-series-c-140000111.html",
            "Geothermal developer raises a Series C round", summary="A funding round, described at length."),
    _source("M6", "https://ca.finance.yahoo.com/news/utility-signs-geothermal-offtake-150000222.html",
            "Utility signs a geothermal offtake agreement", summary="An offtake agreement, described at length."),
    _source("M7", "https://finance.yahoo.com/news/enhanced-geothermal-market-size-160000333.html",
            "Enhanced Geothermal Market Size to Reach USD 9 Billion", kind="market_report",
            summary="A market estimate, described at length."),
    _source("M8", "https://www.grandviewresearch.com/industry-analysis/enhanced-geothermal-market",
            "Enhanced Geothermal Market Size Report, 2034", kind="market_report",
            summary="Another firm's estimate, described at length.", published=None),
]


def test_a_registry_is_counted_once_and_only_if_it_lists_market_sources(tmp_path):
    first = _write(tmp_path, "batch/run-a", MARKET)
    copy = tmp_path / "archive" / "run-a"
    copy.mkdir(parents=True)
    (copy / audit.REGISTRY).write_bytes((first / audit.REGISTRY).read_bytes())
    _write(tmp_path, "batch/run-empty", [])
    _write(tmp_path, "batch/run-old", MARKET[:2], collected="2026-09-30T23:59:59Z")
    (tmp_path / "batch" / "broken").mkdir()
    (tmp_path / "batch" / "broken" / audit.REGISTRY).write_text("{not json", encoding="utf-8")

    runs, skipped = audit.load_runs(tmp_path, "2026-10-01")
    assert [run.path for run in runs] == ["archive/run-a"]
    assert skipped == {"copies of a registry already counted": 1,
                       "registries with no market source": 1, "unreadable": 1}


def test_the_replay_drops_copies_and_encyclopedia_entries_and_holds_a_sites_third_source(tmp_path):
    _write(tmp_path, "run", MARKET)
    [run] = audit.load_runs(tmp_path, "2026-10-01")[0]
    result = audit.replay(run)
    # The wire copy takes the Yahoo copy's place; the regional copy and Wikipedia leave.
    assert [row["source_id"] for row in result.kept] == ["M3", "M5", "M6", "M8"]
    assert [(dropped["source_id"], kept["source_id"], why) for dropped, kept, why in result.duplicates] == [
        ("M2", "M1", "same address"), ("M1", "M3", "same headline")]
    assert [row["source_id"] for row in result.encyclopedia] == ["M4"]
    # M5 and M6 fill yahoo.com's share once M1 has gone; M7 is its third.
    assert [row["source_id"] for row in result.waiting] == ["M7"]


def test_the_figures_report_the_site_share_as_a_range(tmp_path):
    cap = {"triggered": True, "applied": True, "pre_cap_score": 4.0, "post_cap_score": 3.5}
    _write(tmp_path, "run", MARKET, scorecard={"market_accessibility": 3.5, "market_cap_audit": cap},
           audit_rows=[{"domain": "market", "query": "[Page-Dates] publication date", "accepted_source_ids": [],
                        "rejected_reasons": ["M5: no publication date found", "M6: page not read within 20 s"]}])
    runs, skipped = audit.load_runs(tmp_path, "2026-10-01")
    figures = audit.measure(runs)
    saved, after = figures["as_saved"], figures["replayed"]
    assert (figures["runs"], figures["market_sources"]) == (1, 8)
    assert saved["runs_listing_a_story_twice"] == 1 and saved["slots_holding_a_second_copy"] == 2
    assert saved["duplicate_signs"] == {"same address": 1, "same headline": 1}
    assert saved["runs_with_a_site_over_its_share"] == 1 and saved["runs_with_an_encyclopedia_entry"] == 1
    assert saved["sources_on_wire_or_syndicating_hosts"] == 6
    assert saved["undated_reasons"] == {
        "no note in the audit": 3,
        "not read: encyclopedia entry": 1,
        "no publication date found": 1,
        "page not read in time": 1,
        "not read: market report on a wire or syndicating host": 1,
        "not read: market report on its publisher's page": 1,
    }
    assert after["sources_no_longer_listed"] == 3 and after["sources_waiting_for_a_slot"] == 1
    assert after["runs_listing_a_story_twice"] == 0
    assert after["runs_with_a_site_over_its_share"] == {
        "if_every_waiting_source_is_replaced": 0, "if_none_is_replaced": 1}
    assert after["preferred_copy_replaces_listed_copy"] == 1
    assert figures["scorecards"] == {
        "scorecards": 1, "with_a_cap_record": 1, "cap_triggered": 1, "cap_lowered_the_score": 1,
        "market_accessibility_at_the_cap": 1}
    text = audit.render("2026-10-01", figures, skipped)
    assert "| Runs where one site holds more than 2 slots | 1 (100%) | 0 (0%) to 1 (100%) |" in text


def test_a_run_with_nothing_to_change_is_reported_as_unchanged(tmp_path):
    """Silence is not a pass: a zero here must come from a run that was read."""
    _write(tmp_path, "run", [MARKET[4], MARKET[7]])
    runs, _ = audit.load_runs(tmp_path, "2026-10-01")
    figures = audit.measure(runs)
    assert figures["runs"] == 1 and figures["replayed"]["runs_changed"] == 0
    assert audit.render_pairs(runs) == ""


def test_page_metadata_is_compared_with_the_releases_own_dateline(tmp_path):
    _write(tmp_path, "run", MARKET)
    runs, _ = audit.load_runs(tmp_path, "2026-10-01")
    yahoo, wire, firm = MARKET[0]["url"], MARKET[2]["url"], MARKET[7]["url"]
    check = audit.page_date_agreement(runs, [
        {"url": yahoo, "source_type": "reputable_news", "date": "2025-10-28"},
        {"url": wire, "source_type": "company_disclosure", "date": "2025-11-30"},
        {"url": MARKET[4]["url"], "source_type": "reputable_news", "date": None},
        # A report publisher's own page is outside the check.
        {"url": firm, "source_type": "market_report", "date": "2024-01-01"},
    ])
    assert check["probed_pages_on_wire_or_syndicating_hosts"] == {
        "company_disclosure: dated": 1, "reputable_news: dated": 1, "reputable_news: undated": 1}
    assert check["with_a_dateline_in_the_saved_excerpt"] == {
        "company_disclosure: further apart": 1, "reputable_news: within a day": 1}
    assert check["differing"] == [{"url": wire, "metadata": "2025-11-30", "dateline": "2025-10-27"}]


def test_a_dateline_is_a_full_date_before_a_wires_mark_and_nothing_else():
    assert audit.dateline("Dublin, Sept. 9, 2026 (GLOBE NEWSWIRE) -- The report").isoformat() == "2026-09-09"
    assert audit.dateline("NEW YORK, October 27, 2025 /PRNewswire/ -- SLB").isoformat() == "2025-10-27"
    assert audit.dateline("The company was founded on October 27, 2025 in Houston.") is None
    assert audit.dateline("Feb 31, 2026 /PRNewswire/ -- no such day") is None


def test_the_command_prints_each_window_and_writes_the_figures(tmp_path, capsys):
    _write(tmp_path / "outputs", "run", MARKET)
    out = tmp_path / "figures.json"
    assert audit.main([str(tmp_path / "outputs"), "--since", "2026-10-01", "--since", "2026-12-01",
                       "--pairs", "--json", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "## Runs collected since 2026-10-01" in printed and "## Runs collected since 2026-12-01" in printed
    assert "- copy (same address): https://uk.finance.yahoo.com/" in printed
    assert "- waits (site share, yahoo.com): https://finance.yahoo.com/news/enhanced-geothermal" in printed
    figures = json.loads(out.read_text(encoding="utf-8"))
    assert figures["2026-10-01"]["runs"] == 1 and figures["2026-12-01"]["runs"] == 0
