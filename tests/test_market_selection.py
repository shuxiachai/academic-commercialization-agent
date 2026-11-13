"""One copy of a story, a bounded share per site, no encyclopedia in the market slots.

The pairs below are from saved runs (2026-10 and 2026-11). Each "same" case
is a release the report listed twice; each "different" case is a pair that a
looser rule would have merged and that the run needs both of.
"""

from __future__ import annotations

from datetime import date

import pytest

from academic_agent import source_pipeline
from academic_agent.market_selection import (
    MARKET_SOURCES_PER_SITE,
    MarketItem,
    prefer,
    provenance_rank,
    same_story,
    shared_text,
    site_of,
)
from academic_agent.source_pipeline import _collect_domain, collect_source_collection
from tests.test_source_pipeline import (
    MatchingCrossref,
    _NullArXiv,
    _NullLens,
    _NullOpenAlex,
    _NullPubMed,
    _NullS2,
    fake_search,
)

TOPIC = "Test commercialization topic"
ACCESSED = date(2026, 11, 13)

_RELEASE = (
    "HOUSTON, Oct. 27, 2025 -- The two companies today announced a partnership to accelerate "
    "commercialization of integrated geothermal assets, including a pilot of enhanced geothermal "
    "systems at an existing plant, with first power expected within two years of the agreement."
)
_OTHER_RELEASE = (
    "The developer said its second commercialization milestone was a signed offtake agreement "
    "with a regional utility, covering forty megawatts of capacity from a plant now under "
    "construction, with financing arranged through a consortium of infrastructure lenders."
)
_ABOUT = (
    " About the company: it develops, finances and operates carbon removal facilities and "
    "commercialization partnerships worldwide, and is a subsidiary of a listed energy group "
    "with operations in more than forty countries and a long record of project delivery."
)


def item(title: str, url: str, summary: str = "", published: date | None = None) -> MarketItem:
    return MarketItem(title=title, url=url, summary=summary, published=published)


# ── site_of ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("url", "site"), [
    ("https://finance.yahoo.com/news/a.html", "yahoo.com"),
    ("https://uk.finance.yahoo.com/news/a.html", "yahoo.com"),
    ("https://ca.finance.yahoo.com/news/a.html", "yahoo.com"),
    ("https://www.grandviewresearch.com/industry-analysis/x", "grandviewresearch.com"),
    ("https://cbinsights.com/research/x", "cbinsights.com"),
    ("https://www.bbc.co.uk/news/x", "bbc.co.uk"),
    ("https://www.gov.uk/government/x", "www.gov.uk"),
    ("https://market.us/report/x", "market.us"),
    ("https://www-pub.iaea.org/x", "iaea.org"),
    ("HTTPS://WWW.Reuters.COM/x", "reuters.com"),
    ("https://192.0.2.10/x", "192.0.2.10"),
    ("not a url", ""),
])
def test_a_publishers_regional_and_section_hosts_are_one_site(url, site):
    assert site_of(url) == site


@pytest.mark.parametrize(("first", "second"), [
    # Each EU body is its own publisher under europa.eu.
    ("https://www.ema.europa.eu/en/x", "https://ec.europa.eu/info/x"),
    # Every name on a hosting platform is a different author.
    ("https://alice.substack.com/p/x", "https://bob.substack.com/p/y"),
    ("https://lab-one.github.io/x", "https://lab-two.github.io/y"),
    ("https://www.bbc.co.uk/news/x", "https://www.theguardian.co.uk/y"),
])
def test_unrelated_publishers_under_a_shared_suffix_are_different_sites(first, second):
    """Grouping them would let one publisher's two pages cost another its slot."""
    assert site_of(first) != site_of(second)


# ── same_story: the three signs ────────────────────────────────────────────


