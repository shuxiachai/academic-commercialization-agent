"""The market stage's kind caps: reports, institutions, one source per authority category.

These three caps predate this file and had no test: on 2026-11-13 each could
be deleted with the suite still green. They are written against
``_collect_domain`` alone and pass on the code before the caps were moved
into ``_market_deferral``, which is what shows the move kept their behaviour.
"""

from __future__ import annotations

from datetime import date

from academic_agent.source_pipeline import _collect_domain
from tests.test_source_pipeline import MatchingCrossref

TOPIC = "Test commercialization topic"
_SNIPPET = ("Coverage of test commercialization topic deployments, with named operators, plant "
            "capacities, contract values and the dates each milestone was reached, item {}.")


def _row(title: str, link: str, index: int) -> dict:
    return {"title": title, "link": link, "snippet": _SNIPPET.format(index)}


def _report(index: int, host: str) -> dict:
    return _row(f"Test commercialization topic Market Size Report 203{index}",
                f"https://www.{host}/reports/test-commercialization-topic-market", index)


def _news(index: int) -> dict:
    return _row(f"Test commercialization topic operator {index} opens a plant",
                f"https://www.news-site-{index}.com/news/operator-opens-plant", index)


def _collect(rows: list[dict], maximum: int):
    return _collect_domain(
        "market", ["q"], lambda _query: {"organic": rows}, MatchingCrossref(), lambda url: (True, ""),
        date(2026, 11, 13), TOPIC, minimum_sources=0, maximum_sources=maximum,
    )


def _reasons(audits) -> list[str]:
    return [reason for audit in audits for reason in audit.rejected_reasons]


def test_a_fifth_market_report_waits_so_that_company_news_takes_the_slot():
    firms = ("grandviewresearch.com", "mordorintelligence.com", "precedenceresearch.com",
             "marketsandmarkets.com", "snsinsider.com")
    rows = [_report(index, host) for index, host in enumerate(firms, 1)] + [_news(6)]
    sources, audits = _collect(rows, maximum=5)
    assert [s.source_type for s in sources] == ["market_report"] * 4 + ["company_disclosure"]
    assert _reasons(audits) == [
        "deferred (market-report cap): 'Test commercialization topic Market Size Report 2035'"]


def test_a_waiting_market_report_fills_a_slot_left_empty():
    firms = ("grandviewresearch.com", "mordorintelligence.com", "precedenceresearch.com",
             "marketsandmarkets.com", "snsinsider.com")
    sources, audits = _collect([_report(index, host) for index, host in enumerate(firms, 1)], maximum=8)
    assert [s.source_id for s in sources] == ["M1", "M2", "M3", "M4", "M5"]
    assert audits[-1].query == "[Deferred-Promotion]" and audits[-1].accepted_source_ids == ["M5"]


def test_a_fourth_institutional_source_waits_so_that_company_news_takes_the_slot():
    hosts = ("energy.gov", "nasa.gov", "nrel.gov", "epa.gov")
    rows = [_row(f"Test commercialization topic programme overview {index}",
                 f"https://www.{host}/programmes/test-commercialization-topic", index)
            for index, host in enumerate(hosts, 1)] + [_news(5)]
    sources, audits = _collect(rows, maximum=4)
    assert [s.source_type for s in sources] == ["government"] * 3 + ["company_disclosure"]
    assert _reasons(audits) == [
        "deferred (institutional cap): 'Test commercialization topic programme overview 4'"]


def test_a_second_regulator_record_waits_once_its_category_is_covered():
    rows = [
        _row("Test commercialization topic device approval summary",
             "https://www.fda.gov/medical-devices/test-commercialization-topic-approval", 1),
        _row("Test commercialization topic assessment report",
             "https://www.ema.europa.eu/en/medicines/test-commercialization-topic", 2),
        _row("Test commercialization topic trial record",
             "https://clinicaltrials.gov/study/NCT00000001", 3),
        _news(4),
    ]
    sources, audits = _collect(rows, maximum=3)
    hosts = [str(s.url).split("/")[2] for s in sources]
    # One regulator, then the registry (another category), then the news item.
    assert hosts == ["www.fda.gov", "clinicaltrials.gov", "www.news-site-4.com"]
    assert _reasons(audits) == [
        "deferred (authority category already covered): 'Test commercialization topic assessment report'"]
