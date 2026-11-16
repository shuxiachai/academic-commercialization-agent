"""One issuer's releases share two market slots, wherever they are carried.

The site share cannot see that one company wrote three releases when three
hosts carry them. The pairs below are from saved runs (2026-10 and 2026-11):
each "same" case is a pair one issuer wrote, and each "different" case is a
pair a looser reading tied together and that the run needs both of.
"""

from __future__ import annotations

import pytest

from academic_agent.market_selection import (
    MARKET_SOURCES_PER_ISSUER,
    Issuer,
    MarketItem,
    issuer_mates,
    issuer_of,
    same_issuer,
    site_of,
)
from tests.test_market_selection import _collect, _news, _news_title, _reasons, _result

# ── what a result states about its issuer ──────────────────────────────────

_HELIO_OPENING = (
    'Berkeley, California--(Newsfile Corp. - February 4, 2026) - Helio Corporation (OTCID: HLEO) ("Helio" or the '
    '"Company") today reaffirmed the value of solar-powered orbital infrastructure for commercialization of '
    "space-based solar power, as energy demand grows on Earth and in space."
)
_NO_OPENING = (
    "rising demand from artificial intelligence, electrification, and industrial growth. The company remains "
    "focused on commercialization of grid scale energy delivery to terrestrial customers."
)


def item(title: str, url: str, summary: str = _NO_OPENING) -> MarketItem:
    return MarketItem(title=title, url=url, summary=summary)


HELIO_YAHOO = item("Helio Sees Space-Based Solar Power Gaining Urgency",
                   "https://finance.yahoo.com/news/helio-sees-space-based-solar-120000176.html", _HELIO_OPENING)
HELIO_TITAN = item("Helio Corporation (HLEO) enters space-based solar power | HLEO Stock News",
                   "https://www.stocktitan.net/news/HLEO/helio-corporation-announces-strategic-entry-into-space.html")
HELIO_OTC = item("Helio Sees Space-Based Solar Power Gaining Urgency | HLEO - Helio Corporation | News",
                 "https://www.otcmarkets.com/stock/HLEO/news/Helio-Sees-Space-Based-Solar-Power?id=509342")
# Stock Titan often prints a headline of its own, with no company name in it.
HELIO_REWRITTEN = item("Space power developer wins new aerospace contracts | HLEO Stock News",
                       "https://www.stocktitan.net/news/HLEO/helio-corporation-secures-new-aerospace-contracts.html")
HELIO_INSIDER = item("Helio Highlights New Age Space Race as Space Based Solar Power Moves from Prototype | Markets Insider",
                     "https://markets.businessinsider.com/news/stocks/helio-highlights-new-age-space-race-1035941226")


def test_a_carrier_that_files_releases_under_a_symbol_names_the_issuer_in_its_address():
    assert issuer_of(HELIO_TITAN).symbols == {"HLEO"}
    assert issuer_of(HELIO_OTC).symbols == {"HLEO"}
    # The same path on a host that does not file by symbol says nothing.
    elsewhere = item("A headline", "https://finance.yahoo.com/news/HLEO/helio-enters-space-based-solar-power.html")
    assert issuer_of(elsewhere).symbols == frozenset()
    # ...and a path of another shape on the host that does.
    assert issuer_of(item("A headline", "https://www.stocktitan.net/sec-filings/HLEO/8-k.html")).symbols == frozenset()
    assert issuer_of(item("A headline", "https://www.otcmarkets.com/stock/HLEO/overview")).symbols == frozenset()


def test_a_carrier_that_files_by_symbol_prints_the_issuers_name_beside_it():
    """In the run of 2026-11-15 these two titles were the only place Helio was named."""
    assert issuer_of(HELIO_TITAN).names == {("helio",)}, '"Helio Corporation (HLEO) enters ..."'
    assert issuer_of(HELIO_OTC).names == {("helio",)}, '"... | HLEO - Helio Corporation | News"'
    assert issuer_of(HELIO_REWRITTEN).names == frozenset()
    # A name beside some other symbol is a company the headline mentions.
    partner = item("Northrop Grumman (NOC) picks Helio for orbital power study | HLEO Stock News",
                   "https://www.stocktitan.net/news/HLEO/northrop-grumman-picks-helio-for-orbital-power-study.html")
    assert issuer_of(partner).names == frozenset() and issuer_of(partner).symbols == {"HLEO"}
    # The same title on a host that does not file by symbol names nobody.
    elsewhere = item(HELIO_TITAN.title, "https://finance.yahoo.com/news/helio-corporation-enters-120000176.html")
    assert issuer_of(elsewhere) == Issuer(carried=True, tail="hleostocknews")