@pytest.mark.parametrize(("first", "second"), [
    # A regional edition of one Yahoo Finance page (space-based solar run, M2 and M3).
    ("https://ca.finance.yahoo.com/news/helio-sees-space-based-solar-120000176.html",
     "https://finance.yahoo.com/news/helio-sees-space-based-solar-120000176.html"),
    # The same page with a tracking parameter the locator check did not strip.
    ("https://finance.yahoo.com/news/psyence-biomed-announces-approval-psylabs-120000015.html?fr=sycsrp_catchall",
     "https://finance.yahoo.com/news/psyence-biomed-announces-approval-psylabs-120000015.html"),
    # With and without "www.".
    ("https://www.cbinsights.com/research/leading-brain-computer-interface-startups",
     "https://cbinsights.com/research/leading-brain-computer-interface-startups"),
])
def test_one_article_at_two_addresses_of_one_site_is_one_story(first, second):
    """Titles and excerpts are not consulted: the address alone settles it."""
    assert same_story(item("One title", first), item("Another title entirely", second)) == "same address"
    assert same_story(item("Another title entirely", second), item("One title", first)) == "same address"


def test_one_numbered_article_filed_under_two_sections_is_one_story():
    """Yahoo lists an article under /news/ and under a sector; the id in the slug is the article's."""
    first = item("One title", "https://finance.yahoo.com/news/standing-ovation-raises-34-2-064500233.html")
    second = item("Another title entirely",
                  "https://finance.yahoo.com/sectors/technology/articles/standing-ovation-raises-34-2-064500233.html")
    assert same_story(first, second) == "same address"


def test_a_recurring_release_filed_under_each_year_is_not_one_story():
    """The same slug in two directories, with no id: this year's results and last year's."""
    title = "Example Energy Announces Third Quarter Financial Results"
    first = item(title, "https://www.example-energy.com/news/2025/third-quarter-financial-results")
    second = item(title, "https://ir.example-energy.com/news/2026/third-quarter-financial-results")
    assert same_story(first, second) == ""


def test_one_release_under_two_numeric_ids_of_one_site_is_one_story():
    """Yahoo posted this release twice; only the id at the end of the slug differs."""
    title = "SLB and Ormat Partner to Accelerate Integrated Geothermal Asset Development"
    first = item(title, "https://finance.yahoo.com/news/slb-ormat-partner-accelerate-integrated-130000995.html")
    second = item(title, "https://uk.finance.yahoo.com/news/slb-ormat-partner-accelerate-integrated-130000034.html")
    assert same_story(first, second) == "same address"


def test_a_shared_slug_stem_needs_the_same_headline_too():
    """Two releases can open with the same six words; the id is then all that tells them apart."""
    first = item("SLB and Ormat Partner to Accelerate Integrated Geothermal Asset Development",
                 "https://finance.yahoo.com/news/slb-ormat-partner-accelerate-integrated-130000995.html")
    second = item("SLB and Ormat Partner to Accelerate Integrated Carbon Storage in Norway",
                  "https://finance.yahoo.com/news/slb-ormat-partner-accelerate-integrated-140000111.html")
    assert same_story(first, second) == ""


def test_numbered_articles_under_one_title_are_a_series_not_one_article():
    """Only a long numeric id is set aside; "-1" and "-2" number the parts of a series."""
    title = "Quarterly Geothermal Industry Update for Investors and Operators"
    first = item(title, "https://finance.yahoo.com/news/quarterly-geothermal-industry-update-1.html")
    second = item(title, "https://finance.yahoo.com/news/quarterly-geothermal-industry-update-2.html")
    assert same_story(first, second) == ""


@pytest.mark.parametrize(("first", "second"), [
    # A short final segment recurs across a site's sections.
    ("https://energy.example.edu/research/index.html", "https://physics.example.edu/research/index.html"),
    ("https://ir.example.com/news", "https://www.example.com/news"),
    # "-2" is what a site appends to a second article of the same name (a PatSnap pair
    # in a saved run): not shown to be the same article, so both stay.
    ("https://www.patsnap.com/resources/blog/articles/dry-electrode-manufacturing-for-solid-state-batteries",
     "https://www.patsnap.com/resources/blog/articles/dry-electrode-manufacturing-for-solid-state-batteries-2"),
    # The same long slug on two different sites proves nothing by itself.
    ("https://www.grandviewresearch.com/reports/brain-computer-interface-market",
     "https://www.mordorintelligence.com/reports/brain-computer-interface-market"),
])
def test_addresses_that_do_not_show_one_article_are_left_alone(first, second):
    title = "Dry electrode manufacturing for solid-state batteries - PatSnap"
    assert same_story(item(title, first), item(title, second)) == ""


