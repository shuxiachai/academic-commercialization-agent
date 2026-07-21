"""External API client classes for the source collection pipeline.

Extracted from source_pipeline.py. Import anything you need from here;
source_pipeline re-exports these symbols for backwards compatibility.
"""

import json
import os
import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen


_TOPIC_PREPOSITIONS = frozenset({
    "for", "in", "with", "using", "via", "through", "by", "on", "at",
})

class SourceCollectionError(RuntimeError):
    """Raised when a truthful minimum source set cannot be assembled."""


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
        except (OSError, URLError, TimeoutError, json.JSONDecodeError):
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


_PM_MONTH = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

class PubMedClient:
    """Client for NCBI PubMed E-utilities. Free, no key required.
    Set NCBI_API_KEY to raise rate limit from 3 to 10 req/s.
    """

    _ESEARCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    _EFETCH   = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    _ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

    def __init__(self, *, timeout: int = 25, retries: int = 2) -> None:
        self.timeout = timeout
        self.retries = retries
        self._api_key = os.getenv("NCBI_API_KEY") or ""
        self._ua = "AcademicAgentSourceCollector/1.0"

    def _get(self, url: str) -> bytes:
        req = Request(url, headers={"User-Agent": self._ua})
        for attempt in range(self.retries + 1):
            try:
                with urlopen(req, timeout=self.timeout) as resp:
                    return resp.read()
            except HTTPError as exc:
                if exc.code == 429:
                    time.sleep(3 * (attempt + 1))
                    continue
                return b""
            except (URLError, TimeoutError, OSError):
                if attempt >= self.retries:
                    return b""
                time.sleep(0.75 * (attempt + 1))
        return b""

    def search(self, topic: str, rows: int = 15) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "db": "pubmed",
            "term": topic,
            "retmax": min(rows, 100),
            "retmode": "json",
            "sort": "relevance",
        }
        if self._api_key:
            params["api_key"] = self._api_key
        raw = self._get(f"{self._ESEARCH}?{urlencode(params)}")
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        ids = data.get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []

        fetch_params: dict[str, Any] = {
            "db": "pubmed",
            "id": ",".join(ids),
            "rettype": "xml",
            "retmode": "xml",
        }
        if self._api_key:
            fetch_params["api_key"] = self._api_key
        xml_bytes = self._get(f"{self._EFETCH}?{urlencode(fetch_params)}")
        return self._parse_xml(xml_bytes) if xml_bytes else []

    def _parse_xml(self, xml_bytes: bytes) -> list[dict[str, Any]]:
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError:
            return []
        results = []
        for article in root.findall(".//PubmedArticle"):
            try:
                rec = self._parse_article(article)
                if rec:
                    results.append(rec)
            except (AttributeError, TypeError, ValueError):
                continue
        return results

    def _parse_article(self, article: Any) -> dict[str, Any] | None:
        import xml.etree.ElementTree as ET
        medline = article.find("MedlineCitation")
        if medline is None:
            return None
        art = medline.find("Article")
        if art is None:
            return None

        title_el = art.find("ArticleTitle")
        title = ET.tostring(title_el, encoding="unicode", method="text").strip() if title_el is not None else ""
        if not title:
            return None

        abstract_parts = [
            ET.tostring(t, encoding="unicode", method="text").strip()
            for t in art.findall(".//AbstractText")
        ]
        abstract = " ".join(p for p in abstract_parts if p)

        doi = ""
        for id_el in art.findall(".//ELocationID"):
            if id_el.get("EIdType") == "doi":
                doi = (id_el.text or "").strip().lower()
                break
        if not doi:
            for id_el in (medline.findall(".//ArticleId") + article.findall(".//ArticleId")):
                if id_el.get("IdType") == "doi":
                    doi = (id_el.text or "").strip().lower()
                    break

        pmid_el = medline.find("PMID")
        pmid = (pmid_el.text or "").strip() if pmid_el is not None else ""

        journal_el = art.find(".//Journal/Title") or art.find(".//Journal/ISOAbbreviation")
        journal = (journal_el.text or "PubMed").strip() if journal_el is not None else "PubMed"

        pub_date = ""
        for date_el in art.findall(".//PubDate"):
            year_el = date_el.find("Year")
            month_el = date_el.find("Month")
            if year_el is not None and year_el.text:
                yr = year_el.text.strip()
                mo_raw = (month_el.text or "").strip() if month_el is not None else ""
                mo = _PM_MONTH.get(mo_raw[:3].lower(), mo_raw[:2].zfill(2) if mo_raw.isdigit() else "01")
                pub_date = f"{yr}-{mo}-01"
                break

        return {"title": title, "abstract": abstract, "doi": doi, "pmid": pmid, "journal": journal, "pub_date": pub_date}

    def get_mesh_terms(self, topic: str, max_terms: int = 3) -> list[str]:
        """Return MeSH controlled-vocabulary terms related to the topic.

        Uses NCBI ESearch on the 'mesh' database, then ESummary to resolve term
        names.  Biomedical topics benefit greatly from MeSH-structured queries
        (e.g. "large language models" → "Natural Language Processing" [MeSH]).
        Returns an empty list on any failure.
        """
        params: dict[str, Any] = {
            "db": "mesh", "term": topic,
            "retmax": max_terms * 2, "retmode": "json",
        }
        if self._api_key:
            params["api_key"] = self._api_key
        raw = self._get(f"{self._ESEARCH}?{urlencode(params)}")
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []

        # Fast path: extract MeSH terms directly from translation stack.
        terms: list[str] = []
        for entry in data.get("esearchresult", {}).get("translationstack", []):
            if isinstance(entry, dict) and entry.get("field") == "MeSH Terms":
                raw_term = entry.get("term", "")
                clean = re.sub(r'\[MeSH Terms\]$', '', raw_term, flags=re.IGNORECASE)
                clean = clean.strip().strip('"')
                if clean and len(clean) > 2:
                    terms.append(clean)
        if terms:
            return list(dict.fromkeys(terms))[:max_terms]

        # Fallback: resolve IDs via ESummary.
        ids = data.get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []
        sum_params: dict[str, Any] = {
            "db": "mesh", "id": ",".join(ids[:max_terms]),
            "retmode": "json",
        }
        if self._api_key:
            sum_params["api_key"] = self._api_key
        raw_sum = self._get(f"{self._ESUMMARY}?{urlencode(sum_params)}")
        if not raw_sum:
            return []
        try:
            sum_data = json.loads(raw_sum)
        except json.JSONDecodeError:
            return []
        result = sum_data.get("result", {})
        for mid in ids[:max_terms]:
            entry = result.get(str(mid), {})
            name = entry.get("ds_name") or ""
            if name:
                terms.append(str(name))
        return list(dict.fromkeys(terms))[:max_terms]

    def search_mesh(self, mesh_terms: list[str], rows: int = 10) -> list[dict[str, Any]]:
        """Search PubMed using MeSH controlled-vocabulary terms.

        Constructs an OR query of the form:
            ("term1"[MeSH Terms] OR "term2"[MeSH Terms])
        Falls back to a plain-text search if no terms provided.
        """
        if not mesh_terms:
            return []
        mesh_query = " OR ".join(f'"{t}"[MeSH Terms]' for t in mesh_terms)
        return self.search(f"({mesh_query})", rows=rows)

