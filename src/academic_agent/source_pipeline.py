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
from urllib.parse import quote, unquote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

from academic_agent.evidence import EvidenceSource, _WEIGHT_PROFILES, check_public_url


Domain = Literal["academic", "patent", "market"]

# ── Weight profile detection ──────────────────────────────────────────────────
# Substring markers are matched against the lower-cased English topic.
# Biomedical is checked first (more specific); industrial is the default.
_BIOMEDICAL_MARKERS: tuple[str, ...] = (
    "drug ", "therapy", "vaccine", "clinical trial", "pharmaceutical",
    "diagnostic", "implant", "surgical", "gene editing", "cell therapy",
    "gene therapy", "medical device", "antibody", "in vitro", "in vivo",
    "oncology", "cancer treatment", "immunotherapy",
)
_MATERIAL_MARKERS: tuple[str, ...] = (
    "catalyst", "catalysis", "polymer", "thin film", "nanoparticle",
    "nanomaterial", "graphene", "ceramic ", "composite material",
    "deposition", "crystal structure", "synthesis route",
    "perovskite", "solar cell", "photovoltaic", "semiconductor",
    "electrode", "electrolyte", "superconductor", "alloy", "coating",
    "metamaterial", "2d material", "carbon nanotube",
)


def _detect_weight_profile(topic: str) -> str:
    """Return the scoring weight profile name for an English topic string."""
    t = topic.lower()
    if any(m in t for m in _BIOMEDICAL_MARKERS):
        return "biomedical"
    if any(m in t for m in _MATERIAL_MARKERS):
        return "material_science"
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
_TOPIC_PREPOSITIONS = frozenset({
    "for", "in", "with", "using", "via", "through", "by", "on", "at",
})
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
    # Energy / utility industry trade press
    "utilitydive.com",
    "greentechmedia.com",
    "energymonitor.ai",
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
    "iea.org",
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
_OFFICIAL_DISCLOSURE_PATH_MARKERS = (
    "/blog/",
    "/company/",
    "/investor",
    "/media/",
    "/news/",
    "/press",
)
# Sources whose evidence_summary is shorter than this are rejected as too thin
# to provide meaningful content for LLM analysis.
# Set to 100: real Serper snippets are typically 100-160 chars; 150 was too
# aggressive and caused legitimate market sources to be rejected.
_MIN_EVIDENCE_SUMMARY_CHARS = 100

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


class SourceCollectionError(RuntimeError):
    """Raised when a truthful minimum source set cannot be assembled."""


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
    academic_sources: list[EvidenceSource] = Field(min_length=3)
    patent_sources: list[EvidenceSource] = Field(min_length=1)
    market_sources: list[EvidenceSource] = Field(min_length=2)
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


class SerperClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        n_results: int = 10,
        timeout: int = 20,
        gl: str = "us",
        hl: str = "en",
    ) -> None:
        self.api_key = api_key or os.getenv("SERPER_API_KEY")
        if not self.api_key:
            raise SourceCollectionError("SERPER_API_KEY is required for source retrieval.")
        self.n_results = n_results
        self.timeout = timeout
        self.gl = gl
        self.hl = hl

    def search(self, query: str) -> dict[str, Any]:
        body: dict[str, Any] = {"q": query, "num": self.n_results}
        if self.gl != "us" or self.hl != "en":
            body["gl"] = self.gl
            body["hl"] = self.hl
        request = Request(
            "https://google.serper.dev/search",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json",
                "User-Agent": "AcademicAgentSourceCollector/1.0",
            },
            method="POST",
        )
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    raise SourceCollectionError("Serper returned a non-object response.")
                return payload
            except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                last_exc = exc
                time.sleep(2 ** attempt)
            except HTTPError as exc:
                if exc.code in {429, 500, 502, 503, 504}:
                    last_exc = exc
                    time.sleep(2 ** attempt)
                else:
                    raise SourceCollectionError(
                        f"Serper search failed for {query!r}: {exc}"
                    ) from exc
        raise SourceCollectionError(
            f"Serper search failed for {query!r} after 3 attempts: {last_exc}"
        ) from last_exc