def test_a_document_mirror_is_the_same_story_as_its_original():
    """everycrsreport.com republishes CRS reports whole; the two excerpts shared nothing."""
    mirror = item("Enhanced Geothermal Systems (EGS) Commercialization - EveryCRSReport.com",
                  "https://www.everycrsreport.com/reports/IF13278.html", "An excerpt from page one.")
    original = item("Enhanced Geothermal Systems (EGS) Commercialization",
                    "https://www.congress.gov/crs-product/IF13278", "A different excerpt, from page two.")
    assert same_story(mirror, original) == "mirror"
    assert same_story(original, mirror) == "mirror"
    other_report = item("Enhanced Geothermal Systems (EGS) Permitting on Federal Land",
                        "https://www.congress.gov/crs-product/IF13300")
    assert same_story(mirror, other_report) == ""


@pytest.mark.parametrize(("carrier_title", "carrier_url"), [
    # The headline with the host's name after it.
    ("1PointFive and Bain & Company Announce Agreement for Direct Air Capture Carbon Removal Credits | Markets Insider",
     "https://markets.businessinsider.com/news/stocks/release-103570663"),
    # The headline cut short by the search result.
    ("1PointFive and Bain & Company Announce Agreement ...",
     "https://www.otcmarkets.com/stock/OXY/news/story?id=509342"),
    # A rewritten headline on a page whose address still carries the release's own.
    ("1PointFive, Bain sign DAC credits deal | OXY Stock News",
     "https://www.stocktitan.net/news/OXY/1point-five-and-bain-company-announce-agreement-for-direct-air-8o7v21wdr57b.html"),
])
def test_a_release_carried_by_a_syndicating_host_is_the_same_story(carrier_title, carrier_url):
    release = item("1PointFive and Bain & Company Announce Agreement for Direct Air Capture Carbon Removal Credits",
                   "https://finance.yahoo.com/news/1pointfive-bain-company-announce-agreement-130000434.html",
                   _RELEASE)
    copy = item(carrier_title, carrier_url, _RELEASE + " Read more on the host's site.")
    assert same_story(release, copy) == "same headline"
    assert same_story(copy, release) == "same headline"


def test_the_issuers_own_page_and_the_wire_copy_are_the_same_story():
    own = item("CATL Debuts World's First Field-Validated Sodium-Ion BESS ...",
               "https://www.catl.com/en/news/6861.html", _RELEASE)
    wire = item("CATL Debuts World's First Field-Validated Sodium-Ion BESS, Bringing Sodium Storage to Scale",
                "https://www.prnewswire.com/news-releases/catl-debuts-302581234.html", _RELEASE)
    assert same_story(own, wire) == "same headline"


def test_dates_falling_together_confirm_a_headline_when_the_excerpts_share_nothing():
    title = "Quantum Corridor, Toshiba Demonstrate First Cross-State Quantum Key Distribution"
    first = item(title, "https://finance.yahoo.com/news/a-133000465.html", _RELEASE, date(2025, 12, 9))
    second = item(title, "https://www.prnewswire.com/news-releases/b-302636001.html", _OTHER_RELEASE,
                  date(2025, 12, 10))
    assert shared_text(first.summary, second.summary) == 0.0
    assert same_story(first, second) == "same headline"


# ── same_story: what must not be merged ────────────────────────────────────


