"""Offline delivery regressions for negated retrieval terms and host provenance."""

from datetime import date
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from academic_agent.evidence import EvidenceSource
from academic_agent.language import TopicSearchPlan
from academic_agent import source_pipeline as pipeline


_TOPIC = "Battery-free RFID temperature sensing tags for cold-chain logistics"
_DATE = date(2026, 9, 29)
# Public titles observed in the saved 2026-09-29 source artifact. These are
# regression controls, not a new independent relevance or provenance benchmark.
_OFF_TOPIC = (
    "WO2026016605 HIGH-TEMPERATURE SODIUM ION ELECTROLYTE AND HIGH-SAFETY SODIUM ION BATTERY",
    "HIGH-VOLTAGE ENERGY STORAGE POWER SYSTEM AND BATTERY CLUSTER STATE PRECISE SENSING METHOD THEREOF",
)
_ON_TOPIC = (
    "Semi-active RFID e-tag with temperature sensor",
    "Active RFID based wireless temperature data collection system and method",
    "Passive RFID temperature sensors with liquid crystal elastomers",
    "Battery-free wireless tag",
)


def _web_rows(titles, *, host="patents.google.com"):
    return [
        {
            "title": title,
            "link": f"https://{host}/patent/US20260000{index}A1",
            "snippet": (
                f"{title}. This saved search extract describes the device and "
                "its operating method; legal scope still requires the full claims."
            ),
        }
        for index, title in enumerate(titles, 1)
    ]


def _market_row(host, path="/news/product", *, item=None):
    """The row under test, or with ``item`` a filler about something else.

    A filler has its own headline and wording. With the row's own, the three
    market rows were one headline and one excerpt on three hosts, which the
    market stage now takes for copies of one story and lists once.
    """
    if item is not None:
        return {
            "title": f"RFID temperature sensing {item} enters cold-chain service",
            "link": f"https://{host}{path}",
            "snippet": (
                f"A logistics operator reports on RFID temperature sensing {item} "
                "in its cold-chain network, with the number of sites equipped and "
                "the readings collected over the first season of operation."
            ),
        }
    return {
        "title": "RFID temperature sensing product announcement",
        "link": f"https://{host}{path}",
        "snippet": (
            "The announcement describes battery-free RFID temperature sensing "
            "tags for cold-chain logistics, including deployment and product "
            "availability. This extract does not verify the article's authorship."
        ),
    }


def _collect(*, topic=_TOPIC, patent_titles=(), market_rows=(), lens_titles=()):
    academic = EvidenceSource(
        source_id="A1",
        title=topic,
        url="https://example.org/paper",
        publisher="Offline Journal",
        accessed_date=_DATE,
        source_type="academic_paper",
        credibility_tier="medium",
        credibility_reason="Offline academic control; no provider request.",
        evidence_summary=f"{topic}. " * 5,
        summary_source="abstract",
        citation_count=1,
    )
    patents = _web_rows(patent_titles)
    markets = [
        *market_rows,
        _market_row("reuters.com", "/technology/rfid-one", item="reader network"),
        _market_row("reuters.com", "/technology/rfid-two", item="pallet tag fleet"),
    ]

    def search(query):
        if any(host in query for host in (
            "patents.google.com", "patentscope.wipo.int", "worldwide.espacenet.com"
        )):
            return {"organic": patents}
        return {"organic": markets}

    lens_records = [
        {
            "lens_id": f"offline-{index}",
            "biblio": {"invention_title": [{"text": title, "lang": "EN"}]},
            "abstract": [{"text": f"{title}. " * 4, "lang": "EN"}],
        }
        for index, title in enumerate(lens_titles, 1)
    ]
    lens = SimpleNamespace(
        api_key="offline-placeholder" if lens_titles else "",
        search=lambda *args, **kwargs: lens_records,
    )
    # Only the unrelated academic lane and language planner are stubbed. Patent
    # and market construction, admission, post-filtering and serialization are
    # real, so a corrected helper that never reaches delivery cannot pass.
    with (
        patch("academic_agent.language.plan_topic_search",
              return_value=TopicSearchPlan(search_topic=topic)),
        patch.object(pipeline, "_collect_academic_primary",
                     return_value=([academic], [])),
        patch("socket.socket.connect", side_effect=AssertionError("network forbidden")),
    ):
        return pipeline.collect_source_collection(
            topic,
            searcher=search,
            crossref=object(),
            openalex=object(),
            s2=object(),
            lens=lens,
            url_checker=lambda url: (True, ""),
            minimum_sources=1,
            maximum_sources=8,
            accessed_date=_DATE,
        ).model_dump(mode="json")