class OpenAlexClient:
    """Client for the OpenAlex Works API (free, no key required)."""

    _BASE = "https://api.openalex.org/works"
    _SELECT = ",".join([
        "id", "title", "doi", "publication_date",
        "primary_location", "cited_by_count", "abstract_inverted_index", "topics",
    ])

    def __init__(self, *, timeout: int = 20, retries: int = 2) -> None:
        self.timeout = timeout
        self.retries = retries
        mailto = os.getenv("OPENALEX_MAILTO") or os.getenv("CROSSREF_MAILTO")
        ua = "AcademicAgentSourceCollector/1.0"
        self.headers = {"User-Agent": f"{ua} (mailto:{mailto})" if mailto else ua}

    def search(self, topic: str, rows: int = 15) -> list[dict[str, Any]]:
        # Use the core noun phrase (before prepositions) with title.search.
        # Full topic string is too broad: "solid-state batteries for grid energy
        # storage" would also match solid-state transformer + energy storage papers.
        core = _topic_core_phrase(topic)
        params = urlencode({
            "filter": f"title.search:{core}",
            "sort": "cited_by_count:desc",
            "per-page": min(rows, 50),
            "select": self._SELECT,
        })
        url = f"{self._BASE}?{params}"
        request = Request(url, headers=self.headers)
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                return payload.get("results") or []
            except HTTPError as exc:
                if exc.code == 429:
                    time.sleep(2 ** attempt)
                    continue
                return []
            except (URLError, TimeoutError, OSError, json.JSONDecodeError):
                if attempt >= self.retries:
                    return []
                time.sleep(0.75 * (attempt + 1))
        return []

    def fetch_citation_by_doi(self, doi: str) -> int | None:
        """Return cited_by_count for a single paper by DOI. Returns None on failure."""
        url = f"{self._BASE}/https://doi.org/{doi}?select=cited_by_count"
        request = Request(url, headers=self.headers)
        try:
            with urlopen(request, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return int(data.get("cited_by_count") or 0)
        except Exception:
            return None

    def search_recent(self, topic: str, since_year: int = 2023, rows: int = 15) -> list[dict[str, Any]]:
        """Search OpenAlex for papers published since_year or later, sorted by date desc."""
        core = _topic_core_phrase(topic)
        params = urlencode({
            "filter": f"title.search:{core},publication_year:>{since_year - 1}",
            "sort": "publication_date:desc",
            "per-page": min(rows, 50),
            "select": self._SELECT,
        })
        url = f"{self._BASE}?{params}"
        request = Request(url, headers=self.headers)
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                return payload.get("results") or []
            except HTTPError as exc:
                if exc.code == 429:
                    time.sleep(2 ** attempt)
                    continue
                return []
            except (URLError, TimeoutError, OSError, json.JSONDecodeError):
                if attempt >= self.retries:
                    return []
                time.sleep(0.75 * (attempt + 1))
        return []


class SemanticScholarClient:
    """Client for the Semantic Scholar Academic Graph API.

    Free to use without a key (1 req/s). Optional API key raises limits to
    10 req/s — set SEMANTIC_SCHOLAR_API_KEY in the environment to activate.
    """

    _BASE_URL = "https://api.semanticscholar.org/graph/v1/paper"
    _SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
    _FIELDS = "title,abstract,year,citationCount,externalIds,publicationVenue,publicationDate"

    def __init__(self, *, timeout: int = 15, retries: int = 2) -> None:
        self.timeout = timeout
        self.retries = retries
        key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        self.headers: dict[str, str] = {"User-Agent": "AcademicAgentSourceCollector/1.0"}
        if key:
            self.headers["x-api-key"] = key

    def get_abstract_by_doi(self, doi: str) -> str:
        """Fetch abstract text for a paper by DOI from S2. Returns '' on failure."""
        url = f"{self._BASE_URL}/DOI:{quote(doi, safe='')}?fields=abstract"
        request = Request(url, headers=self.headers)
        try:
            with urlopen(request, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return str(payload.get("abstract") or "")
        except Exception:
            return ""

    def search(self, topic: str, rows: int = 15) -> list[dict[str, Any]]:
        params = urlencode({
            "query": topic,
            "limit": min(rows, 100),
            "fields": self._FIELDS,
        })
        request = Request(f"{self._SEARCH_URL}?{params}", headers=self.headers)
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                return payload.get("data") or []
            except HTTPError as exc:
                if exc.code == 429:
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    wait = float(retry_after) if retry_after else (5 * 2 ** attempt)
                    time.sleep(min(wait, 60))
                    continue
                return []
            except (URLError, TimeoutError, OSError, json.JSONDecodeError):
                if attempt >= self.retries:
                    return []
                time.sleep(0.75 * (attempt + 1))
        return []


class CrossrefClient:
    def __init__(self, *, timeout: int = 20, retries: int = 2) -> None:
        self.timeout = timeout
        self.retries = retries
        self.last_error: str | None = None
        mailto = os.getenv("CROSSREF_MAILTO")
        self.user_agent = "AcademicAgentSourceCollector/1.0"
        if mailto:
            self.user_agent += f" (mailto:{mailto})"

    def _request(self, url: str) -> dict[str, Any] | None:
        request = Request(url, headers={"User-Agent": self.user_agent})
        self.last_error = None
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    self.last_error = "Crossref returned a non-object response"
                    return None
                message = payload.get("message")
                if isinstance(message, dict):
                    return message
                self.last_error = "Crossref response has no message object"
                return None
            except HTTPError as exc:
                if exc.code == 404:
                    return None
                self.last_error = f"Crossref HTTP {exc.code}"
                retryable = exc.code in {408, 429, 500, 502, 503, 504}
                if not retryable or attempt >= self.retries:
                    return None
            except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                self.last_error = f"Crossref request failed: {exc}"
                if attempt >= self.retries:
                    return None
            time.sleep(0.75 * (attempt + 1))
        return None

    def lookup_doi(self, doi: str) -> dict[str, Any] | None:
        return self._request(f"https://api.crossref.org/works/{quote(doi, safe='')}")

    def search_title(self, title: str) -> list[dict[str, Any]]:
        params = urlencode({"query.title": title, "rows": 5})
        message = self._request(f"https://api.crossref.org/works?{params}")
        if not message:
            return []
        items = message.get("items")
        return [item for item in items or [] if isinstance(item, dict)]


def _clean_text(value: str) -> str:
    return " ".join(html.unescape(_TAG_PATTERN.sub(" ", value)).split())


def _safe_summary(snippet: str, title: str) -> str:
    cleaned = _clean_text(snippet)
    if len(cleaned) >= 20:
        return cleaned[:1500]
    return f"Verified search result for the source titled {title}."


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, "")
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
    return len(overlap) >= 2

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
        len(crossref_abstract) < 20
        and re.search(r"(?:https?://)?doi\.org", snippet, flags=re.IGNORECASE)
        and _extract_doi(snippet) is None
    ):
        return None, "search snippet contains a truncated or unverifiable DOI reference"
    if len(crossref_abstract) >= 20:
        evidence_summary = crossref_abstract[:1500]
        summary_basis = "Crossref abstract"
    else:
        evidence_summary = _safe_summary(snippet, title)
        summary_basis = "DOI-consistent search snippet"
    published = _published_date(item)
    if published and published > accessed_date:
        return None, "Crossref publication date is in the future"
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
            credibility_tier="high",
            credibility_reason=(
                f"DOI, title, and topic matched; evidence summary uses {summary_basis}."
            ),
            evidence_summary=evidence_summary,
        ),
        "",
    )


