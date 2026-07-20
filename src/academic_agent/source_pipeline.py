"""Deterministic source retrieval and validation before LLM analysis."""

import html
import json
import os
import re
import time
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Callable, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

from academic_agent.evidence import EvidenceSource, _WEIGHT_PROFILES, check_public_url

from academic_agent.source_clients import (
    SourceCollectionError,
    _TOPIC_PREPOSITIONS,
    _PM_MONTH,
    _PATENT_STOPWORDS, _PATENT_MAX_QUERY_WORDS, _patent_keywords,
    _http_fetch_json, _topic_core_phrase,
    SerperClient, OpenAlexClient, SemanticScholarClient,
    PubMedClient, ArxivClient, LensPatentClient, CrossrefClient,
)


Domain = Literal["academic", "patent", "market"]

# ── Weight profile detection ──────────────────────────────────────────────────
# Substring markers are matched against the lower-cased English topic.
# Biomedical is checked first (more specific); industrial is the default.
_BIOMEDICAL_MARKERS: tuple[str, ...] = (
    "drug ", "therapy", "vaccine", "clinical trial", "pharmaceutical",
    "diagnostic", "implant", "surgical", "gene editing", "cell therapy",
    "gene therapy", "medical device", "antibody", "in vitro", "in vivo",
    "oncology", "cancer treatment", "immunotherapy",
    # Bioprocess / cellular agriculture — manufacturing maturity is the key gate
    "cultivated meat", "cultured meat", "cell-based meat", "cellular agriculture",
    "tissue engineering", "stem cell", "bioprocessing", "bioreactor scale",
    "fermentation scale", "cell culture scale",
)
_MATERIAL_MARKERS: tuple[str, ...] = (
    "catalyst", "catalysis", "polymer", "thin film", "nanoparticle",
    "nanomaterial", "graphene", "ceramic ", "composite material",
    "deposition", "crystal structure", "synthesis route",
    "perovskite", "solar cell", "photovoltaic", "semiconductor",
    "electrode", "electrolyte", "superconductor", "alloy", "coating",
    "metamaterial", "2d material", "carbon nanotube",
    # Battery / energy-storage materials — compound stems so generic "battery"
    # in e.g. "battery management system" does not trigger material_science.
    "solid-state batter", "lithium-ion batter", "lithium metal batter",
    "sodium-ion batter", "sodium batter", "all-solid-state",
    "fuel cell", "flow batter", "redox flow",
)
_CLEAN_TECH_MARKERS: tuple[str, ...] = (
    "renewable energy", "wind turbine", "offshore wind", "onshore wind",
    "green hydrogen", "hydrogen production", "hydrogen storage",
    "carbon sequestration", "direct air capture",
    "grid storage", "grid-scale storage", "energy storage system",
    "smart grid", "microgrid", "power-to-gas", "electrolysis",
    "geothermal", "tidal energy", "wave energy",
    "electric vehicle charging", "ev charging", "vehicle-to-grid",
)
_SOFTWARE_AI_MARKERS: tuple[str, ...] = (
    "machine learning", "deep learning", "neural network",
    "large language model", "llm ", "generative ai", "foundation model",
    "natural language processing", "nlp ", "computer vision",
    "reinforcement learning", "transformer model",
    "recommendation system", "saas platform", "api platform",
    "software as a service", "cloud platform",
)


def _detect_weight_profile(topic: str) -> str:
    """Return the scoring weight profile name for an English topic string."""
    t = topic.lower()
    if any(m in t for m in _BIOMEDICAL_MARKERS):
        return "biomedical"
    if any(m in t for m in _MATERIAL_MARKERS):
        return "material_science"
    if any(m in t for m in _CLEAN_TECH_MARKERS):
        return "clean_tech"
    if any(m in t for m in _SOFTWARE_AI_MARKERS):
        return "software_ai"
    return "industrial"
SearchFunction = Callable[[str], dict[str, Any]]
UrlChecker = Callable[[str], tuple[bool, str]]

_DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_TAG_PATTERN = re.compile(r"<[^>]+>")
_WORD_PATTERN = re.compile(r"[a-z0-9]+")
_TOPIC_STOPWORDS = {
    "analysis",
    "application",
    "applications",
    "commercial",
    "commercialization",
    "deployment",
    "research",
    "system",
    "systems",
    "technology",
    "technologies",
    "test",
    "topic",
}
# Prepositions that mark the end of the core noun phrase in a topic string.
# "of" is intentionally excluded: "large-scale manufacturing OF perovskite solar cells"
# — "of" links the activity to the technology, so the technology words must be kept.
_AUTHORITATIVE_RESEARCH_DOMAINS = {
    "iea.org",
    "iaea.org",          # International Atomic Energy Agency (UN)
    "wri.org",
    "weforum.org",       # World Economic Forum
    "oecd.org",          # OECD
    "irena.org",         # International Renewable Energy Agency
    "energy.gov",        # US DOE (caught by .gov rule too, but explicit for clarity)
}
_NONPROFIT_RESEARCH_DOMAINS = {
    "carbon180.org",
    "drawdown.org",
    "rmi.org",           # Rocky Mountain Institute
    "energypolicy.columbia.edu",
    # Solar / clean-energy industry associations — publish authoritative market data
    "seia.org",              # Solar Energy Industries Association (US)
    "solarpowereurope.org",  # SolarPower Europe
    "solarenergyuk.net",     # Solar Energy UK
}
_THINK_TANK_DOMAINS = {
    "itif.org",          # Information Technology and Innovation Foundation
    "brookings.edu",     # Brookings Institution
    "rand.org",          # RAND Corporation
    "pewresearch.org",   # Pew Research Center
    "wilsoncenter.org",  # Wilson Center
    "csis.org",          # Center for Strategic and International Studies
    "chathamhouse.org",  # Chatham House
    "piie.com",          # Peterson Institute for International Economics
}
_PATENT_HOSTS = {
    "patents.google.com",
    "patentscope.wipo.int",
    "worldwide.espacenet.com",
    "patents.justia.com",      # large US patent full-text database
    "lens.org",                # free open patent aggregator (>120 M records)
}
# Publishers/journal-name fragments known to appear on Beall's predatory list or
# widely flagged by the academic community.  Matched case-insensitively as
# substrings of the publisher field returned by search APIs.
_PREDATORY_PUBLISHER_FRAGMENTS: frozenset[str] = frozenset({
    "fringe global",
    "omics publishing",
    "omics international",
    "scientific research publishing",
    "scirp",
    "hindawi",                     # acquired many low-quality journals post-2021
    "science publishing group",
    "american journal of",         # many predatory clones use this prefix
    "international journal of innovation",
    "global journal of",
    "world journal of",
    "european journal of scientific research",
    "ijsrp",
    "iiste",
    "academe research journals",
    "sciencepg",
    "openscience",
    "gavin publishers",
    "lupine publishers",
    "peertechz",
    "crimson publishers",
    "scholars.direct",
    "annex publishers",
    "austin publishing group",
    "symbiosis online publishing",
    "juniper publishers",
    "remedy publications",
    "pulsus group",
    "innovationinfo",
})

# Legitimate journals whose names contain a predatory fragment — checked first
# to prevent false positives (e.g. "american journal of medicine" starts with
# the "american journal of" predatory-clone prefix).
_PREDATORY_PUBLISHER_WHITELIST: frozenset[str] = frozenset({
    "american journal of medicine",
    "american journal of epidemiology",
    "american journal of public health",
    "american journal of respiratory",
    "american journal of clinical",
    "american journal of obstetrics",
    "american journal of surgery",
    "american journal of cardiology",
    "american journal of psychiatry",
    "american journal of roentgenology",
    "american journal of gastroenterology",
    "american journal of kidney",
    "american journal of hematology",
    "american journal of sports medicine",
    "american journal of neuroradiology",
    "american journal of human genetics",
    "american journal of botany",
    "american journal of physics",
    "american journal of mathematics",
    "american journal of nursing",
    "american journal of law",
})

# Borderline publishers: flagged for volume/speed issues but operate many
# legitimate peer-reviewed journals — downgrade to "medium" rather than "low".
_BORDERLINE_PUBLISHER_FRAGMENTS: frozenset[str] = frozenset({
    "mdpi",   # some high-quality SCI-indexed titles (Viruses, Molecules, etc.)
})


def _is_predatory_publisher(publisher: str) -> bool:
    """Return True if the publisher name is definitively predatory (→ low tier)."""
    lowered = publisher.lower()
    if any(safe in lowered for safe in _PREDATORY_PUBLISHER_WHITELIST):
        return False
    return any(frag in lowered for frag in _PREDATORY_PUBLISHER_FRAGMENTS)


def _is_borderline_publisher(publisher: str) -> bool:
    """Return True for borderline publishers that warrant medium (not low) tier."""
    lowered = publisher.lower()
    return any(frag in lowered for frag in _BORDERLINE_PUBLISHER_FRAGMENTS)


_REPUTABLE_NEWS_DOMAINS = {
    "reuters.com",
    "apnews.com",
    "bloomberg.com",
    "ft.com",
    "wsj.com",
    "economist.com",
    "techcrunch.com",
    "axios.com",
}
_INDUSTRY_NEWS_DOMAINS = {
    "autoevolution.com",
    "electrek.co",
    "perovskite-info.com",
    "pv-magazine.com",
    "pv-tech.org",
    "chemengonline.com",
    "biofuelsdigest.com",
    "greencarcongress.com",
    "h2-view.com",
    "quantum-computing-report.com",
    # Oncology / biotech trade press
    "onclive.com",
    "targetedonc.com",
    "cancernetwork.com",
    "cellandgene.com",
    "fiercebiotech.com",
    "fiercepharma.com",
    "healio.com",
    "curetoday.com",
    "medpagetoday.com",
    "pharmavoice.com",
    # General engineering / science news
    "interestingengineering.com",
    # Energy / utility / hydrogen / industrial trade press
    "utilitydive.com",
    "greentechmedia.com",
    "energymonitor.ai",
    "hydrogeninsight.com",
    "rechargenews.com",
    "powermag.com",
    "chemicalprocessing.com",
    "offshore-technology.com",
    # Alternative protein / cultivated meat industry
    "gfi.org",
    "agfundernews.com",
    "foodnavigator.com",
    "fooddive.com",
}
_CONSULTING_RESEARCH_DOMAINS = {
    "mckinsey.com",      # McKinsey & Company
    "bcg.com",           # Boston Consulting Group
    "deloitte.com",
    "accenture.com",
    "kearney.com",
}
_MARKET_RESEARCH_DOMAINS = {
    "gminsights.com",
    "grandviewresearch.com",
    "idtechex.com",
    "marketsandmarkets.com",
    "precedenceresearch.com",
    "mordorintelligence.com",
    "alliedmarketresearch.com",
    "bloombergnef.com",
    "bnef.com",
    "woodmac.com",
    "rystadenergy.com",
    "spglobal.com",
    "inkwoodresearch.com",
    "fortunebusinessinsights.com",
    "transparencymarketresearch.com",
    "researchandmarkets.com",
    "technavio.com",
    "statista.com",
    "reportlinker.com",
    "businessresearchinsights.com",
    "factmr.com",
    "strategicmarketresearch.com",
    "coherentmarketinsights.com",
    "market.us",
    "databridgemarketresearch.com",
    "vantagemarketresearch.com",
    "polarismarketresearch.com",
    "astuteanalytica.com",
    "futuremarketinsights.com",
    "verifiedmarketresearch.com",
    "marketresearchfuture.com",
    "researchnester.com",
}
_ACADEMIC_PUBLISHER_DOMAINS = {
    "doi.org",
    "mdpi.com",
    "nature.com",
    "onlinelibrary.wiley.com",
    "pubmed.ncbi.nlm.nih.gov",
    "pubs.acs.org",
    "pmc.ncbi.nlm.nih.gov",
    "pubs.rsc.org",
    "science.org",
    "sciencedirect.com",
    "springer.com",
}
_PRESS_RELEASE_DOMAINS = {
    "businesswire.com",
    "prnewswire.com",
    "globenewswire.com",
}
_BLOCKED_MARKET_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "medium.com",
    "quora.com",
    "reddit.com",
    "tiktok.com",
    "twitter.com",
    "wikipedia.org",
    "x.com",
    "youtu.be",
    "youtube.com",
    # Low-quality aggregator / curated-list sites that lack primary data
    "wewillcure.com",
    "biospace.com",
    "drugdiscoverytrends.com",
    "pharmiweb.com",
    "drugdiscoverynews.com",
}
_CONTENT_PATH_MARKERS = (
    "/blog/",
    "/company/",
    "/insights/",
    "/investor",
    "/media/",
    "/news/",
    "/press",
    "/research/",
    "/reports/",
    "/analysis/",
    "/publications/",
)
# Sources whose evidence_summary is shorter than this are rejected as too thin
# to provide meaningful content for LLM analysis.
# Set to 100: real Serper snippets are typically 100-160 chars; 150 was too
# aggressive and caused legitimate market sources to be rejected.
# URL query-string parameters that carry no content identity — strip before dedup.
_TRACKING_PARAMS: frozenset[str] = frozenset({
    "srsltid",                                          # Google Search redirect token
    "utm_source", "utm_medium", "utm_campaign",
    "utm_term", "utm_content", "utm_id",
    "gclid", "fbclid", "_ga",                          # ad-click / analytics IDs
    "ref", "referrer", "source",
    "mc_cid", "mc_eid",                                 # Mailchimp
})
_MIN_EVIDENCE_SUMMARY_CHARS = 100
# Minimum number of characters for an abstract/patent body to be considered non-trivial.
_ABSTRACT_MIN_CHARS: int = 20
# Maximum characters kept from abstracts/patent bodies passed to the LLM.
_ABSTRACT_MAX_CHARS: int = 1500
# Papers published within this many days are treated as "recently published" when
# they have zero citations (citation-count lag is expected for brand-new papers).
_ZERO_CITATION_RECENCY_DAYS: int = 90
# Market domain: accept at most this many government/research_institute sources before
# deferring extras so commercial sources have a chance to fill remaining slots.
_MARKET_INSTITUTIONAL_SOFT_CAP = 3
# Market domain: accept at most this many market_report sources before deferring
# extras, so company_disclosure / reputable_news sources have a chance to fill slots.
_MARKET_REPORT_SOFT_CAP = 4
# Maximum Serper results processed per query; limits first-query slot exhaustion
# so subsequent queries in the same domain have a chance to contribute sources.
_SERPER_MAX_RESULTS_PER_QUERY = 8