def test_the_opening_after_the_wires_mark_states_the_symbol_and_the_name():
    stated = issuer_of(HELIO_YAHOO)
    assert stated.symbols == {"HLEO"}
    assert stated.names == {("helio",)}, "The legal form is not part of the name"
    assert stated.carried and stated.own_label == ""


@pytest.mark.parametrize(("opening", "symbols", "names"), [
    ("GALWAY, Ireland, Feb. 17, 2026 /PRNewswire/ -- Medtronic today announced that the first U.S. commercial case",
     set(), {("medtronic",)}),
    ("GALWAY, Ireland /PRNewswire/ -- Medtronic (NYSE: MDT), a global leader in healthcare technology, today announced",
     {"MDT"}, {("medtronic",)}),
    ("SHANGHAI, July 25, 2025 /PRNewswire/ -- Envision Energy, a global leader in green technology, is proud to announce",
     set(), {("envision", "energy")}),
    ("SAN FRANCISCO, Oct. 2, 2026 (GLOBE NEWSWIRE) -- Aikido Technologies, Inc. (Aikido), a floating offshore wind "
     "technology provider, announced today", set(), {("aikido", "technologies")}),
    ("LONDON, Nov. 3, 2026 (GLOBE NEWSWIRE) -- Arqit Quantum Inc. (Nasdaq: ARQQ, ARQQW) (\"Arqit\"), a global leader",
     {"ARQQ"}, {("arqit", "quantum")}),
    ("VANCOUVER, British Columbia--(BUSINESS WIRE)-- Optimi Health Corp. (CSE: OPTI) (OTCQX: OPTHF) (FSE: 8BN) "
     '("Optimi" or the "Company"), a Canadian manufacturer', {"OPTI", "OPTHF", "8BN"}, {("optimi", "health"), ("optimi",)}),
    # Two partners announce together: either is the issuer.
    ("RENO, Nev. and HOUSTON, Oct. 27, 2025 (GLOBE NEWSWIRE) -- Leading geothermal and renewable energy company "
     "Ormat Technologies (NYSE: ORA), and Global energy technology company SLB (NYSE: SLB) today announced",
     {"ORA", "SLB"}, set()),
])
def test_what_a_releases_opening_states(opening, symbols, names):
    stated = issuer_of(item("A headline of a release", "https://finance.yahoo.com/news/a-release-120000176.html", opening))
    assert stated.symbols == symbols
    assert stated.names == names


@pytest.mark.parametrize("opening", [
    # Words that open a sentence are not a company.
    "VANCOUVER, Nov. 4, 2026 (GLOBE NEWSWIRE) -- New results published in Nuclear Fusion confirm General Fusion created",
    "ELLABELL, Ga., Oct. 1, 2026 /PRNewswire/ -- Today, Hyundai Motor Group Metaplant America (HMGMA), in cooperation",
    'Dublin, Sept. 30, 2025 (GLOBE NEWSWIRE) -- The "Floating Offshore Wind Energy Market" report has been added to',
    "BOSTON, Oct. 9, 2026 /PRNewswire/ -- According to the latest study from BCC Research, the market is projected",
    "RENO, Nev., Oct. 27, 2025 (GLOBE NEWSWIRE) -- Leading geothermal company Ormat Technologies, and SLB today",
    # A name must run straight into a comma, a bracket or the verb.
    "STOCKHOLM, Nov. 2, 2026 /PRNewswire/ -- Novatron Fusion Group and Oxford Sigma are pleased to announce a partnership",
])
def test_an_opening_that_does_not_begin_with_a_name_names_nobody(opening):
    assert issuer_of(item("A headline of a release", "https://finance.yahoo.com/news/a-120000176.html", opening)).names == frozenset()