@pytest.mark.parametrize(("first_title", "second_title"), [
    # Two firms, two estimates, near-identical titles: the commonest pair on the saved runs.
    ("Precision Fermentation Market Size, Share | CAGR of 21.0%",
     "Precision Fermentation Market Size, Share | Growth Report 2034"),
    ("Quantum Computing In Drug Discovery Market Size, Share ...",
     "Quantum Computing In Drug Discovery Market Size, Share ..."),
])
def test_two_firms_reports_with_alike_titles_are_different_sources(first_title, second_title):
    first = item(first_title, "https://market.us/report/precision-fermentation-market",
                 "The market was valued at USD 2.8 billion in 2025 and is forecast to reach USD 36 billion.")
    second = item(second_title, "https://www.fortunebusinessinsights.com/precision-fermentation-market-109824",
                  "The market size was USD 4.1 billion in 2025 and is projected to grow to USD 54 billion.")
    assert same_story(first, second) == ""


def test_an_identical_headline_without_a_second_sign_is_left_alone():
    """Undated, nothing shared: a recurring release and its predecessor look exactly like this."""
    title = "Example Therapeutics Reports Inducement Grants Under Nasdaq Listing Rule 5635(c)(4)"
    first = item(title, "https://finance.yahoo.com/news/a-120000111.html", _RELEASE)
    second = item(title, "https://www.globenewswire.com/news-release/b.html", _OTHER_RELEASE)
    assert same_story(first, second) == ""


def test_an_identical_headline_on_dates_far_apart_is_a_recurring_release():
    """Shared boilerplate would otherwise confirm it; the two dates say it is not one release."""
    title = "Example Therapeutics Reports Inducement Grants Under Nasdaq Listing Rule 5635(c)(4)"
    first = item(title, "https://finance.yahoo.com/news/a-120000111.html", _RELEASE, date(2026, 9, 4))
    second = item(title, "https://www.globenewswire.com/news-release/b.html", _RELEASE, date(2026, 10, 5))
    assert same_story(first, second) == ""


def test_two_releases_by_one_company_sharing_their_closing_paragraph_are_different():
    """1PointFive's agreement with Bain and its deployment plan with Carbon Engineering."""
    first = item("1PointFive and Bain & Company Announce Agreement for Direct Air Capture Carbon Removal Credits",
                 "https://markets.businessinsider.com/news/stocks/1pointfive-and-bain-company-announce-103570663",
                 "Bain will purchase carbon removal credits over three years." + _ABOUT)
    second = item("1PointFive and Carbon Engineering Announce Direct Air Capture Deployment Approach",
                  "https://finance.yahoo.com/news/1pointfive-carbon-engineering-announce-direct-123000354.html",
                  "The companies plan seventy facilities by 2035." + _ABOUT)
    assert shared_text(first.summary, second.summary) > 0.5
    assert same_story(first, second) == ""


def test_an_identical_headline_on_two_sites_that_carry_nobody_elses_releases_is_left_alone():
    title = "Hyperloop Transportation Technologies Signs Feasibility Study Agreement"
    first = item(title, "https://www.hyperlooptt.com/news/a", _RELEASE)
    second = item(title, "https://www.railway-technology.com/news/b", _RELEASE)
    assert same_story(first, second) == ""


def test_a_short_headline_is_never_enough():
    first = item("Company Overview | Markets Insider", "https://markets.businessinsider.com/stocks/a", _RELEASE)
    second = item("Company Overview", "https://finance.yahoo.com/quote/b", _RELEASE)
    assert same_story(first, second) == ""


def test_a_truncated_headline_only_matches_as_an_opening():
    full = item("Helio Sees Space-Based Solar Power Gaining Urgency as Industry Leaders Highlight Orbital Energy",
                "https://finance.yahoo.com/news/a-120000176.html", _RELEASE)
    other = item("Helio Sees Space-Based Solar Power Losing Ground ...",
                 "https://www.otcmarkets.com/stock/HLEO/news/b?id=1", _RELEASE)
    assert same_story(full, other) == ""


# ── which copy to keep ─────────────────────────────────────────────────────


