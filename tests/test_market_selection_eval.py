"""The before-and-after collector answers the second arm from the first arm's record.

Zero provider calls: the search client, the planner and every source client
are replaced before the collector wraps them. What is under test is the
wiring a paid run depends on, checked here so that it is not first exercised
with the meter running.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from academic_agent import evidence, language, source_clients, source_pipeline
from academic_agent.language import TopicSearchPlan
from evals.market_selection_v1 import collect, compare
from tests.test_source_pipeline import (
    MatchingCrossref,
    _NullArXiv,
    _NullLens,
    _NullOpenAlex,
    _NullPubMed,
    _NullS2,
    fake_search,
)

ROOT = Path(__file__).resolve().parents[1]
TOPIC = "Test commercialization topic"


def test_the_recorder_answers_a_repeated_call_from_the_record_and_replays_errors(tmp_path):
    asked = []

    def lookup(key, *, strict=False):
        asked.append(key)
        if key == "bad":
            raise ValueError("refused")
        return {"key": key, "items": [1, 2]}

    first = collect.Recorder(tmp_path / "record.cache")
    call = first.function("lookup", lookup)
    answer = call("a")
    answer["items"].append(3)  # a caller changing its answer must not change the record
    assert call("a") == {"key": "a", "items": [1, 2]}
    assert call("a", strict=True) == {"key": "a", "items": [1, 2]}
    with pytest.raises(ValueError, match="refused"):
        call("bad")
    with pytest.raises(ValueError, match="refused"):
        call("bad")
    assert asked == ["a", "a", "bad"]
    assert first.calls == {"lookup: live": 3, "lookup: from the record": 2}
    first.save()

    second = collect.Recorder(tmp_path / "record.cache")
    replay = second.function("lookup", lookup)
    assert replay("a") == {"key": "a", "items": [1, 2]}
    with pytest.raises(ValueError, match="refused"):
        replay("bad")
    assert asked == ["a", "a", "bad"] and second.calls == {"lookup: from the record": 2}


def test_a_recorded_client_records_methods_and_passes_attributes_through(tmp_path):
    class Client:
        api_key = "not-a-call"

        def search(self, query):
            return {"organic": [{"title": query}]}

    recorder = collect.Recorder(tmp_path / "record.cache")
    client = recorder.client("web", Client())
    assert client.api_key == "not-a-call"
    assert client.search("q") == client.search("q") == {"organic": [{"title": "q"}]}
    assert recorder.calls == {"web.search: live": 1, "web.search: from the record": 1}


@pytest.fixture
def offline_world(monkeypatch):
    """Every outside call the collector wraps, replaced and counted."""
    counts = {"search": 0, "plan": 0, "url": 0}

    class Web:
        def search(self, query):
            counts["search"] += 1
            return fake_search(query)

    def plan(topic, n=2, **_kwargs):
        counts["plan"] += 1
        return TopicSearchPlan(search_topic=TOPIC)

    def url_check(url):
        counts["url"] += 1
        return True, ""

    monkeypatch.setattr(source_pipeline, "default_web_search_client", lambda **_locale: Web())
    monkeypatch.setattr(language, "plan_topic_search", plan)
    monkeypatch.setattr(language, "translate_headings", lambda headings, _name: tuple(headings))
    monkeypatch.setattr(evidence, "check_public_url", url_check)
    for name, fake in (("CrossrefClient", MatchingCrossref), ("OpenAlexClient", _NullOpenAlex),
                       ("SemanticScholarClient", _NullS2), ("PubMedClient", _NullPubMed),
                       ("ArxivClient", _NullArXiv), ("LensPatentClient", _NullLens)):
        monkeypatch.setattr(source_clients, name, fake)
    return counts


def _run(tmp_path, arm):
    return collect.main([
        "--src", str(ROOT / "src"), "--arm", arm, "--cache", str(tmp_path / "private" / "record.cache"),
        "--out", str(tmp_path / "runs"), "--accessed", "2026-10-30", "--only", "V06,N03",
    ])


def test_the_second_arm_makes_no_request_the_first_arm_already_made(tmp_path, offline_world, capsys):
    assert _run(tmp_path, "old") == 0
    after_old = dict(offline_world)
    assert after_old["search"] > 0 and after_old["plan"] == 2 and after_old["url"] > 0

    assert _run(tmp_path, "new") == 0
    assert offline_world == after_old, "the new arm sent a request the record already held"

    for case in ("V06", "N03"):
        old = json.loads((tmp_path / "runs" / "old" / case / "validated_sources.json").read_text(encoding="utf-8"))
        new = json.loads((tmp_path / "runs" / "new" / case / "validated_sources.json").read_text(encoding="utf-8"))
        assert [s["url"] for s in old["market_sources"]] == [s["url"] for s in new["market_sources"]]
        assert old["market_sources"][0]["accessed_date"] == "2026-10-30"
        calls = json.loads((tmp_path / "runs" / "new" / case / "calls.json").read_text(encoding="utf-8"))
        assert calls and not [name for name in calls if name.endswith(": live")]
        meta = json.loads((tmp_path / "runs" / "new" / case / "meta.json").read_text(encoding="utf-8"))
        assert (meta["arm"], meta["case"], "error" in meta) == ("new", case, False)

    # A case already collected for an arm is left as it is.
    assert _run(tmp_path, "new") == 0
    assert "already collected for the new arm" in capsys.readouterr().out
    assert offline_world == after_old


def test_a_failed_case_is_recorded_and_the_others_still_run(tmp_path, offline_world, monkeypatch):
    real = source_pipeline.collect_source_collection

    def failing(topic, **kwargs):
        if "trucks" in topic:
            raise source_pipeline.SourceCollectionError("search refused the request")
        return real(topic, **kwargs)

    monkeypatch.setattr(source_pipeline, "collect_source_collection", failing)
    assert _run(tmp_path, "old") == 1
    meta = json.loads((tmp_path / "runs" / "old" / "N03" / "meta.json").read_text(encoding="utf-8"))
    assert meta["error"].startswith("SourceCollectionError: search refused")
    assert (tmp_path / "runs" / "old" / "V06" / "validated_sources.json").exists()
    assert not (tmp_path / "runs" / "old" / "N03" / "validated_sources.json").exists()


def _registry(market, *, academic=("10.1/a",), failed=None, notes=()):
    return {
        "market_sources": [{"url": url, "title": title, "evidence_summary": "", "published_date": published}
                           for url, title, published in market],
        "academic_sources": [{"doi": doi, "url": None, "title": doi} for doi in academic],
        "patent_sources": [{"doi": None, "url": "https://patents.google.com/patent/US1", "title": "p"}],
        "failed_domains": failed or {},
        "audit": [{"domain": "market", "query": "q", "rejected_reasons": list(notes)}],
    }


def test_the_comparison_reads_both_arms_and_lists_what_must_be_read(tmp_path):
    yahoo = "https://finance.yahoo.com/news/helio-sees-space-based-solar-120000176.html"
    mirror = "https://ca.finance.yahoo.com/news/helio-sees-space-based-solar-120000176.html"
    wiki = "https://en.wikipedia.org/wiki/Space-based_solar_power"
    report = "https://finance.yahoo.com/news/space-solar-market-size-130000614.html"
    fresh = "https://www.reuters.com/technology/space-solar-demonstrator"
    note = "duplicate story (same address as the copy at finance.yahoo.com): 'Helio Sees'"
    arms = {
        "old": _registry([(yahoo, "Helio Sees", None), (mirror, "Helio Sees", None), (wiki, "SBSP - Wikipedia", None),
                          (report, "Space Solar Market Size", None)]),
        "new": _registry([(yahoo, "Helio Sees", None), (report, "Space Solar Market Size", "2026-02-04"),
                          (fresh, "Demonstrator flies", None)], academic=("10.1/a", "10.1/b"),
                         notes=(note, "market host is blocked or not approved: x")),
    }
    for arm, registry in arms.items():
        run = tmp_path / arm / "V06"
        run.mkdir(parents=True)
        (run / "validated_sources.json").write_text(json.dumps(registry), encoding="utf-8")
        (run / "calls.json").write_text(json.dumps(
            {"web[].search: live": 2 if arm == "new" else 9, "web[].search: from the record": 7}), encoding="utf-8")
    (tmp_path / "old" / "N03").mkdir()
    (tmp_path / "old" / "N03" / "meta.json").write_text(json.dumps({"error": "SourceCollectionError: x"}), encoding="utf-8")

    row = compare.compare_case(tmp_path, "V06")
    assert (row["old"]["market_sources"], row["new"]["market_sources"]) == (4, 3)
    assert (row["old"]["stories_listed_twice"], row["new"]["stories_listed_twice"]) == (1, 0)
    assert (row["old"]["largest_site"], row["new"]["largest_site"]) == (3, 2)
    assert row["old"]["over_site_share"] and not row["new"]["over_site_share"]
    assert (row["old"]["encyclopedia"], row["new"]["encyclopedia"]) == (1, 0)
    assert (row["old"]["undated"], row["new"]["undated"]) == (4, 2)
    assert [entry["url"] for entry in row["only_old"]] == [mirror, wiki]
    assert [entry["url"] for entry in row["only_new"]] == [fresh]
    assert row["newly_dated"] == [{"url": report, "published_date": "2026-02-04"}]
    assert row["new_arm_notes"] == [note]
    assert not row["academic_identical"] and row["patent_identical"]
    assert row["live_requests"] == {"old": {"web[].search: live": 9}, "new": {"web[].search: live": 2}}

    missing = compare.compare_case(tmp_path, "N03")
    assert missing == {"case": "N03", "missing": {"old": "SourceCollectionError: x"}}
    text = compare.render([row, missing])
    assert "| V06 | 4 -> 3 | 1 -> 0 | 3 -> 2 | 1 -> 0 | 4 -> 2 | NO / yes |" in text
    assert "Cases compared: 1 of 2." in text and f"- only the new arm lists: {fresh}" in text
    assert f"- note: {note}" in text and "not comparable" in text