def test_companies_a_release_goes_on_to_mention_are_not_its_issuers():
    """A market-report release lists a dozen players with their symbols."""
    players = ("Austin, Dec. 08, 2025 (GLOBE NEWSWIRE) -- DNA Data Storage Market Size & Growth Insights: [...] Twist "
               "Bioscience (NASDAQ: TWST) Illumina (NASDAQ: ILMN) Microsoft (NASDAQ: MSFT) are the key players named.")
    assert issuer_of(item("DNA Data Storage Market Size to Hit USD 13 Billion", "https://finance.yahoo.com/news/dna-1.html",
                          players)).symbols == frozenset(), "After a gap in the excerpt the text is from elsewhere in the page"
    late = ("Austin, Dec. 08, 2025 (GLOBE NEWSWIRE) -- " + "The market for the technology keeps growing as adoption widens. " * 5
            + "Key players include Illumina (NASDAQ: ILMN).")
    assert issuer_of(item("A market release", "https://finance.yahoo.com/news/dna-2.html", late)).symbols == frozenset()
    # No wire's mark in the excerpt: a symbol somewhere in it is a mention.
    mention = "The partnership with Illumina (NASDAQ: ILMN) covers commercialization of the storage platform in two regions."
    assert issuer_of(item("A release", "https://finance.yahoo.com/news/dna-3.html", mention)).symbols == frozenset()


def test_a_release_that_calls_a_listed_company_the_company_is_its_own():
    """Stock Titan's excerpt of a Helio filing has no wire's mark, and says who "the Company" is."""
    text = ("On January 6, 2026, the Board of Directors (the “Board”) of Helio Corporation (OTCID: HLEO) "
            "(“Helio” or the “Company”) approved the commercialization plan.")
    assert issuer_of(item("A filing", "https://finance.yahoo.com/news/helio-board-120000176.html", text)).symbols == {"HLEO"}
    filing = issuer_of(item("A filing", "https://finance.yahoo.com/news/helio-board-120000176.html", text))
    assert filing.names == {("helio",)}, "...and the name it gives itself there is its name"
    other = text.replace("or the “Company”", "or the “Partner”")
    assert issuer_of(item("A filing", "https://finance.yahoo.com/news/helio-board-120000176.html", other)) == Issuer(carried=True)
    # The other order, and "the Company" with no name beside it.
    turned = 'VANCOUVER -- Optimi Health Corp. (NASDAQ: OPTH) (CSE: OPTI) (the "Company" or "Optimi"), a manufacturer'
    stated = issuer_of(item("A release", "https://www.nasdaq.com/press-release/optimi-lists-on-nasdaq", turned))
    assert (stated.symbols, stated.names) == ({"OPTH", "OPTI"}, {("optimi",)}), "Every listing named before the definition"
    bare = 'The Board of Example Mining Ltd. (TSXV: EXM) (the "Company") approved the plan.'
    stated = issuer_of(item("A release", "https://finance.yahoo.com/news/example-mining-120000176.html", bare))
    assert (stated.symbols, stated.names) == ({"EXM"}, frozenset())


def test_a_page_that_is_not_carried_states_only_whose_site_it_is_on():
    page = issuer_of(item("Direct Air Capture Market Size, Share & Growth, 2026-2035",
                          "https://www.snsinsider.com/reports/direct-air-capture-market-10621", _HELIO_OPENING))
    assert page == Issuer(own_label="snsinsider")
    # A short label is a word, not a firm: market.us would be "market".
    assert issuer_of(item("A report", "https://market.us/report/quantum-key-distribution-qkd-market")) == Issuer()
    assert issuer_of(item("No address", "")) == Issuer()


# ── one issuer ─────────────────────────────────────────────────────────────


def test_releases_filed_under_or_opening_with_one_symbol_have_one_issuer():
    assert same_issuer(HELIO_YAHOO, HELIO_TITAN) == "same symbol"
    assert same_issuer(HELIO_TITAN, HELIO_OTC) == "same symbol"
    wave = item("Eco Wave Power Launches Array | WAVE Stock News", "https://www.stocktitan.net/news/WAVE/eco-wave-power-x.html")
    assert same_issuer(HELIO_TITAN, wave) == ""


def test_a_company_listed_on_several_exchanges_is_one_issuer():
    first = item("Optimi Health Reports Results", "https://finance.yahoo.com/news/optimi-a-120000176.html",
                 'VANCOUVER--(BUSINESS WIRE)-- Optimi Health Corp. (CSE: OPTI) (OTCQX: OPTHF) (FSE: 8BN) ("Optimi")')
    second = item("Optimi Health Lists on Nasdaq", "https://www.nasdaq.com/press-release/optimi-b",
                  "VANCOUVER, Nov. 2, 2026 (GLOBE NEWSWIRE) -- Optimi (NASDAQ: OPTH) (CSE: OPTI) (FSE: 8BN0) said")
    assert same_issuer(first, second) == "same symbol"