class SourceRelevanceProvenanceRegressionTests(TestCase):
    def test_web_patents_do_not_match_the_negated_battery_noun(self):
        """Battery plus temperature/sensing admitted two unrelated WIPO titles."""
        for topic in (
            _TOPIC,
            "battery-free RFID temperature sensing for cold-chain logistics",
            _TOPIC.replace("Battery-free", "Battery free"),
            _TOPIC.replace("Battery-free", "Battery\u2011free"),
        ):
            with self.subTest(topic=topic):
                delivered = _collect(topic=topic, patent_titles=(*_ON_TOPIC, *_OFF_TOPIC))
                patents = delivered["patent_sources"]
                self.assertEqual({row["title"] for row in patents}, set(_ON_TOPIC))
                self.assertEqual([row["source_id"] for row in patents], ["P1", "P2", "P3", "P4"])
                self.assertTrue(all(row["summary_source"] == "search_snippet" for row in patents))
                rejections = " ".join(
                    reason for audit in delivered["audit"]
                    for reason in audit["rejected_reasons"]
                )
                for title in _OFF_TOPIC:
                    self.assertIn(title, rejections)
                self.assertFalse(delivered["failed_domains"])

    def test_lens_patents_do_not_restore_the_same_negated_noun_match(self):
        """The primary patent adapter must not reintroduce the web-filter defect."""
        titles = (
            "Semi-active RFID temperature sensor",
            "Active RFID temperature data collection",
            *_ON_TOPIC[2:],
        )
        delivered = _collect(lens_titles=(*titles, *_OFF_TOPIC))
        self.assertEqual(
            {row["title"] for row in delivered["patent_sources"]}, set(titles)
        )
        self.assertTrue(all(
            row["summary_source"] == "abstract" for row in delivered["patent_sources"]
        ))

    def test_sparse_collection_does_not_backfill_the_rejected_patents(self):
        """The final min_keep fallback must not resurrect title-admission failures."""
        delivered = _collect(patent_titles=_OFF_TOPIC)
        self.assertEqual(delivered["patent_sources"], [])

    def test_non_negated_battery_topics_keep_battery_patents(self):
        """A battery-free repair must not become a ban on real battery inventions."""
        for topic, title in (
            ("Sodium ion battery electrolytes", _OFF_TOPIC[0]),
            ("Battery cluster state sensing", _OFF_TOPIC[1]),
        ):
            with self.subTest(topic=topic):
                delivered = _collect(topic=topic, patent_titles=(title,))
                self.assertEqual([s["title"] for s in delivered["patent_sources"]], [title])

    def test_separate_unnegated_battery_mention_still_supplies_a_match(self):
        """Protect the negated occurrence, not every battery word in a mixed topic."""
        title = "Battery temperature monitor"
        delivered = _collect(
            topic="Battery-free RFID tags with battery temperature monitoring",
            patent_titles=(title,),
        )
        self.assertEqual([s["title"] for s in delivered["patent_sources"]], [title])

    def test_compound_only_topics_and_unicode_titles_remain_admissible(self):
        """A complete battery-free phrase must survive without another topic match."""
        for separator in ("-", " ", "\u2010", "\u2011", "\u2013"):
            with self.subTest(separator=separator):
                title = _ON_TOPIC[-1].replace("-", separator)
                delivered = _collect(
                    topic=f"Battery{separator}free",
                    patent_titles=(title, *_OFF_TOPIC),
                )
                self.assertEqual(
                    [s["title"] for s in delivered["patent_sources"]], [title]
                )

    def test_secondary_financial_hosts_reach_delivery_as_news(self):
        """Yahoo syndication and Investing news were labelled first-party companies."""
        for host in (
            "finance.yahoo.com", "uk.finance.yahoo.com", "investing.com",
            "www.investing.com", "uk.investing.com",
        ):
            with self.subTest(host=host):
                delivered = _collect(market_rows=(_market_row(host),))
                row = next(s for s in delivered["market_sources"] if host in s["url"])
                self.assertEqual(row["source_type"], "reputable_news")
                self.assertEqual(row["credibility_tier"], "medium")
                self.assertEqual(row["summary_source"], "search_snippet")
                self.assertIn(host, row["credibility_reason"])
                self.assertIn("syndicat", row["credibility_reason"].lower())
                self.assertNotIn("First-party company page", row["credibility_reason"])

    def test_deceptive_host_and_path_do_not_prove_first_party_status(self):
        """News paths and trusted-looking host substrings are not authorship evidence."""
        for host, path in (
            ("finance.yahoo.com.attacker.example", "/news/company-update"),
            ("investing.com.attacker.example", "/news/company-update"),
            ("notfinance.yahoo.com", "/news/company-update"),
            ("notinvesting.com", "/news/company-update"),
            ("attacker.example", "/news/finance.yahoo.com/company-update"),
            ("attacker.example", "/press/investing.com/company-update"),
            ("batteryco.com", "/news/commercial-deployment"),
        ):
            with self.subTest(host=host, path=path):
                delivered = _collect(market_rows=(_market_row(host, path),))
                row = next(s for s in delivered["market_sources"] if host in s["url"])
                # Retain the legacy candidate category, not its old claim of
                # verified ownership. Known secondary hosts take a separate path.
                self.assertEqual(row["source_type"], "company_disclosure")
                self.assertEqual(row["credibility_tier"], "medium")
                self.assertIn("unverified", row["credibility_reason"].lower())
                self.assertNotIn("First-party company page", row["credibility_reason"])
                self.assertNotIn("authoritative", row["credibility_reason"].lower())

    def test_query_text_cannot_supply_a_company_content_path(self):
        """An arbitrary query string containing /news/ must not admit a host."""
        delivered = _collect(market_rows=(
            _market_row("attacker.example", "/catalog?next=/news/finance.yahoo.com"),
        ))
        self.assertFalse(any("attacker.example" in s["url"] for s in delivered["market_sources"]))

    def test_press_wire_disclosure_provenance_is_preserved(self):
        """Known wire announcements remain attributed disclosures, not editorial news."""
        delivered = _collect(market_rows=(_market_row("businesswire.com"),))
        row = next(s for s in delivered["market_sources"] if "businesswire.com" in s["url"])
        self.assertEqual(row["source_type"], "company_disclosure")
        self.assertIn("wire service", row["credibility_reason"])