# Country-specific government TLD patterns (non-.gov forms used internationally).
# Defined at module level to avoid recreating the tuple on every call to
# _market_source_profile(), which is invoked once per candidate URL.
_GOV_SUFFIXES = (
    ".gouv.fr",  # French government
    ".bund.de",  # German federal
    ".go.jp",    # Japanese government
    ".go.kr",    # South Korean government
    ".go.id",    # Indonesian government
    ".govt.nz",  # New Zealand government
    ".gob.es",   # Spanish government
    ".gob.mx",   # Mexican government
    ".gob.ar",   # Argentine government
    ".gov.au",   # Australian government
    ".gov.uk",   # UK government
    ".gov.cn",   # Chinese government
    ".gov.in",   # Indian government
    ".gov.br",   # Brazilian government
    ".gov.sg",   # Singapore government
    ".gov.za",   # South African government
)



class SearchAudit(BaseModel):
    domain: Domain
    query: str
    result_count: int
    accepted_source_ids: list[str] = Field(default_factory=list)
    rejected_reasons: list[str] = Field(default_factory=list)


class SourceCollection(BaseModel):
    topic: str                          # English topic used for search APIs
    display_topic: str = ""             # Original topic in user's language (for report title)
    output_language: str = "English"    # Human-readable language name passed to LLM
    localized_headings: list[str] = Field(default_factory=list)  # Translated section headings
    weight_profile: str = "industrial"  # Scoring weight profile: industrial | biomedical | material_science
    collected_at: datetime
    academic_sources: list[EvidenceSource] = Field(min_length=1)
    patent_sources: list[EvidenceSource] = Field(default_factory=list)
    patent_assignees: list[str] = Field(default_factory=list)  # Deduplicated company/org names from patents
    market_sources: list[EvidenceSource] = Field(default_factory=list)
    academic_queries: list[str] = Field(min_length=1)
    patent_queries: list[str] = Field(min_length=1)
    market_queries: list[str] = Field(min_length=1)
    audit: list[SearchAudit] = Field(default_factory=list)

    def sources_for_prefix(self, prefix: str) -> list[EvidenceSource]:
        mapping = {
            "A": self.academic_sources,
            "P": self.patent_sources,
            "M": self.market_sources,
        }
        try:
            return list(mapping[prefix])
        except KeyError as exc:
            raise ValueError(f"Unsupported source prefix: {prefix}") from exc

    def queries_for_prefix(self, prefix: str) -> list[str]:
        mapping = {
            "A": self.academic_queries,
            "P": self.patent_queries,
            "M": self.market_queries,
        }
        try:
            return list(mapping[prefix])
        except KeyError as exc:
            raise ValueError(f"Unsupported source prefix: {prefix}") from exc

    def crew_inputs(self) -> dict[str, str]:
        from academic_agent.evidence import _REQUIRED_REPORT_HEADINGS

        def dump_sources(sources: list[EvidenceSource]) -> str:
            return json.dumps(
                [source.model_dump(mode="json") for source in sources],
                ensure_ascii=False,
                separators=(",", ":"),
            )

        raw_headings = self.localized_headings or list(_REQUIRED_REPORT_HEADINGS)
        display = self.display_topic or self.topic
        # Append the display topic to the title heading so the LLM writes the
        # full title "# 学术商业化评估：用于骨组织工程的生物3D打印支架" instead of
        # just the bare translated prefix "# 学术商业化评估："
        headings = list(raw_headings)
        if headings and not headings[0].rstrip().endswith(display):
            headings[0] = headings[0].rstrip() + display
        w = _WEIGHT_PROFILES.get(self.weight_profile, _WEIGHT_PROFILES["industrial"])
        weight_profile_str = (
            f"{self.weight_profile} "
            f"(Market {w['market']}% + TRL {w['trl']}% + MRL {w['mrl']}% "
            f"+ Patent {w['patent']}% + Evidence {w['evidence']}%)"
        )
        return {
            "research_topic":  self.topic,
            "display_topic":   display,
            "output_language": self.output_language,
            "localized_headings": "\n".join(headings),
            "weight_profile":  weight_profile_str,
            "academic_sources_json": dump_sources(self.academic_sources),
            "patent_sources_json":   dump_sources(self.patent_sources),
            "patent_assignees_json": json.dumps(self.patent_assignees, ensure_ascii=False),
            "market_sources_json":   dump_sources(self.market_sources),
            "academic_search_queries_json": json.dumps(
                self.academic_queries, ensure_ascii=False
            ),
            "patent_search_queries_json": json.dumps(
                self.patent_queries, ensure_ascii=False
            ),
            "market_search_queries_json": json.dumps(
                self.market_queries, ensure_ascii=False
            ),
        }



# ── Academic dedup thresholds ─────────────────────────────────────────────────
# SequenceMatcher threshold above which two titles are treated as near-duplicates.
_TITLE_NEAR_DUP_THRESHOLD: float = 0.88
# Minimum word-overlap ratio required before running the (slower) SequenceMatcher.
# Titles below this overlap ratio can never reach _TITLE_NEAR_DUP_THRESHOLD.
_TITLE_PREFILTER_OVERLAP: float = 0.4
# Threshold for matching an incoming title against explicitly blocked titles.
# Higher than _TITLE_NEAR_DUP_THRESHOLD: blocked titles are specifically excluded
# for a reason, so a higher confidence is required before treating a near-identical
# title as the same work.
_TITLE_BLOCKED_MATCH_THRESHOLD: float = 0.92

# ── Shared patent-search utilities ───────────────────────────────────────────


def _clean_text(value: str) -> str:
    return " ".join(html.unescape(_TAG_PATTERN.sub(" ", value)).split())


def _safe_summary(snippet: str, title: str) -> str:
    cleaned = _clean_text(snippet)
    if len(cleaned) >= _ABSTRACT_MIN_CHARS:
        return cleaned[:_ABSTRACT_MAX_CHARS]
    return f"Verified search result for the source titled {title}."


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    path = unquote(parsed.path).rstrip("/.,;)>]") or "/"
    # Strip tracking/session parameters that don't identify content (e.g. srsltid,
    # utm_*, gclid) so the same page with different tracking tokens deduplicates.
    if parsed.query:
        kept = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() not in _TRACKING_PARAMS]
        clean_query = urlencode(kept) if kept else ""
    else:
        clean_query = ""
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, clean_query, "")
    )


def _extract_doi(*values: str) -> str | None:
    for value in values:
        match = _DOI_PATTERN.search(value)
        if match:
            return match.group(0).rstrip(".,;:)").lower()
    return None


def _crossref_title(item: dict[str, Any]) -> str:
    titles = item.get("title")
    if isinstance(titles, list) and titles:
        return _clean_text(str(titles[0]))
    return ""


def _title_similarity(left: str, right: str) -> float:
    normalized_left = " ".join(_WORD_PATTERN.findall(left.lower()))
    normalized_right = " ".join(_WORD_PATTERN.findall(right.lower()))
    if not normalized_left or not normalized_right:
        return 0.0
    left_tokens = set(normalized_left.split())
    right_tokens = set(normalized_right.split())
    overlap = len(left_tokens & right_tokens) / max(
        1, min(len(left_tokens), len(right_tokens))
    )
    sequence = SequenceMatcher(None, normalized_left, normalized_right).ratio()
    return max(overlap, sequence)


def _title_matches_topic(title: str, topic: str) -> bool:
    topic_tokens = {
        token
        for token in _WORD_PATTERN.findall(topic.lower())
        if len(token) >= 4 and token not in _TOPIC_STOPWORDS
    }
    if not topic_tokens:
        return True
    title_tokens = set(_WORD_PATTERN.findall(title.lower()))
    overlap = topic_tokens & title_tokens
    # Require ≥2 matching tokens so a single generic word like "manufacturing"
    # or "storage" alone cannot qualify an off-topic paper.
    if len(overlap) < 2:
        return False
    # For specific multi-word topics (≥4 content tokens), guard against
    # coincidental matches where two unrelated compound phrases in the title
    # each contribute one word that happens to appear in the topic.
    # Example failure: "solid electrolyte interphase" + "state of understanding"
    # both contribute to matching the topic "solid-state batteries" via the
    # isolated words "solid" and "state", even though "solid-state" as a
    # compound is absent from the title.
    #
    # Strategy: identify consecutive topic-word pairs where BOTH words are in
    # the overlap set (meaning they exist in the topic AND the title).  These
    # are pairs that must be semantically linked — if they are adjacent in the
    # topic they should also appear adjacent in the title.  If no such
    # adjacent pair exists in the topic (e.g. "direct [air] capture"), skip
    # the adjacency check entirely and accept the match.
    if len(topic_tokens) >= 4:
        topic_word_list = _WORD_PATTERN.findall(topic.lower())
        title_word_list = _WORD_PATTERN.findall(title.lower())
        title_bigrams = {
            (title_word_list[i], title_word_list[i + 1])
            for i in range(len(title_word_list) - 1)
        }
        adjacent_matched_in_topic = [
            (topic_word_list[i], topic_word_list[i + 1])
            for i in range(len(topic_word_list) - 1)
            if topic_word_list[i] in overlap and topic_word_list[i + 1] in overlap
        ]
        if adjacent_matched_in_topic and not any(
            pair in title_bigrams for pair in adjacent_matched_in_topic
        ):
            return False
    return True

def _published_date(item: dict[str, Any]) -> date | None:
    for key in ("published-print", "published-online", "published", "issued"):
        container = item.get(key)
        if not isinstance(container, dict):
            continue
        parts = container.get("date-parts")
        if not isinstance(parts, list) or not parts or not isinstance(parts[0], list):
            continue
        values = parts[0]
        if not values:
            continue
        try:
            year = int(values[0])
            month = int(values[1]) if len(values) > 1 else 1
            day = int(values[2]) if len(values) > 2 else 1
            return date(year, month, day)
        except (TypeError, ValueError):
            continue
    return None


def _resolve_crossref_item(
    result: dict[str, Any],
    crossref: CrossrefClient,
) -> tuple[dict[str, Any] | None, str]:
    title = _clean_text(str(result.get("title", "")))
    link = str(result.get("link", ""))
    snippet = str(result.get("snippet", ""))

    doi = _extract_doi(link, snippet)
    if doi:
        item = crossref.lookup_doi(doi)
        if item and _title_similarity(title, _crossref_title(item)) >= 0.65:
            return item, ""

    for item in crossref.search_title(title):
        if _title_similarity(title, _crossref_title(item)) >= 0.72:
            return item, ""
    last_error = getattr(crossref, "last_error", None)
    detail = f"; last Crossref error: {last_error}" if last_error else ""
    return None, f"no Crossref metadata matched title {title!r}{detail}"