def _topic_core_phrase(topic: str) -> str:
    """Return the core noun phrase of a topic (stop at the first preposition).

    'solid-state batteries for grid energy storage' → 'solid-state batteries'
    'CRISPR gene editing applications in agriculture' → 'CRISPR gene editing applications'
    'perovskite solar cells' → 'perovskite solar cells'

    Using only the core phrase in OpenAlex title.search avoids false matches
    from secondary words like 'energy' or 'storage' that appear in unrelated fields.
    """
    words = topic.split()
    core: list[str] = []
    for word in words:
        if word.lower() in _TOPIC_PREPOSITIONS:
            break
        core.append(word)
    return " ".join(core[:6]) if core else topic


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
    if len(abstract) < 40 and s2_client is not None:
        abstract = s2_client.get_abstract_by_doi(doi)
    if len(abstract) < 40:
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
    if cited == 0 and days_since_pub is not None and days_since_pub <= 90:
        credibility_reason = (
            "OpenAlex record: DOI verified, peer-reviewed journal. "
            f"Newly published ({days_since_pub}d ago); 0 citations is expected, "
            "not a quality signal."
        )
    else:
        credibility_reason = (
            f"OpenAlex record: DOI verified, peer-reviewed journal, "
            f"{cited:,} citations."
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
            credibility_tier="high",
            credibility_reason=credibility_reason,
            evidence_summary=abstract[:1500],
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
    if len(abstract) < 40:
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
            credibility_tier="high",
            credibility_reason=(
                f"Semantic Scholar record: DOI verified, peer-reviewed journal, "
                f"{cited:,} citations."
            ),
            evidence_summary=abstract[:1500],
            citation_count=cited,
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


def _topic_keywords(topic: str) -> frozenset[str]:
    """Extract meaningful lowercase words from a topic string."""
    words = re.findall(r"[a-z]{3,}", topic.lower())
    return frozenset(w for w in words if w not in _STOP_WORDS)


def _topic_bigrams(topic: str) -> frozenset[str]:
    """Extract consecutive 2-word phrases from topic keywords (after stop-word removal)."""
    words = [w for w in re.findall(r"[a-z]{3,}", topic.lower()) if w not in _STOP_WORDS]
    return frozenset(f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1))


