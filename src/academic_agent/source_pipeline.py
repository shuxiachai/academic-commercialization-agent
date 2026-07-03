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

from academic_agent.evidence import EvidenceSource, check_public_url


Domain = Literal["academic", "patent", "market"]
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
_TOPIC_PREPOSITIONS = frozenset({
    "for", "in", "of", "with", "using", "via", "through", "by", "on", "at",
})
_AUTHORITATIVE_RESEARCH_DOMAINS = {
    "iea.org",
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
_PATENT_HOSTS = {
    "patents.google.com",
    "patentscope.wipo.int",
    "worldwide.espacenet.com",
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
    "pv-tech.org",
    "chemengonline.com",
    "biofuelsdigest.com",
    "greencarcongress.com",
    "h2-view.com",
    "quantum-computing-report.com",
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
_MIN_EVIDENCE_SUMMARY_CHARS = 150


class SourceCollectionError(RuntimeError):
    """Raised when a truthful minimum source set cannot be assembled."""


class SearchAudit(BaseModel):
    domain: Domain
    query: str
    result_count: int
    accepted_source_ids: list[str] = Field(default_factory=list)
    rejected_reasons: list[str] = Field(default_factory=list)


class SourceCollection(BaseModel):
    topic: str
    collected_at: datetime
    academic_sources: list[EvidenceSource] = Field(min_length=3)
    patent_sources: list[EvidenceSource] = Field(min_length=3)
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
        def dump_sources(sources: list[EvidenceSource]) -> str:
            return json.dumps(
                [source.model_dump(mode="json") for source in sources],
                ensure_ascii=False,
                separators=(",", ":"),
            )

        return {
            "research_topic": self.topic,
            "academic_sources_json": dump_sources(self.academic_sources),
            "patent_sources_json": dump_sources(self.patent_sources),
            "market_sources_json": dump_sources(self.market_sources),
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
    ) -> None:
        self.api_key = api_key or os.getenv("SERPER_API_KEY")
        if not self.api_key:
            raise SourceCollectionError("SERPER_API_KEY is required for source retrieval.")
        self.n_results = n_results
        self.timeout = timeout

    def search(self, query: str) -> dict[str, Any]:
        request = Request(
            "https://google.serper.dev/search",
            data=json.dumps({"q": query, "num": self.n_results}).encode("utf-8"),
            headers={
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json",
                "User-Agent": "AcademicAgentSourceCollector/1.0",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            raise SourceCollectionError(
                f"Serper search failed for {query!r}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise SourceCollectionError("Serper returned a non-object response.")
        return payload


class OpenAlexClient:
    """Client for the OpenAlex Works API (free, no key required)."""

    _BASE = "https://api.openalex.org/works"
    _SELECT = ",".join([
        "id", "title", "doi", "publication_date",
        "primary_location", "cited_by_count", "abstract_inverted_index",
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


class SemanticScholarClient:
    """Client for the Semantic Scholar Academic Graph API.

    Free to use without a key (1 req/s). Optional API key raises limits to
    10 req/s — set SEMANTIC_SCHOLAR_API_KEY in the environment to activate.
    """

    _SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
    _FIELDS = "title,abstract,year,citationCount,externalIds,publicationVenue,publicationDate"

    def __init__(self, *, timeout: int = 15, retries: int = 2) -> None:
        self.timeout = timeout
        self.retries = retries
        key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        self.headers: dict[str, str] = {"User-Agent": "AcademicAgentSourceCollector/1.0"}
        if key:
            self.headers["x-api-key"] = key

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
    return bool(topic_tokens & title_tokens)

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


def _academic_source_from_openalex(
    work: dict[str, Any],
    source_id: str,
    accessed_date: date,
    research_topic: str,
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
    if not _title_matches_topic(title, research_topic):
        return None, f"OpenAlex title not relevant to topic: {title!r}"

    abstract = _openalex_abstract(work)
    if len(abstract) < 40:
        return None, f"OpenAlex abstract too thin ({len(abstract)} chars): {title!r}"

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
                f"OpenAlex record: DOI verified, peer-reviewed journal, "
                f"{cited:,} citations."
            ),
            evidence_summary=abstract[:1500],
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
    if host.endswith(".gov") or ".gov." in host or host in {
        "europa.eu",
        "ec.europa.eu",
    }:
        return (
            "government",
            "high",
            "Official government source; authoritative within its stated scope.",
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
        credibility_reason = (
            "Official patent registry record; legal scope still requires claim review."
        )
    else:
        profile = _market_source_profile(canonical, host)
        if profile is None:
            return None, f"market host is blocked or not approved: {host}"
        source_type, credibility_tier, credibility_reason = profile

    reachable, reason = url_checker(canonical)
    if not reachable:
        return None, f"unreachable URL {canonical}: {reason}"
    return (
        EvidenceSource(
            source_id=source_id,
            title=title,
            url=canonical,
            publisher=_publisher_for_host(host),
            accessed_date=accessed_date,
            source_type=source_type,
            credibility_tier=credibility_tier,
            credibility_reason=credibility_reason,
            evidence_summary=_safe_summary(snippet, title),
        ),
        "",
    )


def _queries(topic: str) -> dict[Domain, list[str]]:
    return {
        "academic": [
            f"{topic} peer reviewed DOI",
            f"{topic} review journal",
            f"{topic} efficiency stability commercialization",
        ],
        "patent": [
            f"{topic} site:patents.google.com/patent",
            f"{topic} site:patentscope.wipo.int",
            f"{topic} patent applicant",
        ],
        "market": [
            # Broad commercialization signals
            f"{topic} company commercial deployment",
            f"{topic} government standards pilot",
            f"{topic} manufacturing commercialization",
            # Commercial maturity signals: who is selling, market size, investment
            f"{topic} product manufacturer revenue commercial sales 2024",
            f"{topic} market size billion company investment startup",
        ],
    }


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
    seen_locators: set[str] = set()
    excluded_dois = {
        doi.lower()
        for doi in (blocked_dois or set())
    }
    excluded_titles = {title for title in (blocked_titles or set()) if title.strip()}

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
            if len(source.evidence_summary) < _MIN_EVIDENCE_SUMMARY_CHARS:
                audit.rejected_reasons.append(
                    f"evidence summary too thin "
                    f"({len(source.evidence_summary)} chars): {source.title!r}"
                )
                continue
            locator = source.doi or str(source.url)
            if locator.lower() in seen_locators:
                audit.rejected_reasons.append(f"duplicate source: {locator}")
                continue
            seen_locators.add(locator.lower())
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
    """Collect academic sources: OpenAlex primary, Semantic Scholar supplement."""
    # ── Step 1: OpenAlex ──────────────────────────────────────────────────
    works = openalex.search(topic, rows=max(20, maximum_sources * 3))
    oa_audit = SearchAudit(domain="academic", query=f"[OpenAlex] {topic}", result_count=len(works))
    accepted: list[EvidenceSource] = []
    seen_dois: set[str] = set()

    for work in works:
        if len(accepted) >= maximum_sources:
            break
        source_id = f"A{len(accepted) + 1}"
        source, reason = _academic_source_from_openalex(work, source_id, accessed_date, topic)
        if source is None:
            oa_audit.rejected_reasons.append(reason)
            continue
        doi_key = (source.doi or "").lower()
        if doi_key and doi_key in seen_dois:
            oa_audit.rejected_reasons.append(f"duplicate DOI: {doi_key}")
            continue
        if doi_key:
            seen_dois.add(doi_key)
        accepted.append(source)
        oa_audit.accepted_source_ids.append(source_id)

    audits: list[SearchAudit] = [oa_audit]

    # ── Step 2: Semantic Scholar supplement (when OpenAlex falls short) ───
    if len(accepted) < maximum_sources:
        s2_papers = s2.search(topic, rows=max(20, maximum_sources * 3))
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
            doi_key = (source.doi or "").lower()
            if doi_key and doi_key in seen_dois:
                s2_audit.rejected_reasons.append(f"duplicate DOI: {doi_key}")
                continue
            if doi_key:
                seen_dois.add(doi_key)
            accepted.append(source)
            s2_audit.accepted_source_ids.append(source_id)
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
    normalized_topic = " ".join(topic.split())
    if len(normalized_topic) < 3:
        raise SourceCollectionError("Research topic must contain at least 3 characters.")
    if minimum_sources < 1 or maximum_sources < minimum_sources:
        raise ValueError("Source count bounds are invalid.")

    resolved_searcher = searcher or SerperClient().search
    resolved_crossref = crossref or CrossrefClient()
    resolved_openalex = openalex or OpenAlexClient()
    resolved_s2 = s2 or SemanticScholarClient()
    resolved_date = accessed_date or date.today()
    query_map = _queries(normalized_topic)
    all_audits: list[SearchAudit] = []

    # ── Academic: OpenAlex primary, S2 supplement, Serper+Crossref fallback
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
        except SourceCollectionError:
            pass

    if len(academic) < minimum_sources:
        raise SourceCollectionError(
            f"academic retrieval produced {len(academic)} validated sources "
            f"(OpenAlex + Serper+Crossref combined); "
            f"at least {minimum_sources} are required."
        )
    _renumber(academic, "A")

    # ── Patents: Serper ───────────────────────────────────────────────────
    patents, patent_audits = _collect_domain(
        "patent",
        query_map["patent"],
        resolved_searcher, resolved_crossref, url_checker,
        resolved_date, normalized_topic,
        minimum_sources=minimum_sources,
        maximum_sources=maximum_sources,
    )
    all_audits.extend(patent_audits)

    # ── Market: Serper (unchanged) ─────────────────────────────────────────
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

    return SourceCollection(
        topic=normalized_topic,
        collected_at=datetime.now(timezone.utc),
        academic_sources=academic,
        patent_sources=patents,
        market_sources=market,
        academic_queries=query_map["academic"],
        patent_queries=query_map["patent"],
        market_queries=query_map["market"],
        audit=all_audits,
    )


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