def _academic_source(
    result: dict[str, Any],
    source_id: str,
    crossref: CrossrefClient,
    accessed_date: date,
    research_topic: str,
) -> tuple[EvidenceSource | None, str]:
    item, reason = _resolve_crossref_item(result, crossref)
    if item is None:
        return None, reason
    doi = str(item.get("DOI", "")).lower().strip()
    title = _crossref_title(item)
    publisher = _clean_text(str(item.get("publisher", "")))
    if not doi or not title or not publisher:
        return None, "Crossref record lacks DOI, title, or publisher"
    if not _title_matches_topic(title, research_topic):
        return None, f"Crossref title is not relevant to research topic: {title!r}"

    result_dois = {
        candidate
        for candidate in (
            _extract_doi(str(result.get("link", ""))),
            _extract_doi(str(result.get("snippet", ""))),
        )
        if candidate is not None
    }
    conflicting_dois = sorted(candidate for candidate in result_dois if candidate != doi)
    if conflicting_dois:
        return None, (
            "search result snippet or URL cites a different DOI: "
            + ", ".join(conflicting_dois)
        )

    abstract = item.get("abstract")
    crossref_abstract = _clean_text(abstract) if isinstance(abstract, str) else ""
    snippet = str(result.get("snippet", ""))
    if (
        len(crossref_abstract) < _ABSTRACT_MIN_CHARS
        and re.search(r"(?:https?://)?doi\.org", snippet, flags=re.IGNORECASE)
        and _extract_doi(snippet) is None
    ):
        return None, "search snippet contains a truncated or unverifiable DOI reference"
    if len(crossref_abstract) >= _ABSTRACT_MIN_CHARS:
        evidence_summary = crossref_abstract[:_ABSTRACT_MAX_CHARS]
        summary_basis = "Crossref abstract"
    else:
        evidence_summary = _safe_summary(snippet, title)
        summary_basis = "DOI-consistent search snippet"
    published = _published_date(item)
    if published and published > accessed_date:
        return None, "Crossref publication date is in the future"
    cited = int(item.get("is-referenced-by-count") or 0)
    days_since_pub = (accessed_date - published).days if published else None
    if cited == 0 and (days_since_pub is None or days_since_pub > _ZERO_CITATION_RECENCY_DAYS):
        credibility_tier = "medium"
        age_note = f"{days_since_pub}d since publication" if days_since_pub else "publication date unknown"
        credibility_reason = (
            f"DOI, title, and topic matched; evidence summary uses {summary_basis}. "
            f"0 citations after {age_note} — treat findings conservatively; "
            "independent corroboration recommended."
        )
    else:
        credibility_tier = "high"
        credibility_reason = (
            f"DOI, title, and topic matched; evidence summary uses {summary_basis}."
        )
    if _is_predatory_publisher(publisher):
        credibility_tier = "low"
        credibility_reason = (
            f"Publisher '{publisher}' appears on predatory/low-quality journal lists. "
            "Findings should not be cited without independent corroboration."
        )
    elif _is_borderline_publisher(publisher):
        credibility_tier = "medium"
        credibility_reason = (
            f"Publisher '{publisher}' operates legitimate journals but is flagged for "
            "volume/speed issues; verify the specific journal's impact factor."
        )
    return (
        EvidenceSource(
            source_id=source_id,
            title=title,
            url=f"https://doi.org/{doi}",
            doi=doi,
            publisher=publisher,
            published_date=published,
            accessed_date=accessed_date,
            source_type="academic_paper",
            credibility_tier=credibility_tier,
            credibility_reason=credibility_reason,
            evidence_summary=evidence_summary,
            citation_count=cited if cited > 0 else None,
        ),
        "",
    )




def _topic_tail_words(topic: str, *, min_len: int = 5) -> set[str]:
    """Return substantive words from the tail part of a topic (after first preposition).

    'CAR-T cell therapy for solid tumors' → {'solid', 'tumors'}
    'solid-state batteries for electric vehicles' → {'electric', 'vehicles'}
    'perovskite solar cells' → set()  (no preposition)

    Used to tighten domain-specific filters when a topic has a 'for X' structure
    so that broad-category sources (e.g. generic 'CAR-T market' reports) are
    rejected when the research question is specifically about a sub-indication.
    """
    words = topic.split()
    for i, word in enumerate(words):
        if word.lower() in _TOPIC_PREPOSITIONS:
            tail = " ".join(words[i + 1:])
            return {
                w for w in _WORD_PATTERN.findall(tail.lower())
                if len(w) >= min_len and w not in _TOPIC_STOPWORDS
            }
    return set()


def _openalex_abstract(work: dict[str, Any]) -> str:
    """Reconstruct abstract from OpenAlex inverted-index format."""
    inverted = work.get("abstract_inverted_index")
    if not isinstance(inverted, dict) or not inverted:
        return ""
    positions: dict[int, str] = {}
    for word, pos_list in inverted.items():
        if isinstance(pos_list, list):
            for pos in pos_list:
                positions[int(pos)] = word
    return " ".join(positions[i] for i in sorted(positions))


def _openalex_topic_relevant(work: dict[str, Any], research_topic: str) -> bool | None:
    """Check if a paper's OpenAlex topic labels match the research topic.

    Returns:
        True  — at least one high-confidence topic label overlaps the core phrase
        False — topic labels present but none match (paper is off-topic)
        None  — no topic data; caller should fall back to title-based check
    """
    raw_topics = work.get("topics") or []
    confident_labels = [
        t["display_name"]
        for t in raw_topics
        if isinstance(t, dict) and t.get("display_name")
        and float(t.get("score", 0)) >= 0.5
    ]
    if not confident_labels:
        return None

    core = _topic_core_phrase(research_topic)
    core_words = _WORD_PATTERN.findall(core.lower())
    core_bigrams = {
        f"{core_words[i]} {core_words[i + 1]}"
        for i in range(len(core_words) - 1)
    }
    # Fall back to meaningful single tokens when core is only one word
    core_tokens = {w for w in core_words if len(w) >= 4}

    for label in confident_labels:
        label_words = _WORD_PATTERN.findall(label.lower())
        if core_bigrams:
            label_bigrams = {
                f"{label_words[i]} {label_words[i + 1]}"
                for i in range(len(label_words) - 1)
            }
            if core_bigrams & label_bigrams:
                return True
        elif core_tokens & set(label_words):
            return True

    # Bigram pass missed — OpenAlex may use different term order or phrasing.
    # Use all core words of length >= 8 as anchors (OR logic). This recovers
    # multi-word biomedical topics where several medium-length words are each
    # more informative than the single longest: e.g. "neoantigen"(10) +
    # "vaccines"(8) together cover more synonymous topic phrasings than either
    # alone.  The len >= 8 threshold keeps short generic words like "lithium"(7)
    # out of the anchor set, preserving the solid-state / SEI-paper boundary
    # ("batteries"(9) is still the only anchor, absent from SEI topic labels).
    if core_words:
        anchor_tokens = {w for w in core_words if len(w) >= 8}
        if not anchor_tokens:          # all core words are short — use the longest
            anchor_tokens = {max(core_words, key=len)}
        all_label_words: set[str] = set()
        for label in confident_labels:
            all_label_words.update(_WORD_PATTERN.findall(label.lower()))
        if anchor_tokens & all_label_words:
            return True

    return False


def _academic_source_from_openalex(
    work: dict[str, Any],
    source_id: str,
    accessed_date: date,
    research_topic: str,
    *,
    s2_client: SemanticScholarClient | None = None,
) -> tuple[EvidenceSource | None, str]:
    title = _clean_text(str(work.get("title") or ""))
    doi_raw = str(work.get("doi") or "").lower().strip()
    # OpenAlex returns DOIs as full URLs: "https://doi.org/10.xxxx/..."
    if doi_raw.startswith("https://doi.org/"):
        doi = doi_raw[len("https://doi.org/"):]
    elif doi_raw.startswith("http://doi.org/"):
        doi = doi_raw[len("http://doi.org/"):]
    else:
        doi = doi_raw

    if not title:
        return None, "OpenAlex work has no title"
    # OpenAlex indexes peer review meta-documents (review reports, decision letters,
    # author responses) as separate works.  These are not papers and have no abstract.
    _PEER_REVIEW_PREFIXES = (
        "Review for ", "Decision letter for ", "Author response for ",
        "Review of ", "Peer review of ",
    )
    if any(title.startswith(pfx) for pfx in _PEER_REVIEW_PREFIXES):
        return None, f"OpenAlex peer-review artifact (not a paper): {title!r}"
    if not doi:
        return None, f"OpenAlex work has no DOI: {title!r}"
    topic_match = _openalex_topic_relevant(work, research_topic)
    # Always require a title match regardless of OpenAlex topic classification.
    # topic_match=True only means OpenAlex field labels overlap (e.g. "Manufacturing"),
    # which is too broad — a generic manufacturing paper should not pass title check.
    if not _title_matches_topic(title, research_topic):
        if topic_match is True:
            return None, f"OpenAlex topic matched broadly but title is off-topic: {title!r}"
        elif topic_match is False:
            return None, f"OpenAlex topics indicate off-topic paper: {title!r}"
        else:
            return None, f"OpenAlex title not relevant to topic: {title!r}"

    abstract = _openalex_abstract(work)
    if len(abstract) < 60 and s2_client is not None:
        abstract = s2_client.get_abstract_by_doi(doi)
    if len(abstract) < 60:
        return None, f"abstract too thin ({len(abstract)} chars): {title!r}"

    primary = work.get("primary_location") or {}
    source_meta = primary.get("source") or {}
    publisher = _clean_text(str(source_meta.get("display_name") or ""))
    if not publisher:
        publisher = "OpenAlex"

    pub_date_str = str(work.get("publication_date") or "")
    published: date | None = None
    try:
        if pub_date_str:
            published = date.fromisoformat(pub_date_str[:10])
            if published > accessed_date:
                return None, f"OpenAlex publication date in future: {pub_date_str}"
    except ValueError:
        pass

    cited = int(work.get("cited_by_count") or 0)
    days_since_pub = (accessed_date - published).days if published else None
    # Sparse abstract (60–119 chars) → downgrade to medium credibility so agents
    # treat this source conservatively.  Full abstracts keep "high".
    summary_sparse = len(abstract) < 120
    if summary_sparse:
        credibility_tier: str = "medium"
        credibility_reason = (
            f"OpenAlex record: DOI verified, peer-reviewed journal, "
            f"{cited:,} citations. Brief evidence summary — detailed findings may be limited."
        )
    elif cited == 0 and days_since_pub is not None and days_since_pub <= _ZERO_CITATION_RECENCY_DAYS:
        credibility_tier = "high"
        credibility_reason = (
            "OpenAlex record: DOI verified, peer-reviewed journal. "
            f"Newly published ({days_since_pub}d ago); 0 citations is expected, "
            "not a quality signal."
        )
    elif cited == 0 and (days_since_pub is None or days_since_pub > _ZERO_CITATION_RECENCY_DAYS):
        credibility_tier = "medium"
        age_note = f"{days_since_pub}d since publication" if days_since_pub else "publication date unknown"
        credibility_reason = (
            f"OpenAlex record: DOI verified, peer-reviewed journal. "
            f"0 citations after {age_note} — treat findings conservatively; "
            "independent corroboration recommended."
        )
    else:
        credibility_tier = "high"
        credibility_reason = (
            f"OpenAlex record: DOI verified, peer-reviewed journal, "
            f"{cited:,} citations."
        )
    # Publisher quality override: downgrade regardless of citation count.
    if _is_predatory_publisher(publisher):
        credibility_tier = "low"
        credibility_reason = (
            f"Publisher '{publisher}' appears on predatory/low-quality journal lists. "
            "Findings should not be cited without independent corroboration."
        )
    elif _is_borderline_publisher(publisher):
        credibility_tier = "medium"
        credibility_reason = (
            f"Publisher '{publisher}' operates legitimate journals but is flagged for "
            "volume/speed issues; verify the specific journal's impact factor."
        )
    return (
        EvidenceSource(
            source_id=source_id,
            title=title,
            url=f"https://doi.org/{doi}",
            doi=doi,
            publisher=publisher,
            published_date=published,
            accessed_date=accessed_date,
            source_type="academic_paper",
            credibility_tier=credibility_tier,
            credibility_reason=credibility_reason,
            evidence_summary=abstract[:_ABSTRACT_MAX_CHARS],
            summary_source="abstract",
            citation_count=cited,
        ),
        "",
    )