def _normalise_text(text: str) -> str:
    """Lowercase and replace hyphens/underscores with spaces for consistent matching."""
    return re.sub(r"[-_]", " ", text.lower())


_COMPARISON_TITLE_MARKERS: frozenset[str] = frozenset({
    "compared with", "comparison of", " versus ", " vs. ", " vs ",
    "in comparison", "as compared to", "relative to",
})


def _relevance_score(source: "EvidenceSource", keywords: frozenset[str], bigrams: frozenset[str]) -> int:
    """Score relevance: 1 pt per keyword hit + 2 pts per bigram hit.

    Papers whose title has no topic keywords AND contains comparison markers
    are penalised by 2 pts — they are typically off-topic comparison papers.
    """
    if not keywords:
        return 1
    title_text = _normalise_text(source.title)
    body_text  = title_text + " " + _normalise_text(source.evidence_summary)
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
) -> list["EvidenceSource"]:
    """Filter low-relevance sources and sort survivors by relevance score descending."""
    keywords = _topic_keywords(topic)
    bigrams  = _topic_bigrams(topic)
    scored   = sorted(
        [(s, _relevance_score(s, keywords, bigrams)) for s in sources],
        key=lambda x: x[1],
        reverse=True,
    )
    kept = [s for s, sc in scored if sc >= min_score]
    return kept if len(kept) >= min_keep else [s for s, _ in scored]


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
        ),
        "",
    )