class ArxivClient:
    """Client for the arXiv e-print API. Free, no key required.
    Covers CS / AI / physics / biology / economics preprints.
    API docs: https://info.arxiv.org/help/api/index.html
    """

    _URL = "https://export.arxiv.org/api/query"
    _UA  = "AcademicAgentSourceCollector/1.0"
    _ATOM   = "http://www.w3.org/2005/Atom"
    _ARXIV_NS = "http://arxiv.org/schemas/atom"

    def __init__(self, *, timeout: int = 30, retries: int = 2) -> None:
        self.timeout = timeout
        self.retries = retries

    def search(self, topic: str, rows: int = 10) -> list[dict[str, Any]]:
        params = urlencode({
            "search_query": f"all:{topic}",
            "max_results": min(rows, 50),
            "sortBy": "relevance",
            "sortOrder": "descending",
        })
        request = Request(f"{self._URL}?{params}", headers={"User-Agent": self._UA})
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as resp:
                    return self._parse_feed(resp.read())
            except HTTPError as exc:
                if exc.code == 429:
                    time.sleep(5 * (attempt + 1))
                    continue
                return []
            except (URLError, TimeoutError, OSError):
                if attempt >= self.retries:
                    return []
                time.sleep(1.5 * (attempt + 1))
        return []

    def _parse_feed(self, xml_bytes: bytes) -> list[dict[str, Any]]:
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError:
            return []
        results: list[dict[str, Any]] = []
        ns, ans = self._ATOM, self._ARXIV_NS
        for entry in root.findall(f"{{{ns}}}entry"):
            try:
                title_el = entry.find(f"{{{ns}}}title")
                title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""
                if not title:
                    continue

                summary_el = entry.find(f"{{{ns}}}summary")
                abstract = (summary_el.text or "").strip().replace("\n", " ") if summary_el is not None else ""

                id_el = entry.find(f"{{{ns}}}id")
                arxiv_url = (id_el.text or "").strip() if id_el is not None else ""
                m = re.search(r"arxiv\.org/abs/(\d{4}\.\d{4,5})", arxiv_url, re.IGNORECASE)
                if m:
                    arxiv_url = f"https://arxiv.org/abs/{m.group(1)}"

                doi_el = entry.find(f"{{{ans}}}doi")
                doi = (doi_el.text or "").strip() if doi_el is not None else ""

                pub_el = entry.find(f"{{{ns}}}published")
                pub_date = pub_el.text.strip()[:10] if pub_el is not None and pub_el.text else ""

                authors = [
                    (a.find(f"{{{ns}}}name").text or "").strip()
                    for a in entry.findall(f"{{{ns}}}author")
                    if a.find(f"{{{ns}}}name") is not None
                ]
                author_str = ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")

                results.append({
                    "title": title, "abstract": abstract,
                    "arxiv_url": arxiv_url, "doi": doi,
                    "pub_date": pub_date, "authors": author_str,
                })
            except (AttributeError, TypeError, ValueError):
                continue
        return results