def _academic_source_from_s2(
    paper: dict[str, Any],
    source_id: str,
    accessed_date: date,
    research_topic: str,
) -> tuple[EvidenceSource | None, str]:
    title = _clean_text(str(paper.get("title") or ""))
    abstract = _clean_text(str(paper.get("abstract") or ""))
    external_ids = paper.get("externalIds") or {}
    doi = str(external_ids.get("DOI") or "").lower().strip()

    if not title:
        return None, "Semantic Scholar paper has no title"
    if not doi:
        return None, f"S2 paper has no DOI: {title!r}"
    if not _title_matches_topic(title, research_topic):
        return None, f"S2 title not relevant to topic: {title!r}"
    if len(abstract) < 60:
        return None, f"S2 abstract too thin ({len(abstract)} chars): {title!r}"

    venue = paper.get("publicationVenue") or {}
    publisher = _clean_text(str(venue.get("name") or ""))
    if not publisher:
        publisher = "Semantic Scholar"

    pub_date_str = str(paper.get("publicationDate") or "")
    pub_year = paper.get("year")
    published: date | None = None
    try:
        if pub_date_str:
            published = date.fromisoformat(pub_date_str[:10])
        elif pub_year:
            published = date(int(pub_year), 1, 1)
        if published and published > accessed_date:
            return None, f"S2 publication date in future: {pub_date_str or pub_year}"
    except (ValueError, TypeError):
        pass

    cited = int(paper.get("citationCount") or 0)
    summary_sparse = len(abstract) < 120
    return (
        EvidenceSource(
            source_id=source_id,
            title=title,
            url=f"https://doi.org/{doi}",
            doi=doi,
            publisher=publisher,
            published_date=published,
            accessed_date=accessed_date,
            source_type="academic_paper",
            credibility_tier="medium" if summary_sparse else "high",
            credibility_reason=(
                f"Semantic Scholar record: DOI verified, peer-reviewed journal, "
                f"{cited:,} citations."
                + (" Brief evidence summary — detailed findings may be limited." if summary_sparse else "")
            ),
            evidence_summary=abstract[:_ABSTRACT_MAX_CHARS],
            summary_source="abstract",
            citation_count=cited,
        ),
        "",
    )


def _academic_source_from_arxiv(
    record: dict[str, Any],
    source_id: str,
    accessed_date: date,
    research_topic: str,
) -> tuple["EvidenceSource | None", str]:
    title    = _clean_text(record.get("title") or "")
    abstract = _clean_text(record.get("abstract") or "")
    arxiv_url = str(record.get("arxiv_url") or "").strip()
    doi       = str(record.get("doi") or "").strip()
    pub_date_str = str(record.get("pub_date") or "")
    authors   = str(record.get("authors") or "arXiv")

    if not title:
        return None, "arXiv record has no title"
    if not arxiv_url and not doi:
        return None, f"arXiv record has no URL: {title!r}"
    if not _title_matches_topic(title, research_topic):
        return None, f"arXiv title not relevant to topic: {title!r}"
    if len(abstract) < 60:
        return None, f"arXiv abstract too thin ({len(abstract)} chars): {title!r}"

    published: date | None = None
    try:
        if pub_date_str:
            published = date.fromisoformat(pub_date_str[:10])
            if published > accessed_date:
                return None, f"arXiv publication date in future: {pub_date_str}"
    except ValueError:
        pass

    # Papers with a published DOI are peer-reviewed; preprints only get medium.
    if doi:
        url = f"https://doi.org/{doi}"
        credibility_tier = "high"
        credibility_reason = (
            f"arXiv preprint with peer-reviewed DOI ({doi})."
        )
    else:
        url = arxiv_url
        credibility_tier = "medium"
        credibility_reason = (
            "arXiv preprint — not yet peer-reviewed; "
            "corroborate with published literature before citing as definitive."
        )

    summary_sparse = len(abstract) < 120
    if summary_sparse:
        credibility_tier = "medium"
        credibility_reason += " Brief abstract."

    return (
        EvidenceSource(
            source_id=source_id,
            title=title,
            url=url,
            doi=doi or None,
            publisher=authors,
            published_date=published,
            accessed_date=accessed_date,
            source_type="academic_paper",
            credibility_tier=credibility_tier,
            credibility_reason=credibility_reason,
            evidence_summary=abstract[:_ABSTRACT_MAX_CHARS],
            summary_source="abstract",
            citation_count=None,
        ),
        "",
    )


def _academic_source_from_pubmed(
    record: dict[str, Any],
    source_id: str,
    accessed_date: date,
    research_topic: str,
) -> tuple["EvidenceSource | None", str]:
    title    = _clean_text(record.get("title") or "")
    abstract = _clean_text(record.get("abstract") or "")
    doi      = str(record.get("doi") or "").lower().strip()
    pmid     = str(record.get("pmid") or "").strip()
    journal  = str(record.get("journal") or "PubMed").strip()
    pub_date_str = str(record.get("pub_date") or "")

    if not title:
        return None, "PubMed record has no title"
    if not (doi or pmid):
        return None, f"PubMed record has no DOI or PMID: {title!r}"
    if not _title_matches_topic(title, research_topic):
        return None, f"PubMed title not relevant to topic: {title!r}"
    if len(abstract) < 60:
        return None, f"PubMed abstract too thin ({len(abstract)} chars): {title!r}"

    published: date | None = None
    try:
        if pub_date_str:
            published = date.fromisoformat(pub_date_str[:10])
            if published > accessed_date:
                return None, f"PubMed publication date in future: {pub_date_str}"
    except ValueError:
        pass

    url = f"https://doi.org/{doi}" if doi else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    summary_sparse = len(abstract) < 120
    return (
        EvidenceSource(
            source_id=source_id,
            title=title,
            url=url,
            doi=doi or None,
            publisher=journal,
            published_date=published,
            accessed_date=accessed_date,
            source_type="academic_paper",
            credibility_tier="medium" if summary_sparse else "high",
            credibility_reason=(
                f"PubMed indexed: peer-reviewed biomedical journal ({journal})."
                + (" Brief evidence summary." if summary_sparse else "")
            ),
            evidence_summary=abstract[:_ABSTRACT_MAX_CHARS],
            summary_source="abstract",
            citation_count=None,
        ),
        "",
    )


def _patent_source_from_lens(
    record: dict[str, Any],
    source_id: str,
    accessed_date: date,
    research_topic: str,
) -> tuple["EvidenceSource | None", str]:
    biblio  = record.get("biblio") or {}
    pub_ref = biblio.get("publication_reference") or {}

    # title is [{text, lang}, ...] inside biblio.invention_title
    title_data = biblio.get("invention_title") or []
    title = ""
    if isinstance(title_data, list):
        for t in title_data:
            if isinstance(t, dict) and t.get("lang", "").upper() == "EN":
                title = _clean_text(t.get("text") or "")
                break
        if not title and title_data:
            first = title_data[0]
            title = _clean_text(first.get("text") or "" if isinstance(first, dict) else str(first))
    else:
        title = _clean_text(str(title_data))

    if not title:
        return None, "Lens patent has no title"

    abstract_data = record.get("abstract") or []
    abstract = ""
    if isinstance(abstract_data, list):
        for a in abstract_data:
            if isinstance(a, dict) and a.get("lang", "").upper() == "EN":
                abstract = _clean_text(a.get("text") or "")
                break
        if not abstract and abstract_data:
            first = abstract_data[0]
            abstract = _clean_text(first.get("text") or "" if isinstance(first, dict) else str(first))
    else:
        abstract = _clean_text(str(abstract_data))

    lens_id     = str(record.get("lens_id") or "").strip()
    doc_num     = str(pub_ref.get("doc_number") or "").strip()
    jurisdiction = str(pub_ref.get("jurisdiction") or record.get("jurisdiction") or "").strip()
    kind        = str(pub_ref.get("kind") or "").strip()
    pub_num     = f"{jurisdiction}{doc_num}{kind}" if doc_num else ""

    if not lens_id:
        return None, f"Lens patent has no lens_id: {title!r}"
    if not _title_matches_topic(title, research_topic):
        return None, f"Lens patent title not relevant to topic: {title!r}"

    parties = biblio.get("parties") or {}
    applicant_list = parties.get("applicants") or []
    applicants: list[str] = []
    if isinstance(applicant_list, list):
        for a in applicant_list:
            if isinstance(a, dict):
                name = ((a.get("extracted_name") or {}).get("value") or "").strip()
                if not name:
                    name = (a.get("name") or "").strip()
                if name:
                    applicants.append(name)
    publisher = "; ".join(applicants[:3]) if applicants else "Patent Applicant"

    pub_date_str = str(pub_ref.get("date") or "").strip()
    published: date | None = None
    try:
        if pub_date_str:
            published = date.fromisoformat(pub_date_str[:10])
    except ValueError:
        pass

    evidence = abstract or f"Patent {pub_num or lens_id}: {title}."
    if len(evidence) < _ABSTRACT_MIN_CHARS:
        evidence = f"Patent record: {title}."

    pub_year = published.year if published else "unknown"
    return (
        EvidenceSource(
            source_id=source_id,
            title=title,
            url=f"https://lens.org/lens/patent/{lens_id}",
            doi=None,
            publisher=publisher,
            published_date=published,
            accessed_date=accessed_date,
            source_type="patent",
            credibility_tier="high",
            credibility_reason=(
                f"Lens.org patent record: {pub_num or lens_id}; "
                f"applicants: {publisher}; year: {pub_year}. "
                "Legal scope requires full claim review."
            ),
            evidence_summary=evidence[:_ABSTRACT_MAX_CHARS],
            citation_count=None,
        ),
        "",
    )


def _publisher_for_host(host: str) -> str:
    labels = host.removeprefix("www.").split(".")
    return labels[-2].replace("-", " ").title() if len(labels) >= 2 else host


def _host_matches(host: str, domains: set[str]) -> bool:
    normalized = host.removeprefix("www.").lower()
    return any(
        normalized == domain or normalized.endswith(f".{domain}")
        for domain in domains
    )


def _market_source_profile(
    canonical_url: str,
    host: str,
) -> tuple[str, str, str] | None:
    if _host_matches(host, _BLOCKED_MARKET_DOMAINS):
        return None
    if _host_matches(host, _ACADEMIC_PUBLISHER_DOMAINS):
        return None
    if _host_matches(host, _AUTHORITATIVE_RESEARCH_DOMAINS):
        return (
            "research_institute",
            "high",
            "Authoritative intergovernmental or independent research institution.",
        )
    if _host_matches(host, _NONPROFIT_RESEARCH_DOMAINS):
        return (
            "research_institute",
            "medium",
            "Specialist nonprofit research or advocacy organization; verify primary claims.",
        )
    if _host_matches(host, _THINK_TANK_DOMAINS):
        return (
            "research_institute",
            "medium",
            "Independent policy research institution or think tank; verify primary data sources.",
        )
    if host.endswith(".gov") or re.search(r"\.gov\.[a-z]{2}$", host) or host in {
        "europa.eu",
        "ec.europa.eu",
    }:
        return (
            "government",
            "high",
            "Official government source; authoritative within its stated scope.",
        )
    if any(host.endswith(s) for s in _GOV_SUFFIXES):
        return (
            "government",
            "high",
            "Official government source; authoritative within its stated scope.",
        )
    if host.endswith(".edu") or re.search(r"\.edu\.[a-z]{2}$", host):
        return (
            "research_institute",
            "medium",
            "University or academic institution; credible for research outputs, "
            "verify for commercial claims.",
        )
    if any(marker in host for marker in ("iso.org", "iec.ch", "standards.")):
        return (
            "standards_body",
            "high",
            "Official standards organization or standards registry.",
        )
    if _host_matches(host, _REPUTABLE_NEWS_DOMAINS):
        return (
            "reputable_news",
            "medium",
            "Editorial source on the approved general-news list; verify primary claims.",
        )
    if _host_matches(host, _INDUSTRY_NEWS_DOMAINS):
        return (
            "reputable_news",
            "medium",
            "Specialist trade publication; useful but not an independent primary record.",
        )
    if _host_matches(host, _MARKET_RESEARCH_DOMAINS):
        return (
            "market_report",
            "medium",
            "Commercial market estimate with potentially proprietary methodology.",
        )
    if _host_matches(host, _CONSULTING_RESEARCH_DOMAINS):
        return (
            "market_report",
            "medium",
            "Major consulting or strategy firm; verify methodology and primary data.",
        )
    if _host_matches(host, _PRESS_RELEASE_DOMAINS):
        return (
            "company_disclosure",
            "medium",
            "Press release wire service; primary for attributed company announcements.",
        )

    path = urlsplit(canonical_url).path.lower()
    if path in {"", "/"} or any(marker in path for marker in _CONTENT_PATH_MARKERS):
        return (
            "company_disclosure",
            "medium",
            "First-party company page; authoritative for its own claims but not independent.",
        )
    return None