def test_the_copy_nearest_the_issuer_is_preferred():
    own = item("t", "https://www.catl.com/en/news/6861.html")
    wire = item("t", "https://www.prnewswire.com/news-releases/x.html")
    yahoo = item("t", "https://finance.yahoo.com/news/x.html")
    regional = item("t", "https://uk.finance.yahoo.com/news/x.html")
    insider = item("t", "https://markets.businessinsider.com/news/stocks/x")
    assert [provenance_rank(i.url) for i in (own, wire, yahoo, insider)] == [0, 1, 2, 2]
    assert prefer(own, wire) and prefer(wire, yahoo) and prefer(own, yahoo)
    assert prefer(yahoo, regional)
    # Never the other way, and never between two equals: the first listed stays.
    assert not prefer(wire, own) and not prefer(yahoo, wire) and not prefer(regional, yahoo)
    assert not prefer(yahoo, insider) and not prefer(insider, yahoo)
    # A shorter host name on another site is not a "main host": stocktitan.net is not nearer than Yahoo.
    titan = item("t", "https://stocktitan.net/news/OXY/x.html")
    assert not prefer(titan, yahoo) and not prefer(yahoo, titan)
    assert not prefer(yahoo, yahoo)


# ── the market stage ───────────────────────────────────────────────────────


def _result(title: str, link: str, snippet: str = _RELEASE) -> dict:
    return {"title": title, "link": link, "snippet": snippet}


def _news_title(index: int) -> str:
    return f"Test commercialization topic operator {index} signs a supply contract for its plant"


def _news(index: int, host: str = "www.reuters.com") -> dict:
    return _result(
        _news_title(index),
        f"https://{host}/technology/operator-{index}-signs-commercialization-contract",
        f"Operator {index} said the commercialization contract covers plant {index}, with a "
        f"utility as the buyer, capacity of {index}00 megawatts and delivery starting in 203{index}; "
        f"the deal is the operator's largest so far and was financed by lender group {index}.",
    )


def _collect(results_by_query: dict[str, list[dict]], *, maximum: int = 8, **kwargs):
    def search(query: str) -> dict:
        return {"organic": results_by_query[query]}

    return _collect_domain(
        "market", list(results_by_query), search, MatchingCrossref(), lambda url: (True, ""),
        ACCESSED, TOPIC, minimum_sources=0, maximum_sources=maximum, **kwargs,
    )


def _reasons(audits) -> list[str]:
    return [reason for audit in audits for reason in audit.rejected_reasons]


def test_a_story_listed_twice_takes_one_slot_and_the_next_result_takes_the_other():
    """Space-based solar, 2026-10: M2 and M3 were one Yahoo page; the slot goes to M4's story now."""
    sources, audits = _collect({"q": [
        _result("Helio Sees Space-Based Solar Power Commercialization Gaining Urgency",
                "https://finance.yahoo.com/news/helio-sees-space-based-solar-120000176.html"),
        _result("Helio Sees Space-Based Solar Power Commercialization Gaining Urgency",
                "https://ca.finance.yahoo.com/news/helio-sees-space-based-solar-120000176.html"),
        _news(1),
    ]}, maximum=2)
    assert [str(s.url) for s in sources] == [
        "https://finance.yahoo.com/news/helio-sees-space-based-solar-120000176.html",
        "https://www.reuters.com/technology/operator-1-signs-commercialization-contract",
    ]
    assert [s.source_id for s in sources] == ["M1", "M2"]
    assert _reasons(audits) == [
        "duplicate story (same address as the copy at finance.yahoo.com): "
        "'Helio Sees Space-Based Solar Power Commercialization Gaining Urgency'"
    ]


def test_a_copy_nearer_the_issuer_takes_over_the_slot_of_the_one_listed_first():
    title = "1PointFive and Bain Announce Commercialization Agreement for Carbon Removal Credits"
    sources, audits = _collect({
        "q1": [_result(title, "https://finance.yahoo.com/news/1pointfive-bain-announce-agreement-130000434.html"),
               _news(1)],
        "q2": [_result(title, "https://www.prnewswire.com/news-releases/1pointfive-and-bain-302000001.html")],
    })
    assert [(s.source_id, site_of(str(s.url))) for s in sources] == [("M1", "prnewswire.com"), ("M2", "reuters.com")]
    assert sources[0].source_type == "company_disclosure"
    assert _reasons(audits) == [
        "duplicate story (same headline); the copy at www.prnewswire.com replaces the one at "
        f"finance.yahoo.com: {title!r}"
    ]
    # The slot's id stays with the query that first found the story.
    assert [a.accepted_source_ids for a in audits] == [["M1", "M2"], []]