def test_releases_that_open_with_one_company_name_have_one_issuer():
    first = item("Aikido Technologies Full-Scale Floating Wind Demonstrator to Be Tested in Norway",
                 "https://finance.yahoo.com/news/aikido-technologies-full-scale-floating-213000311.html",
                 "SAN FRANCISCO, Oct. 2, 2026 (GLOBE NEWSWIRE) -- Aikido Technologies, Inc. (Aikido), a floating offshore wind")
    second = item("Aikido Launches Offshore Datacenter Technology",
                  "https://finance.yahoo.com/news/aikido-launches-offshore-datacenter-technology-120000680.html",
                  "SAN FRANCISCO, Nov. 5, 2026 (GLOBE NEWSWIRE) -- Aikido Technologies (Aikido), an offshore infrastructure")
    other = item("Envision Energy Powers the World's First Green Marine Ammonia Bunkering",
                 "https://www.prnewswire.com/news-releases/envision-energy-powers-x-302000001.html",
                 "SHANGHAI, July 25, 2025 /PRNewswire/ -- Envision Energy, a global leader in green technology, is proud")
    assert same_issuer(first, second) == "same name"
    assert same_issuer(first, other) == ""


def test_a_carried_headline_that_begins_with_the_issuers_name_is_the_issuers():
    """Search excerpted the middle of this release, so it states no issuer of its own."""
    assert same_issuer(HELIO_YAHOO, HELIO_INSIDER) == "named in headline"
    assert same_issuer(HELIO_INSIDER, HELIO_YAHOO) == "named in headline"


@pytest.mark.parametrize("other", [
    # The name later in the headline is a company written about.
    item("Why Investors Think Helio Could Lead Space-Based Solar Power",
         "https://finance.yahoo.com/news/why-investors-think-helio-120000111.html"),
    # A page that is not a carried release: a newspaper writing about the company.
    item("Helio Highlights New Age Space Race as Space Based Solar Power Moves from Prototype",
         "https://www.reuters.com/business/energy/helio-highlights-new-age-space-race"),
    # The headline is the name and nothing else.
    item("Helio", "https://finance.yahoo.com/quote/HLEO/news-120000112.html"),
    # A release that states an issuer of its own is that issuer's.
    item("Helio and Envision Energy Sign a Supply Agreement",
         "https://www.prnewswire.com/news-releases/helio-and-envision-energy-sign-302000002.html",
         "SHANGHAI, July 25, 2025 /PRNewswire/ -- Envision Energy, a global leader in green technology, today announced"),
])
def test_a_headline_alone_does_not_make_an_issuer(other):
    assert same_issuer(HELIO_YAHOO, other) == ""
    assert same_issuer(other, HELIO_YAHOO) == ""


def test_a_symbol_only_release_and_a_headline_only_release_are_not_tied_directly():
    """Each is tied to the release that states both; issuer_mates carries the link."""
    assert same_issuer(HELIO_REWRITTEN, HELIO_INSIDER) == ""
    assert same_issuer(HELIO_REWRITTEN, HELIO_YAHOO) == "same symbol"


SNS_PAGE = item("Direct Air Capture Market Size, Share & Growth, 2026-2035",
                "https://www.snsinsider.com/reports/direct-air-capture-market-10621")


@pytest.mark.parametrize(("title", "summary"), [
    ("Carbon Dioxide Utilization Market Size to Reach USD 16.22 Billion by 2032 | SNS Insider", _NO_OPENING),
    ("DNA Data Storage Market Size to Hit USD 13291.51 million by 2032 | Research by SNS Insider", _NO_OPENING),
    ("Carbon Dioxide Utilization Market Size to Reach USD 16.22 Billion by 2032: SNS Insider Inc.", _NO_OPENING),
    ("Carbon Dioxide Utilization Market to Reach USD 16.22 Billion by 2032- SNS Insider", _NO_OPENING),
    ("Carbon Dioxide Utilization Market Size to Reach USD 16.22 Billion",
     'Austin, Nov. 06, 2025 (GLOBE NEWSWIRE) -- According to the SNS Insider, "The Carbon Dioxide Utilization Market"'),
    ("Carbon Dioxide Utilization Market Size to Reach USD 16.22 Billion",
     'Austin, Nov. 06, 2025 (GLOBE NEWSWIRE) -- "As per the SNS Insider report, the market reached a valuation of"'),
    ("Carbon Dioxide Utilization Market Size to Reach USD 16.22 Billion",
     "Austin, Nov. 06, 2025 /PRNewswire/ -- The market will grow, according to a new report published by SNS Insider."),
])
def test_a_release_that_credits_a_research_firm_is_that_firms(title, summary):
    release = item(title, "https://finance.yahoo.com/news/carbon-dioxide-utilization-market-size-120000505.html", summary)
    assert same_issuer(SNS_PAGE, release) == "credited firm"
    assert same_issuer(release, SNS_PAGE) == "credited firm"