def _parse_patent_year(url: str, snippet: str = "") -> int | None:
    """Extract approximate publication year from a patent URL or Serper snippet.

    Reliable formats (from patent number in URL path):
      WO{YYYY}...   — PCT/WIPO (always 4-digit year after WO)
      EP{YYYY}{6+}  — European Patent Office (year-based numbering)
      KR{YYYY}...   — Korean patent (year-based numbering)
    Fallback: first plausible 4-digit year (1990–current) in the snippet text.
    """
    current_year = date.today().year
    path = urlsplit(url).path
    m = re.search(r"/patent/([A-Z]{2}\d[\w]*)/", path, re.IGNORECASE)
    if m:
        pnum = m.group(1).upper()
        for pattern in (
            r"^WO(\d{4})",              # WO2024149278A1 → 2024
            r"^EP(\d{4})\d{5,}",        # EP1234567A1 (year-based numbering)
            r"^KR(\d{4})\d+",           # KR20240123456 → 2024
            r"^US(20\d{2})\d{7}[A-Z]",  # US20240194939A1 → 2024 (application numbers)
        ):
            pm = re.match(pattern, pnum)
            if pm:
                year = int(pm.group(1))
                if 1990 <= year <= current_year + 1:
                    return year
    # Fallback: find first 4-digit year token in snippet that is not a future
    # forecast year (market snippets commonly include "by 2030" projections).
    for m2 in re.finditer(r"\b(20[0-2]\d|199\d)\b", snippet):
        year = int(m2.group(1))
        if 1990 <= year <= current_year:
            return year
    return None


_STOP_WORDS: frozenset[str] = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "been", "by", "for",
    "from", "has", "have", "in", "is", "it", "its", "of", "on", "or",
    "that", "the", "their", "there", "these", "they", "this", "to",
    "was", "were", "which", "with",
})

# Generic experimental terms that appear in virtually every empirical paper
# regardless of domain (e.g. "process parameters" matches Al-alloy drilling
# and CFRP autoclave curing equally).  Excluded from keyword relevance scoring
# so only domain-specific terms contribute to source relevance.
_EXPERIMENTAL_NOISE_TERMS: frozenset[str] = frozenset({
    "process", "processes", "parameter", "parameters",
    "sample", "samples", "experiment", "experiments",
    "measurement", "measurements", "property", "properties",
    "result", "results", "value", "values", "data",
})

# High-frequency technology/method terms that appear across ALL domains and
# therefore cannot identify the application domain of a paper.  Used by
# _topic_domain_keywords to strip generic words before extracting domain signal.
_GENERIC_TECH_TERMS: frozenset[str] = frozenset({
    "large", "small", "lightweight", "language", "model", "models",
    "system", "systems", "method", "methods", "approach", "approaches",
    "application", "applications", "analysis", "based", "using",
    "deep", "learning", "neural", "network", "artificial", "intelligence",
    "machine", "detection", "classification", "generation", "evaluation",
    "performance", "review", "survey", "assessment", "management",
    "framework", "technique", "techniques", "result", "results",
    "research", "study", "novel", "efficient", "effective", "advanced",
    "improved", "new", "proposed", "automated", "automatic", "general",
})


def _topic_keywords(topic: str) -> frozenset[str]:
    """Extract meaningful lowercase words from a topic string."""
    words = re.findall(r"[a-z]{3,}", topic.lower())
    return frozenset(
        w for w in words
        if w not in _STOP_WORDS and w not in _EXPERIMENTAL_NOISE_TERMS
    )


def _topic_bigrams(topic: str) -> frozenset[str]:
    """Extract consecutive 2-word phrases from topic keywords (after stop-word removal)."""
    words = [w for w in re.findall(r"[a-z]{3,}", topic.lower()) if w not in _STOP_WORDS]
    return frozenset(f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1))


def _topic_domain_keywords(topic: str) -> frozenset[str]:
    """Extract the application-domain portion of a topic after a splitting preposition.

    For topics like "large language models in clinical medicine", this returns
    the domain part keywords ({"clinical", "medicine"}) stripped of generic tech
    terms.  These are used as a hard inclusion filter: academic papers must
    mention at least one domain keyword in their title or summary, otherwise
    they are treated as off-domain and excluded.

    For topics without a splitting preposition (e.g. "solid state batteries"),
    returns an empty frozenset so no domain check is applied.
    """
    lower = topic.lower()
    for prep in (" in ", " for ", " applied to ", " used in "):
        idx = lower.find(prep)
        if idx > 0:
            domain_part = lower[idx + len(prep):]
            words = re.findall(r"[a-z]{4,}", domain_part)
            domain_kw = frozenset(
                w for w in words
                if w not in _STOP_WORDS and w not in _GENERIC_TECH_TERMS
            )
            if domain_kw:
                return domain_kw
    return frozenset()


def _normalise_text(text: str) -> str:
    """Lowercase and replace hyphens/underscores with spaces for consistent matching."""
    return re.sub(r"[-_]", " ", text.lower())


_COMPARISON_TITLE_MARKERS: frozenset[str] = frozenset({
    "compared with", "comparison of", " versus ", " vs. ", " vs ",
    "in comparison", "as compared to", "relative to",
})


def _relevance_score(
    source: "EvidenceSource",
    keywords: frozenset[str],
    bigrams: frozenset[str],
    domain_keywords: frozenset[str] = frozenset(),
) -> int:
    """Score relevance: 1 pt per keyword hit + 2 pts per bigram hit.

    Papers whose title has no topic keywords AND contains comparison markers
    are penalised by 2 pts — they are typically off-topic comparison papers.

    When domain_keywords is provided (non-empty), a source that contains none
    of those keywords in its title or summary is given score -1 (hard exclusion)
    to prevent cross-domain papers from slipping through on generic tech terms
    alone (e.g. an SQL-injection paper scoring high on "large language models"
    when the topic is "large language models in clinical medicine").
    """
    if not keywords:
        return 1
    title_text = _normalise_text(source.title)
    body_text  = title_text + " " + _normalise_text(source.evidence_summary)

    # Hard domain filter: exclude papers that share the technology keywords but
    # belong to a completely different application domain.
    if domain_keywords and not any(dk in body_text for dk in domain_keywords):
        return -1

    score = (
        sum(1 for kw in keywords if kw in body_text)
        + sum(2 for bg in bigrams if bg in body_text)
    )
    title_kw = sum(1 for kw in keywords if kw in title_text)
    title_bg = sum(1 for bg in bigrams if bg in title_text)
    if title_kw == 0 and title_bg == 0 and any(m in title_text for m in _COMPARISON_TITLE_MARKERS):
        score = max(0, score - 2)
    return score


def _filter_by_relevance(
    sources: list["EvidenceSource"],
    topic: str,
    min_score: int = 1,
    min_keep: int = 2,
    *,
    skip_domain_filter: bool = False,
) -> list["EvidenceSource"]:
    """Filter low-relevance sources and sort survivors by relevance score descending.

    Sources with score -1 (domain mismatch) are always excluded, even when the
    fallback min_keep logic would otherwise include them.  The fallback returns
    the top-scoring qualified sources rather than the entire collection.

    skip_domain_filter: when True, the hard domain-keyword exclusion (score=-1) is
    bypassed.  Use for market sources, which commonly use industry shorthand such as
    "PV" instead of "photovoltaic" — terms that the domain filter would incorrectly
    reject despite the source being clearly on-topic.
    """
    keywords = _topic_keywords(topic)
    bigrams  = _topic_bigrams(topic)
    domain_keywords = frozenset() if skip_domain_filter else _topic_domain_keywords(topic)
    scored   = sorted(
        [(s, _relevance_score(s, keywords, bigrams, domain_keywords)) for s in sources],
        key=lambda x: x[1],
        reverse=True,
    )
    qualified = [(s, sc) for s, sc in scored if sc >= 0]
    kept = [s for s, sc in qualified if sc >= min_score]
    return kept if len(kept) >= min_keep else [s for s, _ in qualified]


def _record_relevance_filter(
    before: list["EvidenceSource"],
    after: list["EvidenceSource"],
    domain: str,
    audits: list["SearchAudit"],
    min_score: int,
) -> None:
    """Add a post-filter audit entry when _filter_by_relevance silently removes sources.

    Without this, sources that passed _collect_domain but were later dropped appear
    in audit.accepted_source_ids without a corresponding entry in the final source list,
    creating a misleading discrepancy.
    """
    after_ids = {s.source_id for s in after}
    removed = [s for s in before if s.source_id not in after_ids]
    if not removed:
        return
    audits.append(SearchAudit(
        domain=domain,
        query="[Relevance-Filter]",
        result_count=0,
        rejected_reasons=[
            f"score<{min_score} — removed '{s.title}'"
            for s in removed
        ],
    ))


def _web_source(
    result: dict[str, Any],
    source_id: str,
    domain: Literal["patent", "market"],
    accessed_date: date,
    url_checker: UrlChecker,
) -> tuple[EvidenceSource | None, str]:
    title = _clean_text(str(result.get("title", "")))
    link = str(result.get("link", "")).strip()
    snippet = str(result.get("snippet", ""))
    if len(title) < 5 or not link:
        return None, "search result lacks a usable title or URL"
    try:
        canonical = _canonical_url(link)
        host = (urlsplit(canonical).hostname or "").lower()
    except ValueError as exc:
        return None, f"invalid URL: {exc}"

    if domain == "patent":
        if host not in _PATENT_HOSTS:
            return None, f"non-primary patent host: {host}"
        source_type = "patent"
        credibility_tier = "high"
        patent_year = _parse_patent_year(canonical, snippet)
        credibility_reason = (
            f"Official patent registry record; publication year: {patent_year}; "
            "legal scope still requires claim review."
            if patent_year else
            "Official patent registry record; legal scope still requires claim review."
        )
    else:
        profile = _market_source_profile(canonical, host)
        if profile is None:
            return None, f"market host is blocked or not approved: {host}"
        source_type, credibility_tier, credibility_reason = profile

    # Skip reachability check for known official patent registries — always up.
    if domain == "patent" and host in _PATENT_HOSTS:
        reachable, reason = True, ""
    else:
        reachable, reason = url_checker(canonical)
    if not reachable:
        return None, f"unreachable URL {canonical}: {reason}"
    published_date: date | None = None
    if domain == "patent" and patent_year:
        published_date = date(patent_year, 1, 1)
    elif domain == "market":
        market_year = _parse_patent_year("", snippet)
        if market_year:
            published_date = date(market_year, 1, 1)

    # B2: Staleness penalty for commercial market reports.
    # Market size estimates older than 3 years have low reliability.
    if (domain == "market"
            and source_type == "market_report"
            and published_date is not None
            and (accessed_date.year - published_date.year) > 3):
        credibility_tier = "low"
        credibility_reason = (
            f"Stale market data (published {published_date.year}): "
            "commercial market estimates >3 years old have low reliability. "
            + credibility_reason
        )

    return (
        EvidenceSource(
            source_id=source_id,
            title=title,
            url=canonical,
            publisher=_publisher_for_host(host),
            published_date=published_date,
            accessed_date=accessed_date,
            source_type=source_type,
            credibility_tier=credibility_tier,
            credibility_reason=credibility_reason,
            evidence_summary=_safe_summary(snippet, title),
            summary_source="search_snippet" if domain == "market" else None,
        ),
        "",
    )