def test_a_copy_no_nearer_the_issuer_leaves_the_listed_one_in_place():
    title = "1PointFive and Bain Announce Commercialization Agreement for Carbon Removal Credits"
    sources, audits = _collect({"q": [
        _result(title, "https://www.prnewswire.com/news-releases/1pointfive-and-bain-302000001.html"),
        _result(title, "https://finance.yahoo.com/news/1pointfive-bain-announce-agreement-130000434.html"),
    ]})
    assert [site_of(str(s.url)) for s in sources] == ["prnewswire.com"]
    assert _reasons(audits) == [f"duplicate story (same headline as the copy at www.prnewswire.com): {title!r}"]


def test_a_third_result_from_one_site_waits_while_another_site_takes_the_slot():
    """Yahoo held five of eight market slots in a saved run; here it would hold three of three."""
    sources, audits = _collect({"q": [
        _news(1, "finance.yahoo.com"), _news(2, "finance.yahoo.com"), _news(3, "finance.yahoo.com"),
        _news(4, "www.reuters.com"),
    ]}, maximum=3)
    assert [site_of(str(s.url)) for s in sources] == ["yahoo.com", "yahoo.com", "reuters.com"]
    assert MARKET_SOURCES_PER_SITE == 2
    assert _reasons(audits) == [
        f"deferred (site share: yahoo.com already holds 2): {_news_title(3)!r}"
    ]


def test_regional_hosts_count_toward_one_sites_share():
    sources, _audits = _collect({"q": [
        _news(1, "finance.yahoo.com"), _news(2, "uk.finance.yahoo.com"), _news(3, "ca.finance.yahoo.com"),
        _news(4, "www.reuters.com"),
    ]}, maximum=3)
    assert [str(s.url).split("/")[2] for s in sources] == [
        "finance.yahoo.com", "uk.finance.yahoo.com", "www.reuters.com"]


def test_a_waiting_result_fills_a_slot_nothing_else_took():
    """The share is a preference, not a ban: three different releases are three sources."""
    sources, audits = _collect({"q": [
        _news(1, "finance.yahoo.com"), _news(2, "finance.yahoo.com"), _news(3, "finance.yahoo.com"),
    ]}, maximum=4)
    assert [s.source_id for s in sources] == ["M1", "M2", "M3"]
    assert str(sources[2].url).endswith("operator-3-signs-commercialization-contract")
    promotion = audits[-1]
    assert promotion.query == "[Deferred-Promotion]" and promotion.accepted_source_ids == ["M3"]