def test_the_resellers_fixed_sentence_credits_it():
    page = item("Carbon Dioxide Removal Market 2026-2030 - Research and Markets",
                "https://www.researchandmarkets.com/reports/6030859/carbon-dioxide-removal-market")
    added = 'Dublin, Jan. 22, 2026 (GLOBE NEWSWIRE) -- The "{}" has been added to ResearchAndMarkets.com\'s offering.'
    first = item("Liquid Carbon Dioxide Research Report 2026: $9.23 Bn Market Opportunities",
                 "https://finance.yahoo.com/news/liquid-carbon-dioxide-research-report-115300644.html",
                 added.format("Liquid Carbon Dioxide Market Report 2026"))
    second = item("Commercial Electric Aircraft Market - Global Forecast Report 2026-2032",
                  "https://uk.finance.yahoo.com/news/commercial-electric-aircraft-market-global-113200429.html",
                  "of 7.1%. [...] " + added.format("Commercial Electric Aircraft Market - Global Forecast 2026-2032"))
    assert same_issuer(page, first) == "credited firm"
    assert same_issuer(first, second) == "credited firm", "Two carried releases that credit one firm"


@pytest.mark.parametrize(("page", "release"), [
    # Read as letters run together, "spacesolar" is inside "BiLight Space Solar Technology".
    (item("Developing and commercialising Space-Based Solar Power", "https://www.spacesolar.co.uk/"),
     item("2026 Japan Photovoltaic Expo Wraps Up, BiLight Space Solar Technology Powers AI Applications",
          "https://finance.yahoo.com/sectors/energy/articles/2026-japan-photovoltaic-expo-wraps-103700684.html",
          "TOKYO, Nov. 1, 2026 /PRNewswire/ -- BiLight Space Solar Technology, a global leader in flexible solar")),
    # market.us is not "Market": a short label is a word.
    (item("Quantum Key Distribution (QKD) Market Size | CAGR of 30%", "https://market.us/report/quantum-key-distribution-qkd-market"),
     item("The Rise of Quantum Key Distribution Market: A $2.63 billion Industry - Market",
          "https://finance.yahoo.com/news/rise-quantum-key-distribution-market-133000854.html",
          "DELRAY BEACH, Fla., Oct. 1, 2026 /PRNewswire/ -- According to Market Research Future, the market size")),
    # ...and so it is inside a longer name set off at the end of a headline.
    (item("Developing and commercialising Space-Based Solar Power", "https://www.spacesolar.co.uk/"),
     item("Orbital Power Expo Wraps Up in Tokyo | BiLight Space Solar Technology",
          "https://finance.yahoo.com/sectors/energy/articles/orbital-power-expo-wraps-up-103700685.html")),
    # The firm named in the middle of the headline, or by a newspaper, is a firm cited.
    (SNS_PAGE, item("SNS Insider Estimate Questioned as Carbon Utilization Market Slows",
                    "https://finance.yahoo.com/news/sns-insider-estimate-questioned-120000505.html")),
    (SNS_PAGE, item("Carbon Dioxide Utilization Market to Reach USD 16.22 Billion | SNS Insider",
                    "https://www.reuters.com/business/energy/carbon-dioxide-utilization-market")),
])
def test_a_firm_not_credited_in_so_many_words_is_not_the_issuer(page, release):
    assert same_issuer(page, release) == ""
    assert same_issuer(release, page) == ""