def _queries(
    topic: str,
    *,
    native_topic: str | None = None,
    patent_cc: str = "",
) -> dict[Domain, list[str]]:
    # Short-form topic for patent/market search: strip parenthetical qualifiers
    # and take the first N words so queries are search-engine-friendly.
    _pat_clean = re.sub(r"\s*\([^)]*\)", "", topic).strip()
    _pat_short = " ".join(_pat_clean.split()[:4])
    # Market short: 6 content words — specific enough to find sector reports
    # without including metric clauses (e.g. "improving X by 12.1%") that
    # appear in no market report.
    _mkt_short = " ".join(_pat_clean.split()[:6])
    patent: list[str] = [
        f"{topic} site:patents.google.com/patent",
        f"{topic} site:patentscope.wipo.int",
        f"{topic} site:worldwide.espacenet.com",
        f"{topic} site:patents.justia.com",
        f"{_pat_short} site:patents.google.com/patent",
        f"{_pat_short} site:patentscope.wipo.int",
    ]
    if patent_cc:
        # Prioritise country-specific patents when input language implies a country.
        patent.insert(0, f"{topic} {patent_cc} site:patents.google.com/patent")

    market: list[str] = [
        # Short-form queries first: more likely to match market/industry reports
        # than the full metric-laden topic string.
        f"{_mkt_short} market size revenue commercial manufacturer 2024 2025",
        f"{_mkt_short} industry company deployment commercial scale",
        f"{topic} product manufacturer revenue commercial sales 2024 2025",
        f"{topic} company commercial deployment industry news",
        f"{_mkt_short} market report investment startup 2024",
        f"{topic} commercial scale production manufacturer press release",
        f"{topic} manufacturing commercialization company",
        f"{topic} government standards policy commercialization",
    ]
    if native_topic and native_topic != topic:
        # One native-language query so the native Serper pass has a base query.
        market.append(native_topic)

    return {
        "academic": [
            f"{topic} peer reviewed DOI journal",
            f"{topic} systematic review meta-analysis",
            f"{topic} site:scholar.google.com",
            f"{topic} Nature Science Cell Lancet article",
            f"{topic} review journal",
            f"{topic} efficiency stability commercialization",
        ],
        "patent": patent,
        "market": market,
    }


def _market_summary_relevant(summary: str, topic: str) -> bool:
    """Return False when a market source summary contains no relevant topic keyword.

    For topics with a 'for X' structure (e.g. 'CAR-T cell therapy for solid
    tumors'), the tail words ('solid', 'tumors') are used as the filter so that
    broad-category reports are rejected when the research question is specifically
    about a sub-indication.

    A summary passes if ANY word from either the tail OR the core phrase appears
    in it. This prevents over-rejection when industry uses synonyms (e.g.
    'cultured meat' / 'lab-grown meat' for a 'cultivated meat' topic) — the
    core word 'meat' still matches even if tail words ('food', 'industry') don't.

    For topics without a preposition, falls back to core words of length >= 6.
    """
    core = _topic_core_phrase(topic)
    core_words = {
        w for w in _WORD_PATTERN.findall(core.lower())
        if len(w) >= 4 and w not in _TOPIC_STOPWORDS
    }
    tail_words = _topic_tail_words(topic, min_len=4)

    if tail_words:
        # Pass if ANY tail word OR ANY core word appears in the summary.
        filter_words = tail_words | core_words
    else:
        filter_words = {w for w in core_words if len(w) >= 6}

    if not filter_words:
        return True
    summary_words = set(_WORD_PATTERN.findall(summary.lower()))
    return bool(filter_words & summary_words)


def _collect_domain(
    domain: Domain,
    queries: list[str],
    searcher: SearchFunction,
    crossref: CrossrefClient,
    url_checker: UrlChecker,
    accessed_date: date,
    research_topic: str,
    *,
    minimum_sources: int,
    maximum_sources: int,
    blocked_dois: set[str] | None = None,
    blocked_titles: set[str] | None = None,
) -> tuple[list[EvidenceSource], list[SearchAudit]]:
    prefix = {"academic": "A", "patent": "P", "market": "M"}[domain]
    accepted: list[EvidenceSource] = []
    audits: list[SearchAudit] = []
    # Pre-populate patent title dedup from blocked_titles so that Serper
    # supplement runs (after Lens/USPTO) don't re-accept the same patents.
    seen_patent_titles: set[str] = (
        {" ".join(_WORD_PATTERN.findall(t.lower())) for t in (blocked_titles or set())}
        if domain == "patent" else set()
    )
    seen_academic_title_keys: set[str] = set()
    seen_locators: set[str] = set()
    # Market domain: defer low-priority sources (institutional OR excess market_report)
    # so that company_disclosure / reputable_news sources have a chance to fill slots.
    _deferred: list[EvidenceSource] = []
    _institutional_accepted = 0
    _market_report_accepted = 0
    _INSTITUTIONAL_TYPES = frozenset(("research_institute", "government"))
    excluded_dois = {
        doi.lower()
        for doi in (blocked_dois or set())
    }
    excluded_titles = {title for title in (blocked_titles or set()) if title.strip()}
    # Pre-normalised keys of already-accepted titles (from OpenAlex pass or
    # prior queries) — used for academic title dedup across search batches.
    excluded_title_keys: set[str] = {
        " ".join(_WORD_PATTERN.findall(t.lower())) for t in excluded_titles
    }
    _pat_kws = _topic_keywords(research_topic) if domain == "patent" else frozenset()
    _pat_bgs = _topic_bigrams(research_topic) if domain == "patent" else frozenset()

    for query in queries:
        if len(accepted) >= maximum_sources:
            break
        response = searcher(query)
        organic = response.get("organic", [])
        results = [item for item in organic if isinstance(item, dict)]
        audit = SearchAudit(domain=domain, query=query, result_count=len(results))
        for result in results[:_SERPER_MAX_RESULTS_PER_QUERY]:
            if len(accepted) >= maximum_sources:
                break
            # Use a stable placeholder; the real ID is assigned only when the
            # source is confirmed accepted so deferred sources never get the
            # same ID as an accepted source during interim processing.
            _tmp_src_id = f"{prefix}0"
            if domain == "market":
                candidate_doi = _extract_doi(
                    unquote(str(result.get("link", ""))),
                    str(result.get("snippet", "")),
                )
                if candidate_doi and candidate_doi.lower() in excluded_dois:
                    audit.rejected_reasons.append(
                        f"duplicates academic DOI: {candidate_doi}"
                    )
                    continue
                # Apply title deduplication only when the result looks like an
                # academic paper (has a DOI link, comes from an academic publisher
                # domain, or its title starts with "[PDF]"). Company announcements
                # and market articles share vocabulary with papers but are distinct
                # sources and should not be rejected on title overlap alone.
                result_link = str(result.get("link", ""))
                result_title = _clean_text(str(result.get("title", "")))
                result_host = (urlsplit(result_link).hostname or "").lower()
                result_looks_academic = (
                    candidate_doi is not None
                    or _host_matches(result_host, _ACADEMIC_PUBLISHER_DOMAINS)
                    or result_title.startswith("[PDF]")
                )
                if result_looks_academic:
                    duplicate_title = next(
                        (
                            title
                            for title in excluded_titles
                            if _title_similarity(result_title, title) >= _TITLE_BLOCKED_MATCH_THRESHOLD
                        ),
                        None,
                    )
                    if duplicate_title is not None:
                        audit.rejected_reasons.append(
                            f"duplicates academic title: {result_title}"
                        )
                        continue
            if domain == "academic":
                source, reason = _academic_source(
                    result, _tmp_src_id, crossref, accessed_date, research_topic
                )
            else:
                source, reason = _web_source(
                    result, _tmp_src_id, domain, accessed_date, url_checker
                )
            if source is None:
                audit.rejected_reasons.append(reason)
                continue
            _es = source.evidence_summary
            _cjk_count = sum(
                1 for c in _es if '一' <= c <= '鿿'
                or '぀' <= c <= 'ヿ'
                or '가' <= c <= '힯'
            )
            _min_chars = 40 if _cjk_count >= 15 else _MIN_EVIDENCE_SUMMARY_CHARS
            if len(_es) < _min_chars:
                audit.rejected_reasons.append(
                    f"evidence summary too thin "
                    f"({len(_es)} chars): {source.title!r}"
                )
                continue
            if domain == "market" and not _market_summary_relevant(
                source.evidence_summary, research_topic
            ):
                audit.rejected_reasons.append(
                    f"market summary lacks core topic keywords: {source.title!r}"
                )
                continue
            if domain == "patent" and _pat_kws:
                _title_norm = _normalise_text(source.title)
                _tscore = (
                    sum(1 for kw in _pat_kws if kw in _title_norm)
                    + sum(2 for bg in _pat_bgs if bg in _title_norm)
                )
                if _tscore < 2:
                    audit.rejected_reasons.append(
                        f"patent title not relevant to topic"
                        f" (score {_tscore}): {source.title!r}"
                    )
                    continue
                # Reject patents targeting the opposite electrode when the topic
                # is electrode-specific (e.g. "anode" topic → reject cathode patents).
                if "anode" in _pat_kws and "cathode" not in _pat_kws:
                    if "cathode" in _title_norm and "anode" not in _title_norm:
                        audit.rejected_reasons.append(
                            f"patent targets cathode, topic focuses on anode: {source.title!r}"
                        )
                        continue
                elif "cathode" in _pat_kws and "anode" not in _pat_kws:
                    if "anode" in _title_norm and "cathode" not in _title_norm:
                        audit.rejected_reasons.append(
                            f"patent targets anode, topic focuses on cathode: {source.title!r}"
                        )
                        continue
            locator = source.doi or str(source.url)
            if locator.lower() in seen_locators:
                audit.rejected_reasons.append(f"duplicate source: {locator}")
                continue
            seen_locators.add(locator.lower())
            if domain == "academic":
                title_key = " ".join(_WORD_PATTERN.findall(source.title.lower()))
                if title_key in seen_academic_title_keys or title_key in excluded_title_keys:
                    audit.rejected_reasons.append(
                        f"duplicate academic title: {source.title}"
                    )
                    continue
                seen_academic_title_keys.add(title_key)
            if domain == "patent":
                patent_title_key = " ".join(_WORD_PATTERN.findall(source.title.lower()))
                if patent_title_key in seen_patent_titles:
                    audit.rejected_reasons.append(
                        f"duplicate patent family title: {source.title}"
                    )
                    continue
                seen_patent_titles.add(patent_title_key)
            if domain == "market":
                if source.source_type in _INSTITUTIONAL_TYPES:
                    if _institutional_accepted >= _MARKET_INSTITUTIONAL_SOFT_CAP:
                        _deferred.append(source)
                        audit.rejected_reasons.append(
                            f"deferred (institutional cap): {source.title!r}"
                        )
                        continue
                    _institutional_accepted += 1
                elif source.source_type == "market_report":
                    if _market_report_accepted >= _MARKET_REPORT_SOFT_CAP:
                        _deferred.append(source)
                        audit.rejected_reasons.append(
                            f"deferred (market-report cap): {source.title!r}"
                        )
                        continue
                    _market_report_accepted += 1
            source.source_id = f"{prefix}{len(accepted) + 1}"
            accepted.append(source)
            audit.accepted_source_ids.append(source.source_id)
        audits.append(audit)
        if len(accepted) >= maximum_sources:
            break

    # Fill remaining market slots from deferred sources (institutional or excess
    # market_report) when higher-priority types didn't fill those slots.
    _promoted_deferred: list[EvidenceSource] = []
    if domain == "market" and _deferred:
        for _deferred_src in _deferred:
            if len(accepted) >= maximum_sources:
                break
            _deferred_src.source_id = f"M{len(accepted) + 1}"
            accepted.append(_deferred_src)
            _promoted_deferred.append(_deferred_src)
    if _promoted_deferred:
        audits.append(SearchAudit(
            domain="market",
            query="[Deferred-Promotion]",
            result_count=len(_promoted_deferred),
            accepted_source_ids=[s.source_id for s in _promoted_deferred],
        ))

    if len(accepted) < minimum_sources:
        rejected = list(
            dict.fromkeys(
                reason
                for audit in audits
                for reason in audit.rejected_reasons
            )
        )
        detail = "; ".join(rejected[:5]) or "search returned no usable candidates"
        raise SourceCollectionError(
            f"{domain} retrieval produced {len(accepted)} validated sources; "
            f"at least {minimum_sources} are required. Rejections: {detail}"
        )
    return accepted, audits