_PATENT_STOPWORDS: frozenset[str] = frozenset(
    {"for", "with", "and", "the", "of", "in", "to", "a", "an"}
)
_PATENT_MAX_QUERY_WORDS: int = 8


def _patent_keywords(topic: str, max_words: int = _PATENT_MAX_QUERY_WORDS) -> str:
    """Return the first ``max_words`` content words from *topic*, skipping stopwords."""
    words = [w for w in topic.split() if w.lower() not in _PATENT_STOPWORDS]
    return " ".join(words[:max_words])

def _http_fetch_json(
    request: Request,
    *,
    retries: int,
    timeout: int,
    backoff: float = 0.75,
) -> "dict[str, Any] | list[Any] | None":
    """Fetch *request* and return the parsed JSON body.

    Retries on transient network / decode errors with exponential backoff.
    Returns ``None`` when retries are exhausted or the response is not JSON
    (e.g. when a retired API endpoint returns an HTML portal page).
    Raises ``HTTPError`` so callers can handle auth / rate-limit codes.
    """
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as resp:
                raw = resp.read()
            if raw.lstrip()[:1] == b"<":
                return None  # HTML page — endpoint likely retired or redirected
            return json.loads(raw.decode("utf-8"))
        except HTTPError:
            raise
        except (URLError, TimeoutError, OSError, json.JSONDecodeError):
            if attempt >= retries:
                return None
            time.sleep(backoff * (attempt + 1))
    return None

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
    # referenced_works is fetched separately (per-paper) for snowballing so we
    # don't bloat every search response with large ID lists.

    def __init__(self, *, timeout: int = 20, retries: int = 2) -> None:
        self.timeout = timeout
        self.retries = retries
        mailto = os.getenv("OPENALEX_MAILTO") or os.getenv("CROSSREF_MAILTO")
        ua = "AcademicAgentSourceCollector/1.0"
        self.headers = {"User-Agent": f"{ua} (mailto:{mailto})" if mailto else ua}

    def search(self, topic: str, rows: int = 15) -> list[dict[str, Any]]:
        # Use default.search (title + abstract) with the core noun phrase so we
        # catch papers where the concept appears in the abstract but not the title.
        # Truncating to the core phrase still avoids over-broad matches from
        # secondary qualifiers like "for grid energy storage".
        core = _topic_core_phrase(topic)
        params = urlencode({
            "filter": f"default.search:{core}",
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
        except (OSError, URLError, TimeoutError, json.JSONDecodeError, ValueError):
            return None

    def fetch_referenced_works(self, doi: str, top_n: int = 25) -> list[str]:
        """Return OpenAlex IDs of works cited by the paper with the given DOI.

        Used for citation snowballing: seed a new search from the references of
        high-quality accepted papers.
        """
        url = f"{self._BASE}/https://doi.org/{doi}?select=referenced_works"
        request = Request(url, headers=self.headers)
        try:
            with urlopen(request, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return list(data.get("referenced_works") or [])[:top_n]
        except (OSError, URLError, TimeoutError, json.JSONDecodeError, ValueError):
            return []

    def fetch_works_by_ids(self, openalex_ids: list[str], rows: int = 15) -> list[dict[str, Any]]:
        """Fetch work metadata for a list of OpenAlex IDs (e.g. from referenced_works).

        IDs may be short ('W2964126049') or full URLs; both are accepted by the API.
        Returns results sorted by cited_by_count descending.
        """
        if not openalex_ids:
            return []
        # API allows pipe-separated filter; cap at 50 IDs to stay under URL length limits.
        ids_param = "|".join(str(i) for i in openalex_ids[:50])
        params = urlencode({
            "filter": f"openalex_id:{ids_param}",
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

    def search_by_topic(self, topic_id: str, rows: int = 10) -> list[dict[str, Any]]:
        """Return high-citation papers in the same OpenAlex topic cluster.

        topic_id is the full OpenAlex topic URL, e.g.
        'https://openalex.org/T12345' or just 'T12345'.
        """
        params = urlencode({
            "filter": f"topics.id:{topic_id}",
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


class LensPatentClient:
    """Client for the Lens.org Patent Search API (free after registration).
    Set LENS_API_KEY to enable; if absent the client silently returns no results.
    Sign up at https://www.lens.org/lens/user/subscriptions
    """

    _URL = "https://api.lens.org/patent/search"

    def __init__(self, api_key: str | None = None, *, timeout: int = 25, retries: int = 2) -> None:
        self.api_key = api_key or os.getenv("LENS_API_KEY") or ""
        self.timeout = timeout
        self.retries = retries

    def search(self, topic: str, rows: int = 10) -> list[dict[str, Any]]:
        if not self.api_key:
            return []
        kw = _patent_keywords(topic)
        body = {
            "query": {
                "bool": {
                    "should": [
                        {"match": {"title": {"query": kw, "boost": 2}}},
                        {"match": {"abstract": kw}},
                        {"match": {"claims": kw}},
                    ]
                }
            },
            "size": min(rows, 50),
            "include": ["lens_id", "biblio", "abstract", "jurisdiction"],
            "sort": [{"_score": "desc"}],
        }
        request = Request(
            self._URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "AcademicAgentSourceCollector/1.0",
            },
            method="POST",
        )
        for attempt in range(self.retries + 1):
            try:
                payload = _http_fetch_json(request, retries=self.retries, timeout=self.timeout)
            except HTTPError as exc:
                if exc.code in {400, 401, 403}:
                    import warnings
                    body_text = ""
                    try:
                        body_text = exc.read().decode("utf-8", errors="replace")[:300]
                    except OSError:
                        pass
                    hint = (
                        "check LENS_API_KEY and trial plan scope"
                        if exc.code in {401, 403}
                        else "bad request — likely an invalid 'include' field name"
                    )
                    warnings.warn(
                        f"Lens.org API returned HTTP {exc.code} ({hint}): {body_text}"
                    )
                    return []
                if exc.code == 429:
                    time.sleep(5 * (attempt + 1))
                    continue
                return []
            if payload is None:
                return []
            if not payload.get("data"):
                import warnings
                warnings.warn(
                    f"Lens.org returned 0 results for keywords {kw!r} "
                    f"(total={payload.get('total', '?')}); "
                    f"response keys: {list(payload.keys())}"
                )
            return payload.get("data") or []
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