def test_a_hyphen_inside_a_word_does_not_set_off_a_firm():
    """ "Space-Based" is one word; "2031- Transparency Market Research" ends with a firm."""
    plain = item("Helio Sees New Urgency in Space-Based", "https://finance.yahoo.com/news/helio-sees-120000176.html")
    assert issuer_of(plain) == Issuer(carried=True)
    credited = item("Artificial Photosynthesis Market to Hit USD 200.4 Billion by 2031- Transparency Market Research Inc.",
                    "https://finance.yahoo.com/news/artificial-photosynthesis-market-size-projected-155900146.html")
    assert issuer_of(credited).tail == "transparencymarketresearch"


def test_a_carriers_own_name_after_two_headlines_ties_nothing():
    first = item("A First Company Announces a Supply Agreement | Markets Insider",
                 "https://markets.businessinsider.com/news/stocks/a-first-company-announces-1035941226")
    second = item("A Second Company Opens a Plant | Markets Insider",
                  "https://markets.businessinsider.com/news/stocks/a-second-company-opens-1035941227")
    assert same_issuer(first, second) == ""


def test_two_pages_on_one_publishers_site_are_the_site_shares_to_count():
    other = item("DNA Data Storage Market Size, Share & Industry Trends, 2035",
                 "https://www.snsinsider.com/reports/dna-data-storage-market-6505")
    assert same_issuer(SNS_PAGE, other) == ""


def test_the_issuers_group_is_reached_through_the_listed_results():
    assert issuer_mates(HELIO_INSIDER, [HELIO_REWRITTEN, HELIO_YAHOO]) == [0, 1], "Tied to the first through the second"
    assert issuer_mates(HELIO_INSIDER, [HELIO_REWRITTEN]) == [], "Nothing listed states both the symbol and the name"
    assert issuer_mates(HELIO_REWRITTEN, [HELIO_INSIDER, SNS_PAGE, HELIO_YAHOO, HELIO_OTC]) == [0, 2, 3]
    assert issuer_mates(SNS_PAGE, [HELIO_YAHOO, HELIO_TITAN]) == []
    assert issuer_mates(HELIO_YAHOO, []) == []


# ── the run of 2026-11-15 ──────────────────────────────────────────────────
#
# The three Helio releases as that run listed them, each with the part of its
# saved excerpt that matters. No excerpt opens with the wire's mark and the
# company's name: two are from the middle of a release, and the third opens
# with a date and the Board.

_RUN_OF_2026_11_15 = (
    ("Helio Positions Itself to Lead the Emerging Space-Based Solar Power (SBSP) Industry | Markets Insider",
     "https://markets.businessinsider.com/news/stocks/helio-positions-itself-to-lead-the-emerging-space-based-solar-power"
     "-sbsp-industry-1035706928",
     "Investment Takeaway The critical question is no longer whether SBSP is viable—but who can execute. Helio believes "
     "that its proven track record providing solutions to the space industry positions the Company to accelerate SBSP "
     "commercialization of space-based solar power and reduce program risk."),
    ("Helio Sees Space-Based Solar Power Gaining Urgency as Industry Leaders and Governments Highlight Orbital Energy "
     "Future | HLEO - Helio Corporation | News",
     "https://www.otcmarkets.com/stock/HLEO/news/Helio-Sees-Space-Based-Solar-Power-Gaining-Urgency-as-Industry-Leaders-and-"
     "Governments-Highlight-Orbital-Energy-Future?id=509342",
     '"As energy demand grows on Earth and in space, space-based solar power is moving from concept to execution," said '
     "Ed Cabrera, Chief Executive Officer of Helio Corporation. [...] intensifies, Helio believes successful commercial "
     "deployment of space-based solar power will depend on systems engineering excellence."),
    ("Helio Corporation (HLEO) enters space-based solar power | HLEO Stock News",
     "https://www.stocktitan.net/news/HLEO/helio-corporation-announces-strategic-entry-into-space-based-solar-80m3vj4edump.html",
     "Helio’s SBSP strategy is intended to address the growing global demand for clean, secure, and resilient baseload "
     "power. [...] Berkeley, California, Jan. 06, 2026 (GLOBE NEWSWIRE) -- On January 6, 2026, the Board of Directors (the "
     "“Board”) of Helio Corporation (OTCID: HLEO) (“Helio” or the “Company”) today announced a strategic "
     "initiative to develop and commercialize space-based solar power systems."),
)