def _queries(
    topic: str,
    *,
    native_topic: str | None = None,
    patent_cc: str = "",
) -> dict[Domain, list[str]]:
    # Short-form topic for patent search: strip parenthetical qualifiers and
    # take the first 4 words so site:-restricted queries match patent titles.
    _pat_clean = re.sub(r"\s*\([^)]*\)", "", topic).strip()
    _pat_short = " ".join(_pat_clean.split()[:4])
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
        f"{topic} company commercial deployment",
        f"{topic} government standards pilot",
        f"{topic} manufacturing commercialization",
        f"{topic} product manufacturer revenue commercial sales 2024",
        f"{topic} startup funding FDA cleared CE marked clinical commercial",
        f"{topic} market size billion company investment startup",
    ]
    if native_topic and native_topic != topic:
        # One native-language query so the native Serper pass has a base query.
        market.append(native_topic)

    return {
        "academic": [
            f"{topic} peer reviewed DOI",
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
    core_words = {w for w in _WORD_PATTERN.findall(core.lower()) if len(w) >= 4}
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
    seen_patent_titles: set[str] = set()
    seen_academic_title_keys: set[str] = set()
    seen_locators: set[str] = set()
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

    for query in queries:
        response = searcher(query)
        organic = response.get("organic", [])
        results = [item for item in organic if isinstance(item, dict)]
        audit = SearchAudit(domain=domain, query=query, result_count=len(results))
        for result in results[:8]:
            if len(accepted) >= maximum_sources:
                break
            source_id = f"{prefix}{len(accepted) + 1}"
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
                            if _title_similarity(result_title, title) >= 0.92
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
                    result, source_id, crossref, accessed_date, research_topic
                )
            else:
                source, reason = _web_source(
                    result, source_id, domain, accessed_date, url_checker
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
            accepted.append(source)
            audit.accepted_source_ids.append(source.source_id)
        audits.append(audit)
        if len(accepted) >= maximum_sources:
            break

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
) -> tuple[list[EvidenceSource], list[SearchAudit]]:
    """Collect academic sources: dual-track (recent 2023+ + high-citation) from OpenAlex, S2 supplement."""
    fetch_rows = max(20, maximum_sources * 4)
    recent_slots = (maximum_sources + 1) // 2  # ceil(max/2) slots reserved for recent papers

    # ── Track A: recent papers (2023+), sorted by publication date desc ──────
    recent_works = openalex.search_recent(topic, since_year=date.today().year - 3, rows=fetch_rows)
    recent_audit = SearchAudit(
        domain="academic",
        query=f"[OpenAlex-Recent 2023+] {topic}",
        result_count=len(recent_works),
    )

    # ── Track B: high-citation papers, sorted by citation count desc ─────────
    cited_works = openalex.search(topic, rows=fetch_rows)
    cited_audit = SearchAudit(
        domain="academic",
        query=f"[OpenAlex-Cited] {topic}",
        result_count=len(cited_works),
    )

    accepted: list[EvidenceSource] = []
    seen_dois: set[str] = set()
    # Word-normalised title dedup catches same-paper published in multiple journal
    # editions under different DOIs (e.g. Angewandte Chemie ange/anie parallel issues).
    seen_title_keys: set[str] = set()
    audits: list[SearchAudit] = [recent_audit, cited_audit]

    def _title_key(title: str) -> str:
        return " ".join(_WORD_PATTERN.findall(title.lower()))

    def _try_add(source: EvidenceSource, audit: SearchAudit) -> bool:
        """Deduplicate by DOI and by normalised title. Returns True if accepted."""
        doi_key = (source.doi or "").lower()
        if doi_key and doi_key in seen_dois:
            audit.rejected_reasons.append(f"duplicate DOI: {doi_key}")
            return False
        tkey = _title_key(source.title)
        if tkey and tkey in seen_title_keys:
            audit.rejected_reasons.append(f"duplicate title (parallel edition): {source.title}")
            return False
        if doi_key:
            seen_dois.add(doi_key)
        seen_title_keys.add(tkey)
        accepted.append(source)
        audit.accepted_source_ids.append(source.source_id)
        return True

    # Fill recent slots first
    for work in recent_works:
        if len(accepted) >= recent_slots:
            break
        source_id = f"A{len(accepted) + 1}"
        source, reason = _academic_source_from_openalex(work, source_id, accessed_date, topic, s2_client=s2)
        if source is None:
            recent_audit.rejected_reasons.append(reason)
            continue
        _try_add(source, recent_audit)

    # Fill remaining slots from high-citation track, skipping already-seen DOIs/titles
    for work in cited_works:
        if len(accepted) >= maximum_sources:
            break
        source_id = f"A{len(accepted) + 1}"
        source, reason = _academic_source_from_openalex(work, source_id, accessed_date, topic, s2_client=s2)
        if source is None:
            cited_audit.rejected_reasons.append(reason)
            continue
        _try_add(source, cited_audit)

    # ── Semantic Scholar supplement (when OpenAlex tracks fall short) ─────────
    if len(accepted) < maximum_sources:
        s2_papers = s2.search(topic, rows=fetch_rows)
        s2_audit = SearchAudit(
            domain="academic",
            query=f"[SemanticScholar] {topic}",
            result_count=len(s2_papers),
        )
        for paper in s2_papers:
            if len(accepted) >= maximum_sources:
                break
            source_id = f"A{len(accepted) + 1}"
            source, reason = _academic_source_from_s2(paper, source_id, accessed_date, topic)
            if source is None:
                s2_audit.rejected_reasons.append(reason)
                continue
            _try_add(source, s2_audit)
        audits.append(s2_audit)

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
    url_checker: UrlChecker = check_public_url,
    minimum_sources: int = 3,
    maximum_sources: int = 6,
    accessed_date: date | None = None,
) -> SourceCollection:
    # ── Language detection & translation ─────────────────────────────────────
    from academic_agent.language import (
        detect_language, get_lang_info,
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

    # Backfill citation_count for Crossref-sourced papers (citation_count=None).
    # Run concurrently — OpenAlex DOI lookup is free, ~150 ms each.
    _needs_citation = [src for src in academic if src.citation_count is None and src.doi]
    if _needs_citation:
        from concurrent.futures import ThreadPoolExecutor

        def _fetch_citation(src: EvidenceSource) -> None:
            cited = resolved_openalex.fetch_citation_by_doi(src.doi)  # type: ignore[arg-type]
            if cited is not None:
                src.citation_count = cited

        with ThreadPoolExecutor(max_workers=4) as _pool:
            list(_pool.map(_fetch_citation, _needs_citation))

    if len(academic) < minimum_sources:
        raise SourceCollectionError(
            f"academic retrieval produced {len(academic)} validated sources "
            f"(OpenAlex + Serper+Crossref combined); "
            f"at least {minimum_sources} are required."
        )

    # ── Patents: Serper ───────────────────────────────────────────────────────
    patents, patent_audits = _collect_domain(
        "patent",
        query_map["patent"],
        resolved_searcher, resolved_crossref, url_checker,
        resolved_date, normalized_topic,
        minimum_sources=1,
        maximum_sources=maximum_sources,
    )
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

    academic = _filter_by_relevance(academic, normalized_topic, min_score=2, min_keep=3)
    patents  = _filter_by_relevance(patents,  normalized_topic, min_score=1, min_keep=1)
    market   = _filter_by_relevance(market,   normalized_topic, min_score=2, min_keep=2)
    _renumber(academic, "A")
    _renumber(patents, "P")
    _renumber(market, "M")

    return SourceCollection(
        topic=normalized_topic,
        display_topic=native_topic or normalized_topic,
        output_language=lang_info["name"],
        localized_headings=localized_headings,
        weight_profile=weight_profile,
        collected_at=datetime.now(timezone.utc),
        academic_sources=academic,
        patent_sources=patents,
        market_sources=market,
        academic_queries=query_map["academic"],
        patent_queries=query_map["patent"],
        market_queries=query_map["market"],
        audit=all_audits,
    )