def _collect_academic_primary(
    topic: str,
    openalex: OpenAlexClient,
    s2: SemanticScholarClient,
    accessed_date: date,
    *,
    maximum_sources: int,
    weight_profile: str = "industrial",
    synonyms: list[str] | None = None,
    pubmed: "PubMedClient | None" = None,
    arxiv: "ArxivClient | None" = None,
) -> tuple[list[EvidenceSource], list[SearchAudit]]:
    """Collect academic sources via concurrent multi-API fetch with synonym,
    topic-cluster, MeSH, and citation-snowball expansion."""
    from concurrent.futures import ThreadPoolExecutor

    fetch_rows = max(20, maximum_sources * 4)
    recent_slots = (maximum_sources + 1) // 2
    all_synonyms = list(synonyms or [])

    pubmed_client = pubmed if pubmed is not None else PubMedClient()
    arxiv_client = arxiv if arxiv is not None else ArxivClient()

    accepted: list[EvidenceSource] = []
    accepted_token_sets: list[frozenset[str]] = []  # parallel to accepted; used for O(1) pre-filter
    seen_dois: set[str] = set()
    seen_title_keys: set[str] = set()
    audits: list[SearchAudit] = []

    def _title_key(title: str) -> str:
        return " ".join(_WORD_PATTERN.findall(title.lower()))

    def _try_add(source: EvidenceSource, audit: SearchAudit) -> bool:
        doi_key = (source.doi or "").lower()
        if doi_key and doi_key in seen_dois:
            audit.rejected_reasons.append(f"duplicate DOI: {doi_key}")
            return False
        tkey = _title_key(source.title)
        if tkey and tkey in seen_title_keys:
            audit.rejected_reasons.append(f"duplicate title: {source.title}")
            return False
        new_tokens = frozenset(tkey.split())
        for i, existing in enumerate(accepted):
            # word-overlap pre-filter: skip SequenceMatcher when titles share too
            # few words to ever reach the 0.88 similarity threshold.
            ex_tokens = accepted_token_sets[i]
            if ex_tokens and new_tokens:
                n = min(len(new_tokens), len(ex_tokens))
                if len(new_tokens & ex_tokens) / n < _TITLE_PREFILTER_OVERLAP:
                    continue
            if _title_similarity(source.title, existing.title) >= _TITLE_NEAR_DUP_THRESHOLD:
                audit.rejected_reasons.append(
                    f"near-duplicate of '{existing.title}': {source.title}"
                )
                return False
        if doi_key:
            seen_dois.add(doi_key)
        seen_title_keys.add(tkey)
        accepted_token_sets.append(new_tokens)
        accepted.append(source)
        audit.accepted_source_ids.append(source.source_id)
        return True

    def _fill_oa(works: list[dict], audit: SearchAudit, limit: int) -> None:
        """Convert and dedup OpenAlex works into accepted up to limit."""
        for work in works:
            if len(accepted) >= limit:
                break
            src_id = f"A{len(accepted) + 1}"
            source, reason = _academic_source_from_openalex(
                work, src_id, accessed_date, topic, s2_client=s2
            )
            if source is None:
                audit.rejected_reasons.append(reason)
                continue
            _try_add(source, audit)

    def _fill(papers: list[dict], audit: SearchAudit, converter, limit: int) -> None:
        """Convert and dedup S2/PubMed/arXiv papers into accepted up to limit."""
        for paper in papers:
            if len(accepted) >= limit:
                break
            src_id = f"A{len(accepted) + 1}"
            source, reason = converter(paper, src_id, accessed_date, topic)
            if source is None:
                audit.rejected_reasons.append(reason)
                continue
            _try_add(source, audit)

    # ── Phase 1: concurrent raw fetch ─────────────────────────────────────────
    with ThreadPoolExecutor(max_workers=6) as pool:
        f_recent = pool.submit(
            openalex.search_recent, topic,
            since_year=date.today().year - 3, rows=fetch_rows,
        )
        f_cited  = pool.submit(openalex.search, topic, rows=fetch_rows)
        f_s2     = pool.submit(s2.search, topic, rows=fetch_rows)
        f_pubmed = pool.submit(pubmed_client.search, topic, rows=fetch_rows)
        f_arxiv  = pool.submit(arxiv_client.search, topic, rows=fetch_rows)
        syn_futures = {
            syn: pool.submit(openalex.search, syn, rows=fetch_rows // 2)
            for syn in all_synonyms
        }

    def _safe(future, label: str) -> list:
        try:
            return future.result()
        except Exception as exc:
            audits.append(SearchAudit(
                domain="academic",
                query=f"[{label}] {topic}",
                result_count=0,
                rejected_reasons=[str(exc)],
            ))
            return []

    recent_works  = _safe(f_recent, "OA-Recent")
    cited_works   = _safe(f_cited,  "OA-Cited")
    s2_papers     = _safe(f_s2,     "S2")
    pm_papers     = _safe(f_pubmed, "PubMed")
    ax_papers     = _safe(f_arxiv,  "arXiv")
    syn_works_map = {syn: _safe(f, f"OA-Syn:{syn[:20]}") for syn, f in syn_futures.items()}

    # ── Phase 2: fill in priority order ───────────────────────────────────────
    recent_audit = SearchAudit(
        domain="academic",
        query=f"[OA-Recent] {topic}",
        result_count=len(recent_works),
    )
    cited_audit = SearchAudit(
        domain="academic",
        query=f"[OA-Cited] {topic}",
        result_count=len(cited_works),
    )
    audits.extend([recent_audit, cited_audit])

    # Recent-slots first, then age-split cited track
    _fill_oa(recent_works, recent_audit, limit=recent_slots)

    _cited_cutoff = date.today().replace(year=date.today().year - 7)
    cited_preferred = [w for w in cited_works if (p := _published_date(w)) is None or p >= _cited_cutoff]
    cited_fallback  = [w for w in cited_works if (p := _published_date(w)) is not None and p < _cited_cutoff]
    _fill_oa(cited_preferred + cited_fallback, cited_audit, limit=maximum_sources)

    # Synonym expansion (each synonym adds a separate audit row)
    for syn, syn_works in syn_works_map.items():
        if len(accepted) >= maximum_sources:
            break
        syn_audit = SearchAudit(
            domain="academic",
            query=f"[OA-Syn:{syn[:30]}] {topic}",
            result_count=len(syn_works),
        )
        audits.append(syn_audit)
        _fill_oa(syn_works, syn_audit, limit=maximum_sources)

    # S2 / PubMed / arXiv supplements when still short
    if len(accepted) < maximum_sources:
        s2_audit = SearchAudit(domain="academic", query=f"[S2] {topic}", result_count=len(s2_papers))
        audits.append(s2_audit)
        _fill(s2_papers, s2_audit, _academic_source_from_s2, maximum_sources)

    if len(accepted) < maximum_sources:
        pm_audit = SearchAudit(domain="academic", query=f"[PubMed] {topic}", result_count=len(pm_papers))
        audits.append(pm_audit)
        _fill(pm_papers, pm_audit, _academic_source_from_pubmed, maximum_sources)

    if len(accepted) < maximum_sources:
        ax_audit = SearchAudit(domain="academic", query=f"[arXiv] {topic}", result_count=len(ax_papers))
        audits.append(ax_audit)
        _fill(ax_papers, ax_audit, _academic_source_from_arxiv, maximum_sources)

    # ── Phase 4: Topic-ID cluster expansion ───────────────────────────────────
    _topic_id_counts: dict[str, int] = {}
    for work in recent_works + cited_works:
        for t in work.get("topics") or []:
            tid = t.get("id") or ""
            if tid:
                _topic_id_counts[tid] = _topic_id_counts.get(tid, 0) + 1
    top_topic_ids = sorted(_topic_id_counts, key=_topic_id_counts.__getitem__, reverse=True)[:2]

    if top_topic_ids and len(accepted) < maximum_sources:
        with ThreadPoolExecutor(max_workers=2) as pool:
            cl_futures = {pool.submit(openalex.search_by_topic, tid, rows=10): tid for tid in top_topic_ids}
        for future, tid in cl_futures.items():
            if len(accepted) >= maximum_sources:
                break
            try:
                cl_works = future.result()
            except Exception:
                cl_works = []
            if not cl_works:
                continue
            cl_audit = SearchAudit(
                domain="academic",
                query=f"[OA-Cluster:{tid.rsplit('/', 1)[-1]}] {topic}",
                result_count=len(cl_works),
            )
            audits.append(cl_audit)
            _fill_oa(cl_works, cl_audit, limit=maximum_sources)

    # ── Phase 5: PubMed MeSH expansion (biomedical topics only) ──────────────
    if weight_profile == "biomedical" and len(accepted) < maximum_sources:
        try:
            mesh_terms = pubmed_client.get_mesh_terms(topic, max_terms=3)
        except Exception:
            mesh_terms = []
        if mesh_terms:
            try:
                mesh_papers = pubmed_client.search_mesh(mesh_terms, rows=fetch_rows // 2)
            except Exception:
                mesh_papers = []
            if mesh_papers:
                mesh_audit = SearchAudit(
                    domain="academic",
                    query=f"[PubMed-MeSH:{', '.join(mesh_terms[:2])}] {topic}",
                    result_count=len(mesh_papers),
                )
                audits.append(mesh_audit)
                _fill(mesh_papers, mesh_audit, _academic_source_from_pubmed, maximum_sources)

    # ── Phase 6: Citation snowball ────────────────────────────────────────────
    if len(accepted) < maximum_sources:
        snowball_candidates = sorted(
            [s for s in accepted if s.doi and (s.citation_count or 0) >= 5],
            key=lambda s: s.citation_count or 0,
            reverse=True,
        )[:3]
        if snowball_candidates:
            with ThreadPoolExecutor(max_workers=3) as pool:
                ref_futures = {pool.submit(openalex.fetch_referenced_works, s.doi, top_n=25): s for s in snowball_candidates}
            all_ref_ids: list[str] = []
            for future in ref_futures:
                try:
                    all_ref_ids.extend(future.result())
                except Exception:
                    pass
            if all_ref_ids:
                try:
                    snowball_works = openalex.fetch_works_by_ids(all_ref_ids, rows=15)
                except Exception:
                    snowball_works = []
                if snowball_works:
                    sb_audit = SearchAudit(
                        domain="academic",
                        query=f"[OA-Snowball] {topic}",
                        result_count=len(snowball_works),
                    )
                    audits.append(sb_audit)
                    _fill_oa(snowball_works, sb_audit, limit=maximum_sources)

    return accepted, audits


def _renumber(sources: list[EvidenceSource], prefix: str) -> None:
    """Reassign sequential source IDs in-place after merging from multiple providers."""
    for i, src in enumerate(sources, start=1):
        src.source_id = f"{prefix}{i}"


def collect_source_collection(
    topic: str,
    *,
    searcher: SearchFunction | None = None,
    crossref: CrossrefClient | None = None,
    openalex: OpenAlexClient | None = None,
    s2: SemanticScholarClient | None = None,
    pubmed: "PubMedClient | None" = None,
    arxiv: "ArxivClient | None" = None,
    lens: "LensPatentClient | None" = None,
    url_checker: UrlChecker = check_public_url,
    minimum_sources: int = 3,
    maximum_sources: int = 8,
    accessed_date: date | None = None,
    paper_seed: "EvidenceSource | None" = None,  # noqa: F821
    extra_market_queries: list[str] | None = None,
) -> SourceCollection:
    # ── Language detection & translation ─────────────────────────────────────
    from academic_agent.language import (
        detect_language, generate_synonyms, get_lang_info,
        translate_to_english, translate_headings,
    )
    from academic_agent.evidence import _REQUIRED_REPORT_HEADINGS

    lang_code  = detect_language(topic)
    lang_info  = get_lang_info(lang_code)
    is_native  = not lang_code.startswith("en")

    if is_native:
        english_topic = translate_to_english(topic)
        native_topic  = topic
    else:
        english_topic = topic
        native_topic  = None

    normalized_topic = " ".join(english_topic.split())
    weight_profile = _detect_weight_profile(normalized_topic)

    # Generate 2 synonym phrasings to widen API search coverage.
    # Done after translation so synonyms are always in English.
    topic_synonyms = generate_synonyms(normalized_topic, n=2)
    if len(normalized_topic) < 3:
        raise SourceCollectionError("Research topic must contain at least 3 characters.")
    if minimum_sources < 1 or maximum_sources < minimum_sources:
        raise ValueError("Source count bounds are invalid.")

    # Translate report headings once so guardrails and the LLM use the same strings.
    if is_native:
        localized_headings = list(
            translate_headings(_REQUIRED_REPORT_HEADINGS, lang_info["name"])
        )
    else:
        localized_headings = []

    patent_cc  = lang_info.get("patent_cc", "")
    query_map  = _queries(normalized_topic, native_topic=native_topic, patent_cc=patent_cc)
    if extra_market_queries:
        # Prepend broader domain queries so they run before the topic-specific ones.
        query_map["market"] = list(extra_market_queries) + query_map["market"]

    resolved_crossref = crossref or CrossrefClient()
    resolved_openalex = openalex or OpenAlexClient()
    resolved_s2       = s2 or SemanticScholarClient()
    resolved_date     = accessed_date or date.today()
    all_audits: list[SearchAudit] = []

    # Default (English) Serper client — only instantiated when no searcher is injected
    if searcher is None:
        default_serper    = SerperClient()
        resolved_searcher = default_serper.search
    else:
        resolved_searcher = searcher

    # Native-language Serper client (only instantiated when needed)
    if is_native and searcher is None:
        native_serper = SerperClient(gl=lang_info["gl"], hl=lang_info["hl"])
    else:
        native_serper = None

    # ── Academic: OpenAlex primary, S2 supplement, Serper+Crossref fallback ──
    academic, oa_audits = _collect_academic_primary(
        normalized_topic, resolved_openalex, resolved_s2, resolved_date,
        maximum_sources=maximum_sources,
        weight_profile=weight_profile,
        synonyms=topic_synonyms,
        pubmed=pubmed,
        arxiv=arxiv,
    )
    all_audits.extend(oa_audits)

    if len(academic) < minimum_sources:
        needed = maximum_sources - len(academic)
        existing_dois = {src.doi for src in academic if src.doi}
        try:
            fallback, fb_audits = _collect_domain(
                "academic",
                query_map["academic"],
                resolved_searcher, resolved_crossref, url_checker,
                resolved_date, normalized_topic,
                minimum_sources=0,
                maximum_sources=needed,
                blocked_dois=existing_dois,
                blocked_titles={src.title for src in academic},
            )
            all_audits.extend(fb_audits)
            for src in fallback:
                if src.doi and src.doi.lower() in existing_dois:
                    continue
                if src.doi:
                    existing_dois.add(src.doi.lower())
                academic.append(src)
                if len(academic) >= maximum_sources:
                    break
        except SourceCollectionError as _fb_err:
            all_audits.append(SearchAudit(
                domain="academic",
                query="[Serper-Fallback]",
                result_count=0,
                rejected_reasons=[str(_fb_err)],
            ))

    # Backfill citation_count for any source still missing it.
    # DOI sources → OpenAlex.  arXiv-only sources (no DOI) → Semantic Scholar arXiv lookup.
    # Run concurrently — both APIs are free, ~150 ms each.
    _needs_citation_doi    = [src for src in academic if src.citation_count is None and src.doi]
    _needs_citation_arxiv  = [
        src for src in academic
        if src.citation_count is None and not src.doi
        and src.url and "arxiv.org/abs/" in str(src.url)
    ]

    def _fetch_citation_doi(src: EvidenceSource) -> None:
        cited = resolved_openalex.fetch_citation_by_doi(src.doi)  # type: ignore[arg-type]
        if cited is not None:
            src.citation_count = cited

    def _fetch_citation_arxiv(src: EvidenceSource) -> None:
        _m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", str(src.url or ""), re.IGNORECASE)
        arxiv_id = _m.group(1) if _m else ""
        if not arxiv_id:
            return
        s2_url = f"https://api.semanticscholar.org/graph/v1/paper/arXiv:{arxiv_id}?fields=citationCount"
        try:
            _s2_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
            _s2_headers = {"User-Agent": "AcademicAgentSourceCollector/1.0"}
            if _s2_key:
                _s2_headers["x-api-key"] = _s2_key
            req = Request(s2_url, headers=_s2_headers)
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            count = data.get("citationCount")
            if count is not None:
                src.citation_count = int(count)
        except Exception:
            pass

    if _needs_citation_doi or _needs_citation_arxiv:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as _pool:
            list(_pool.map(_fetch_citation_doi,   _needs_citation_doi))
            list(_pool.map(_fetch_citation_arxiv, _needs_citation_arxiv))

    # Re-evaluate credibility_tier after backfill.
    # A2: sources initially downgraded for "0 citations" → upgrade if citations now found.
    # A3: arXiv preprints with >= 10 backfilled citations → upgrade to "high".
    for _src in academic:
        if _src.credibility_tier != "medium" or not _src.citation_count:
            continue
        _is_arxiv = _src.url and "arxiv.org/abs/" in str(_src.url)
        _reason = _src.credibility_reason or ""
        if _is_arxiv and _src.citation_count >= 10:
            _src.credibility_tier = "high"
            _src.credibility_reason = (
                f"High-impact preprint: {_src.citation_count} citations (backfilled via S2)"
            )
        elif "0 citation" in _reason and _src.citation_count > 0:
            _src.credibility_tier = "high"
            _src.credibility_reason = (
                f"Upgraded after backfill: {_src.citation_count} citations"
            )

    if len(academic) < minimum_sources:
        raise SourceCollectionError(
            f"academic retrieval produced {len(academic)} validated sources "
            f"(OpenAlex + Serper+Crossref combined); "
            f"at least {minimum_sources} are required."
        )

    # ── Patents: Lens.org primary → Serper fallback ───────────────────────────
    patents: list[EvidenceSource] = []
    patent_audits: list[SearchAudit] = []
    lens_client = lens if lens is not None else LensPatentClient()
    if lens_client.api_key:
        seen_lens_ids: set[str] = set()
        seen_patent_titles: set[str] = set()
        # Lens uses a structured JSON query — pass the clean topic, not Serper
        # site:-qualified strings which return 0 results from the Lens API.
        lens_results = lens_client.search(normalized_topic, rows=maximum_sources * 3)
        lens_audit = SearchAudit(
            domain="patent",
            query=f"[Lens.org] {normalized_topic}",
            result_count=len(lens_results),
        )
        for rec in lens_results:
            if len(patents) >= maximum_sources:
                break
            lid = str(rec.get("lens_id") or "").strip()
            if lid in seen_lens_ids:
                lens_audit.rejected_reasons.append(f"duplicate lens_id: {lid}")
                continue
            source_id = f"P{len(patents) + 1}"
            source, reason = _patent_source_from_lens(rec, source_id, resolved_date, normalized_topic)
            if source is None:
                lens_audit.rejected_reasons.append(reason)
                continue
            tkey = " ".join(_WORD_PATTERN.findall(source.title.lower()))
            if tkey in seen_patent_titles:
                lens_audit.rejected_reasons.append(f"duplicate patent title: {source.title}")
                continue
            seen_lens_ids.add(lid)
            seen_patent_titles.add(tkey)
            patents.append(source)
            lens_audit.accepted_source_ids.append(source_id)
        patent_audits.append(lens_audit)



    # Always run a targeted Google Patents / WIPO Serper search as a geographic
    # supplement: Lens.org skews toward Chinese and Asian patents, while the
    # site:-qualified Serper queries surface US, EP, and WO records not always
    # represented in the Lens index.  Cap at 3 extra slots, but never exceed
    # maximum_sources in total.
    _gp_remaining = max(0, maximum_sources - len(patents))
    if _gp_remaining > 0:
        _gp_slots = min(3, _gp_remaining)
        serper_patents, serper_patent_audits = _collect_domain(
            "patent",
            query_map["patent"],
            resolved_searcher, resolved_crossref, url_checker,
            resolved_date, normalized_topic,
            minimum_sources=0,
            maximum_sources=_gp_slots,
            blocked_titles={p.title for p in patents},
        )
        patent_audits.extend(serper_patent_audits)
        patents.extend(serper_patents)

    all_audits.extend(patent_audits)

    # ── Market: English Serper + native-language Serper supplement ────────────
    market, market_audits = _collect_domain(
        "market",
        query_map["market"],
        resolved_searcher, resolved_crossref, url_checker,
        resolved_date, normalized_topic,
        minimum_sources=max(2, minimum_sources - 1),
        maximum_sources=maximum_sources,
        blocked_dois={src.doi for src in academic if src.doi is not None},
        blocked_titles={src.title for src in academic},
    )
    all_audits.extend(market_audits)

    # ── Company-news coverage guard ───────────────────────────────────────────
    # Market reports are easy to collect but don't show real commercial activity.
    # If no company_disclosure or reputable_news source was collected (meaning all
    # sources are market-forecast reports), run a targeted pass with news-signal
    # queries designed to surface press releases and trade-press articles about
    # specific companies.
    _COMPANY_NEWS_TYPES = frozenset(("company_disclosure", "reputable_news"))
    _company_news_count = sum(1 for s in market if s.source_type in _COMPANY_NEWS_TYPES)
    if _company_news_count < 1:
        # Trigger regardless of whether market slots are full: if all slots are
        # market_report sources, replace the last one so company news is represented.
        _company_news_queries = [
            f"{normalized_topic} company commercial product launch news 2025",
            f"{normalized_topic} manufacturer production deployment announcement press release 2024 2025",
        ]
        try:
            _cn_sources, _cn_audits = _collect_domain(
                "market",
                _company_news_queries,
                resolved_searcher, resolved_crossref, url_checker,
                resolved_date, normalized_topic,
                minimum_sources=0,
                maximum_sources=max(2, maximum_sources - len(market)),
                blocked_dois={src.doi for src in academic if src.doi is not None},
                blocked_titles={src.title for src in academic}
                              | {src.title for src in market},
            )
            all_audits.extend(_cn_audits)
            for _cn in _cn_sources:
                if _cn.source_type not in _COMPANY_NEWS_TYPES:
                    continue
                if len(market) < maximum_sources:
                    market.append(_cn)
                else:
                    # Slots are full — swap out the last market_report source so at
                    # least one company/trade-press source is present.
                    for _i in range(len(market) - 1, -1, -1):
                        if market[_i].source_type == "market_report":
                            market[_i] = _cn
                            break
                    else:
                        continue  # no market_report to replace; skip
                break  # one company-news source secured is enough
        except SourceCollectionError:
            pass

    # Supplement market with native-language search when input is non-English.
    if native_serper is not None and native_topic and len(market) < maximum_sources:
        try:
            native_market, native_market_audits = _collect_domain(
                "market",
                [native_topic],          # topic in user's language as the query
                native_serper.search, resolved_crossref, url_checker,
                resolved_date, normalized_topic,
                minimum_sources=0,
                maximum_sources=maximum_sources - len(market),
                blocked_dois={src.doi for src in academic if src.doi is not None},
                blocked_titles={src.title for src in academic}
                              | {src.title for src in market},
            )
            all_audits.extend(native_market_audits)
            market.extend(native_market)
        except SourceCollectionError:
            pass

    _academic_before = list(academic)
    # When a paper_seed is present it will contribute one guaranteed academic source,
    # so lower min_keep by 1 to avoid discarding valid search results unnecessarily.
    _ac_min_keep = 2 if paper_seed is not None else 3
    academic = _filter_by_relevance(academic, normalized_topic, min_score=3, min_keep=_ac_min_keep)
    _record_relevance_filter(_academic_before, academic, "academic", all_audits, min_score=3)

    _patents_before = list(patents)
    patents  = _filter_by_relevance(patents,  normalized_topic, min_score=1, min_keep=1)
    _record_relevance_filter(_patents_before, patents, "patent", all_audits, min_score=1)

    _market_before = list(market)
    market   = _filter_by_relevance(market,   normalized_topic, min_score=2, min_keep=2,
                                    skip_domain_filter=True)
    _record_relevance_filter(_market_before, market, "market", all_audits, min_score=2)
    if paper_seed is not None:
        academic = [paper_seed] + academic
    _renumber(academic, "A")
    _renumber(patents, "P")
    _renumber(market, "M")

    # Extract unique competitor/assignee names from patent sources.
    _GENERIC_ASSIGNEES = frozenset({
        "uspto", "lens.org", "serper", "google", "wipo", "epo",
        "patentsview", "justia", "espacenet", "unknown", "",
        "patent applicant",  # Lens fallback when no applicant extracted
    })
    seen_assignees: set[str] = set()
    patent_assignees: list[str] = []
    for ps in patents:
        raw = (ps.publisher or "").strip()
        for name in raw.split(","):
            name = name.strip()
            if name and name.lower() not in _GENERIC_ASSIGNEES and name not in seen_assignees:
                seen_assignees.add(name)
                patent_assignees.append(name)

    return SourceCollection(
        topic=normalized_topic,
        display_topic=native_topic or normalized_topic,
        output_language=lang_info["name"],
        localized_headings=localized_headings,
        weight_profile=weight_profile,
        collected_at=datetime.now(timezone.utc),
        academic_sources=academic,
        patent_sources=patents,
        patent_assignees=patent_assignees,
        market_sources=market,
        academic_queries=query_map["academic"],
        patent_queries=query_map["patent"],
        market_queries=query_map["market"],
        audit=all_audits,
    )