def test_the_three_releases_of_that_run_are_one_issuers():
    insider, otc, titan = (item(*row) for row in _RUN_OF_2026_11_15)
    assert issuer_of(insider) == Issuer(carried=True, tail="marketsinsider"), "Nothing in it says who issued it"
    assert (issuer_of(otc).symbols, issuer_of(otc).names) == ({"HLEO"}, {("helio",)})
    assert (issuer_of(titan).symbols, issuer_of(titan).names) == ({"HLEO"}, {("helio",)})
    assert same_issuer(insider, otc) == "named in headline" and same_issuer(otc, titan) == "same symbol"
    # In the order the run listed them: the third finds the other two.
    assert issuer_mates(otc, [insider]) == [0]
    assert issuer_mates(titan, [insider, otc]) == [0, 1]


def test_that_runs_third_release_now_waits_for_a_slot_nothing_else_fills():
    from datetime import date

    from academic_agent.source_pipeline import _collect_domain
    from tests.test_source_pipeline import MatchingCrossref

    def collect(results, maximum):
        return _collect_domain(
            "market", ["q"], lambda query: {"organic": results}, MatchingCrossref(), lambda url: (True, ""),
            date(2026, 11, 15), "space-based solar power", minimum_sources=0, maximum_sources=maximum)

    releases = [_result(*row) for row in _RUN_OF_2026_11_15]
    report = _result("Space-Based Solar Power Market Size & Share Overview, 2041",
                     "https://www.mordorintelligence.com/industry-reports/space-based-solar-power-market",
                     "Commercial uptake of space-based solar power is climbing at a 16.12% CAGR as independent power producers, "
                     "telecom operators, and agri-tech firms evaluate orbital power purchase agreements.")
    sources, audits = collect([*releases, report], 3)
    assert [site_of(str(s.url)) for s in sources] == ["businessinsider.com", "otcmarkets.com", "mordorintelligence.com"]
    assert _reasons(audits) == [
        f"deferred (issuer share: 2 listed sources have its issuer): {_RUN_OF_2026_11_15[2][0]!r}"
    ]
    # With nothing else to list, all three are listed, as before.
    sources, _audits = collect(releases, 8)
    assert [site_of(str(s.url)) for s in sources] == ["businessinsider.com", "otcmarkets.com", "stocktitan.net"]


# ── the market stage ───────────────────────────────────────────────────────

_HELIO_RELEASES = (
    ("Helio Sees Space-Based Solar Power Commercialization Gaining Urgency",
     "https://finance.yahoo.com/news/helio-sees-space-based-solar-120000176.html", _HELIO_OPENING),
    ("Helio Corporation Secures New Aerospace Contracts for Commercialization | HLEO Stock News",
     "https://www.stocktitan.net/news/HLEO/helio-corporation-secures-new-aerospace-and-research-contracts.html",
     "The contracts expand the revenue pipeline and advance commercialization of the company's space power hardware, "
     "with deliveries to two aerospace customers scheduled over the next four quarters."),
    ("Helio Highlights New Age Space Race as Space Based Solar Power Moves from Prototype | Markets Insider",
     "https://markets.businessinsider.com/news/stocks/helio-highlights-new-age-space-race-1035941226",
     "rising demand from artificial intelligence, electrification, and industrial growth. The company remains focused "
     "on commercialization of grid scale energy delivery to terrestrial customers."),
)


def _helio(index: int) -> dict:
    title, link, snippet = _HELIO_RELEASES[index]
    return _result(title, link, snippet)


def test_a_third_release_by_one_issuer_waits_while_another_source_takes_the_slot():
    """Space-based solar power, 2026-11-15: three Helio releases on three hosts held three of eight slots."""
    sources, audits = _collect({"q": [_helio(0), _helio(1), _helio(2), _news(1)]}, maximum=3)
    assert [site_of(str(s.url)) for s in sources] == ["yahoo.com", "stocktitan.net", "reuters.com"]
    assert MARKET_SOURCES_PER_ISSUER == 2
    assert _reasons(audits) == [
        f"deferred (issuer share: 2 listed sources have its issuer): {_HELIO_RELEASES[2][0]!r}"
    ]


def test_a_waiting_release_fills_a_slot_nothing_else_took():
    """The share is a preference, not a ban: three different releases are three sources."""
    sources, audits = _collect({"q": [_helio(0), _helio(1), _helio(2)]}, maximum=4)
    assert [s.source_id for s in sources] == ["M1", "M2", "M3"]
    assert site_of(str(sources[2].url)) == "businessinsider.com"
    assert audits[-1].query == "[Deferred-Promotion]" and audits[-1].accepted_source_ids == ["M3"]