def test_a_query_at_its_source_limit_promotes_no_more_from_a_full_site():
    """Every result here is on one site, as Yahoo's were for some topics.

    Held results do not stop a query being read, so the first query alone
    held enough to fill the domain. Each query still supplies at most its
    limit, as _MARKET_SOURCES_PER_QUERY intends.
    """
    def rows(query: int) -> list[dict]:
        return [_news(query * 10 + index, "finance.yahoo.com") for index in range(1, 7)]

    sources, audits = _collect({"q1": rows(1), "q2": rows(2), "q3": rows(3)}, maximum=8,
                               query_limits={"q1": 3, "q2": 3, "q3": 3})
    found = [int(str(s.url).split("operator-")[1].split("-")[0]) // 10 for s in sources]
    assert found == [1, 1, 1, 2, 2, 2, 3, 3]
    assert audits[-1].query == "[Deferred-Promotion]" and len(audits[-1].accepted_source_ids) == 6


def test_waiting_results_within_their_sites_share_are_promoted_first():
    """A deferred report from a new site outranks an earlier result from a site already at its share."""
    report = "Test commercialization topic Market Size, Share & Trends Report 203{}"
    reports = [_result(report.format(i), f"https://www.firm-{i}.example.com/reports/topic-market-{i}",
                       _OTHER_RELEASE + f" Edition {i}.") for i in range(1, 6)]
    for row, host in zip(reports, ("grandviewresearch.com", "mordorintelligence.com", "precedenceresearch.com",
                                   "marketsandmarkets.com", "snsinsider.com"), strict=True):
        row["link"] = f"https://www.{host}/reports/topic-market"
    sources, _audits = _collect({"q": [
        _news(1, "finance.yahoo.com"), _news(2, "finance.yahoo.com"), _news(3, "finance.yahoo.com"),
        *reports,
    ]}, maximum=7)
    # Two Yahoo, four reports (the report cap), then the fifth report before the third Yahoo.
    assert [site_of(str(s.url)) for s in sources] == [
        "yahoo.com", "yahoo.com", "grandviewresearch.com", "mordorintelligence.com",
        "precedenceresearch.com", "marketsandmarkets.com", "snsinsider.com"]


def test_a_waiting_copy_of_a_story_accepted_later_is_never_promoted():
    title = "1PointFive and Bain Announce Commercialization Agreement for Carbon Removal Credits"
    sources, audits = _collect({"q": [
        _news(1, "finance.yahoo.com"), _news(2, "finance.yahoo.com"),
        _result(title, "https://finance.yahoo.com/news/1pointfive-bain-announce-agreement-130000434.html"),
        _result(title, "https://markets.businessinsider.com/news/stocks/1pointfive-and-bain-103570663"),
    ]})
    assert [site_of(str(s.url)) for s in sources] == ["yahoo.com", "yahoo.com", "businessinsider.com"]
    assert f"duplicate story (same headline as the copy at markets.businessinsider.com): {title!r}" in _reasons(audits)
    assert audits[-1].query == "[Deferred-Promotion]" and audits[-1].accepted_source_ids == []


def test_an_encyclopedia_entry_is_not_market_evidence_even_with_slots_to_spare():
    sources, audits = _collect({"q": [
        _result("Test commercialization topic - Wikipedia", "https://en.wikipedia.org/wiki/Test_commercialization"),
        _news(1),
    ]})
    assert [site_of(str(s.url)) for s in sources] == ["reuters.com"]
    assert _reasons(audits) == [
        "encyclopedia entry is not market evidence: 'Test commercialization topic - Wikipedia'"]


def test_a_later_pass_counts_what_the_earlier_one_kept():
    """The company-news and native-language passes start a new collection for the same slots."""
    title = "1PointFive and Bain Announce Commercialization Agreement for Carbon Removal Credits"
    first_pass, _ = _collect({"q": [
        _result(title, "https://finance.yahoo.com/news/1pointfive-bain-announce-agreement-130000434.html"),
        _news(1, "finance.yahoo.com"),
    ]})
    sources, audits = _collect({"q": [
        _result(title, "https://uk.finance.yahoo.com/news/1pointfive-bain-announce-agreement-130000434.html"),
        _news(2, "finance.yahoo.com"),
        _news(3, "www.reuters.com"),
    ]}, maximum=1, market_kept=first_pass)
    assert [site_of(str(s.url)) for s in sources] == ["reuters.com"]
    assert _reasons(audits) == [
        f"duplicate story (same address as the copy at finance.yahoo.com): {title!r}",
        f"deferred (site share: yahoo.com already holds 2): {_news_title(2)!r}",
    ]


def test_a_nearer_copy_does_not_displace_what_an_earlier_pass_kept():
    """The earlier pass's list belongs to the caller; a later pass only declines the copy."""
    title = "1PointFive and Bain Announce Commercialization Agreement for Carbon Removal Credits"
    first_pass, _ = _collect({"q": [
        _result(title, "https://finance.yahoo.com/news/1pointfive-bain-announce-agreement-130000434.html"),
    ]})
    sources, audits = _collect({"q": [
        _result(title, "https://www.prnewswire.com/news-releases/1pointfive-and-bain-302000001.html"),
        _news(3),
    ]}, market_kept=first_pass)
    assert [site_of(str(s.url)) for s in first_pass] == ["yahoo.com"]
    assert [(s.source_id, site_of(str(s.url))) for s in sources] == [("M1", "reuters.com")]
    assert _reasons(audits) == [f"duplicate story (same headline as the copy at finance.yahoo.com): {title!r}"]


def test_the_company_news_pass_does_not_add_a_third_source_from_a_full_site():
    """Seam: collect_source_collection hands the first pass's sources to the later ones."""
    def report(index: int) -> dict:
        return _result(
            f"Test commercialization topic Market Size to Reach USD {index} Billion by 2034",
            f"https://finance.yahoo.com/news/test-commercialization-topic-market-size-{index}-11300039{index}.html",
            f"The test commercialization topic market was valued at USD {index}.4 billion and is "
            f"forecast to grow at a compound annual rate of {index}1 percent, according to firm {index}'s report.",
        )

    def search(query: str) -> dict:
        if "site:patents" in query or " DOI" in query or "review journal" in query or "efficiency stability" in query:
            return fake_search(query)
        if "announcement press release" in query or "product launch news" in query:
            return {"organic": [_news(7, "finance.yahoo.com"), _news(8, "www.reuters.com")]}
        return {"organic": [report(1), report(2)]}

    collection = collect_source_collection(
        TOPIC, searcher=search, crossref=MatchingCrossref(), openalex=_NullOpenAlex(), s2=_NullS2(),
        lens=_NullLens(), pubmed=_NullPubMed(), arxiv=_NullArXiv(), url_checker=lambda url: (True, ""),
        minimum_sources=2, maximum_sources=4, accessed_date=date(2026, 6, 30),
    )
    sites = [site_of(str(s.url)) for s in collection.market_sources]
    assert sites.count("yahoo.com") == 2 and "reuters.com" in sites
    assert not any("operator-7" in str(s.url) for s in collection.market_sources)


def test_the_rules_leave_other_domains_alone():
    """Two patents on one host are two patents; the share is a market rule."""
    assert source_pipeline.MARKET_SOURCES_PER_SITE == MARKET_SOURCES_PER_SITE
    sources, _audits = _collect_domain(
        "patent", ["Test commercialization topic site:patents.google.com/patent"], fake_search,
        MatchingCrossref(), lambda url: (True, ""), ACCESSED, TOPIC, minimum_sources=0, maximum_sources=8,
    )
    assert len(sources) == 3


def test_the_native_language_pass_counts_what_the_english_pass_kept(monkeypatch):
    """Seam: the pass that searches in the submitter's language fills the same slots.

    It runs only on the default search client, so the client itself is
    replaced here; the native-language client is the one built with a locale.
    No test reached this pass through the collector before.
    """
    from unittest.mock import patch

    from academic_agent.language import TopicSearchPlan

    raw_topic = "测试主题的商业化评估"
    native_queries: list[str] = []

    class Client:
        def __init__(self, native: bool) -> None:
            self.native = native

        def search(self, query: str) -> dict:
            if self.native:
                native_queries.append(query)
                return {"organic": [_news(7, "finance.yahoo.com"), _news(8, "www.reuters.com")]}
            if "site:patents" in query or " DOI" in query or "review journal" in query \
                    or "efficiency stability" in query:
                return fake_search(query)
            if query == raw_topic:
                return {"organic": []}
            return {"organic": [_news(1, "finance.yahoo.com"), _news(2, "uk.finance.yahoo.com")]}

    monkeypatch.setattr(source_pipeline, "default_web_search_client", lambda **locale: Client(bool(locale)))
    with patch("academic_agent.language.plan_topic_search", return_value=TopicSearchPlan(search_topic=TOPIC)):
        collection = collect_source_collection(
            raw_topic, crossref=MatchingCrossref(), openalex=_NullOpenAlex(), s2=_NullS2(),
            lens=_NullLens(), pubmed=_NullPubMed(), arxiv=_NullArXiv(), url_checker=lambda url: (True, ""),
            minimum_sources=2, maximum_sources=3, accessed_date=date(2026, 6, 30),
        )
    assert native_queries == [raw_topic]
    # One slot was left; Yahoo already held two, so it goes to the other site.
    assert [site_of(str(s.url)) for s in collection.market_sources] == ["yahoo.com", "yahoo.com", "reuters.com"]