def test_results_that_state_no_issuer_are_never_held_for_one():
    hosts = ("www.reuters.com", "www.ft.com", "www.bloomberg.com", "www.wsj.com", "apnews.com")
    sources, audits = _collect({"q": [_news(index, host) for index, host in enumerate(hosts, start=1)]})
    assert len(sources) == 5 and _reasons(audits) == []


def test_a_result_within_every_share_is_promoted_before_one_past_its_issuers():
    """A report held by the report cap, from a new site, outranks the issuer's third release."""
    report = "Test commercialization topic Market Size, Share & Trends Report 203{}"
    hosts = ("grandviewresearch.com", "mordorintelligence.com", "precedenceresearch.com", "marketsandmarkets.com",
             "snsinsider.com")
    reports = [_result(report.format(index), f"https://www.{host}/reports/topic-market",
                       "The developer said its commercialization milestone was a signed offtake agreement with a "
                       f"regional utility, covering forty megawatts of capacity. Edition {index}.")
               for index, host in enumerate(hosts, start=1)]
    sources, _audits = _collect({"q": [_helio(0), _helio(1), _helio(2), *reports]}, maximum=7)
    assert [site_of(str(s.url)) for s in sources] == [
        "yahoo.com", "stocktitan.net", "grandviewresearch.com", "mordorintelligence.com",
        "precedenceresearch.com", "marketsandmarkets.com", "snsinsider.com"]


def test_a_query_at_its_source_limit_promotes_no_more_for_an_issuer_at_its_share():
    """A release held for its issuer is charged to its query, as one held for its site is.

    The query has supplied its three; with five slots still empty, the held
    release stays out. Uncharged, the first query to meet a busy issuer would
    supply every slot left.
    """
    sources, audits = _collect({"q1": [_helio(0), _helio(1), _helio(2), _news(1)]}, maximum=8, query_limits={"q1": 3})
    assert [site_of(str(s.url)) for s in sources] == ["yahoo.com", "stocktitan.net", "reuters.com"]
    assert _reasons(audits) == [
        f"deferred (issuer share: 2 listed sources have its issuer): {_HELIO_RELEASES[2][0]!r}"
    ]
    # One more allowed from the query, and the held release takes a slot.
    sources, audits = _collect({"q1": [_helio(0), _helio(1), _helio(2), _news(1)]}, maximum=8, query_limits={"q1": 4})
    assert [site_of(str(s.url)) for s in sources] == ["yahoo.com", "stocktitan.net", "reuters.com", "businessinsider.com"]


def test_a_later_pass_counts_the_issuers_releases_an_earlier_one_kept():
    kept, _audits = _collect({"q": [_helio(0), _helio(1)]})
    assert len(kept) == 2
    later, audits = _collect({"company news": [_helio(2), _news(1)]}, maximum=1, market_kept=kept)
    assert [site_of(str(s.url)) for s in later] == ["reuters.com"]
    assert _reasons(audits) == [
        f"deferred (issuer share: 2 listed sources have its issuer): {_HELIO_RELEASES[2][0]!r}"
    ]


def test_the_site_share_is_named_when_both_shares_are_full():
    """Two Helio releases on Yahoo, then a third there: the older, plainer reason is the one given."""
    third = _result("Helio Positions Itself to Lead Space-Based Solar Power Commercialization",
                    "https://finance.yahoo.com/news/helio-positions-itself-lead-emerging-143000296.html",
                    _HELIO_OPENING.replace("today reaffirmed", "today set out"))
    second = _result("Helio Highlights New Age Space Race for Commercialization",
                     "https://finance.yahoo.com/news/helio-highlights-age-space-race-122200505.html",
                     _HELIO_OPENING.replace("today reaffirmed", "today highlighted"))
    sources, audits = _collect({"q": [_helio(0), second, third, _news(1)]}, maximum=3)
    assert [site_of(str(s.url)) for s in sources] == ["yahoo.com", "yahoo.com", "reuters.com"]
    assert _reasons(audits) == [f"deferred (site share: yahoo.com already holds 2): {third['title']!r}"]


def test_ordinary_news_is_still_admitted_in_order():
    sources, _audits = _collect({"q": [_news(1), _helio(0), _news(2, "www.ft.com")]})
    assert [s.source_id for s in sources] == ["M1", "M2", "M3"]
    assert sources[0].title == _news_title(1)
