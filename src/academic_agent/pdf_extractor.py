"""Extract structured contribution metadata from an uploaded academic PDF."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


_DOI_RE    = re.compile(r"\b(10\.\d{4,9}/[^\s,;<>\"')\]]+)", re.IGNORECASE)
_ARXIV_RE  = re.compile(r"arXiv[:\s]+(\d{4}\.\d{4,5})(?:v\d+)?", re.IGNORECASE)
_ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", re.IGNORECASE)

# Marks a synthesised DOI, as opposed to one registered with a real agency.
_PLACEHOLDER_DOI_PREFIX = "10.0000/uploaded-"


def _placeholder_doi(title: str) -> str:
    """Synthetic DOI for an upload with no verifiable public locator.

    EvidenceSource requires a URL or a DOI, so a paper that resolves to
    neither still needs one to travel through the pipeline as A1 at all.
    Deriving it from the title keeps it stable across re-uploads of the same
    paper (dedup and citation tracking both key off it) while staying
    obviously not a registered identifier to anything that reads it.
    """
    return f"{_PLACEHOLDER_DOI_PREFIX}{hashlib.md5(title.encode()).hexdigest()[:10]}"


class PaperContribution(BaseModel):
    """Structured contribution extracted from an academic paper."""

    title: str = Field(min_length=3)
    authors: str = ""
    doi: str | None = None
    url: str | None = None
    core_contribution: str = Field(min_length=20)
    application_domain: str = Field(min_length=3)
    key_metrics: list[str] = Field(default_factory=list)
    delta_from_prior: str = Field(min_length=10)
    commercialization_topic: str = Field(min_length=10)
    search_keywords: list[str] = Field(min_length=3)
    abstract_excerpt: str = ""


#: How many pages may be read from one document, however long it is.
#:
#: The selection below keeps at most seven pages, but choosing the middle two
#: by density meant reading every page first — so a 4,000-page upload was
#: parsed in full to discard 3,993 pages. The 50 MB upload cap does not bound
#: this: page count and byte count are close to unrelated, and a text-only PDF
#: reaches four figures well inside the limit. This is a public deployment with
#: two run slots, and parsing runs in a worker thread, so an unbounded scan is
#: reachable by anyone who can upload.
#:
#: Chosen so that no real paper changes behaviour. Journal articles run to tens
#: of pages, theses under a hundred; below the ceiling every page is read
#: exactly as before, and above it the middle is sampled evenly rather than
#: truncated — a 300-page document keeps candidates from its whole span, which
#: is where the results sections of the long documents actually are.
_MAX_PAGES_SCANNED = 120


def _pages_to_scan(n: int) -> list[int]:
    """Page indices to read: all of them, or head + tail + an even sample."""
    if n <= _MAX_PAGES_SCANNED:
        return list(range(n))
    head = list(range(min(3, n)))
    tail = list(range(max(0, n - 2), n))
    budget = _MAX_PAGES_SCANNED - len(set(head + tail))
    lo, hi = len(head), n - len(tail)
    step = (hi - lo) / budget
    middle = sorted({lo + int(i * step) for i in range(budget)})
    return sorted(set(head + middle + tail))


def extract_pdf_text(pdf_path: str | Path, max_chars: int = 7000) -> str:
    """Extract text from the highest-signal pages of a PDF.

    Strategy: first 3 pages (title/abstract/intro) + up to 2 middle pages
    with the highest character density (results/methods) + last 2 pages
    (conclusions/references).  Duplicates are removed; total is capped at
    max_chars so the LLM prompt stays within budget.

    At most _MAX_PAGES_SCANNED pages are read; see there for why.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise RuntimeError(
            "pypdfium2 is required. Install with: pip install pypdfium2"
        ) from exc

    with pdfium.PdfDocument(str(pdf_path)) as doc:
        n = len(doc)

        # Read the candidate pages once. Keyed by page number, not by
        # position: once the scan is a sample rather than a full sweep, the
        # nth page read is no longer page n, and a list indexed by page number
        # would quietly return some other page's text.
        page_texts: dict[int, str] = {}
        for i in _pages_to_scan(n):
            tp = doc[i].get_textpage()
            page_texts[i] = tp.get_text_range().strip()

        head_idx  = set(range(min(3, n)))
        tail_idx  = set(range(max(0, n - 2), n))
        fixed_idx = head_idx | tail_idx

        # From the remaining middle pages, pick up to 2 by character count
        middle = [(i, t) for i, t in page_texts.items() if i not in fixed_idx]
        middle.sort(key=lambda x: len(x[1]), reverse=True)
        mid_idx = {i for i, _ in middle[:2]}

        key_pages = sorted(fixed_idx | mid_idx)

        parts: list[str] = []
        for i in key_pages:
            text = page_texts[i]
            if text:
                parts.append(f"[Page {i + 1}]\n{text}")

    combined = "\n\n".join(parts)
    return combined[:max_chars]


def _find_doi(text: str) -> str | None:
    m = _DOI_RE.search(text)
    if m:
        return m.group(1).rstrip(".,;>\"')")
    return None


def _find_arxiv_url(text: str) -> str | None:
    for pattern in (_ARXIV_RE, _ARXIV_URL_RE):
        m = pattern.search(text)
        if m:
            arxiv_id = m.group(1)
            return f"https://arxiv.org/abs/{arxiv_id}"
    return None


def _call_llm_json(prompt: str) -> dict[str, Any]:
    """Call the active LLM via crewai.LLM and return parsed JSON."""
    from academic_agent.llm_config import create_llm

    llm = create_llm(json_mode=True, temperature=0.0)
    raw = llm.call([{"role": "user", "content": prompt}])
    content = (raw or "{}").strip()
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM returned non-JSON content: {exc}\nContent: {content[:200]}"
        ) from exc


def _detect_paper_language(text: str) -> str:
    """Return a BCP-47-style language tag for the dominant script in the first 2000 chars."""
    sample = text[:2000]
    n = max(len(sample), 1)
    zh = sum(1 for c in sample if "一" <= c <= "鿿")
    ja = sum(1 for c in sample if "぀" <= c <= "ヿ")
    ko = sum(1 for c in sample if "가" <= c <= "힣")
    ar = sum(1 for c in sample if "؀" <= c <= "ۿ")
    ru = sum(1 for c in sample if "Ѐ" <= c <= "ӿ")
    if zh / n > 0.12:
        return "zh"
    if ja / n > 0.08:
        return "ja"
    if ko / n > 0.08:
        return "ko"
    if ar / n > 0.08:
        return "ar"
    if ru / n > 0.08:
        return "ru"
    return "en"


_LANG_INSTRUCTIONS: dict[str, str] = {
    "zh": (
        "IMPORTANT — This paper is written in Chinese (中文). "
        "Write ALL fields — title, core_contribution, application_domain, key_metrics, "
        "delta_from_prior, commercialization_topic, and search_keywords — in Chinese to match the paper."
    ),
    "ja": (
        "IMPORTANT — This paper is written in Japanese (日本語). "
        "Write ALL fields — title, core_contribution, application_domain, key_metrics, "
        "delta_from_prior, commercialization_topic, and search_keywords — in Japanese to match the paper."
    ),
    "ko": (
        "IMPORTANT — This paper is written in Korean (한국어). "
        "Write ALL fields — title, core_contribution, application_domain, key_metrics, "
        "delta_from_prior, commercialization_topic, and search_keywords — in Korean to match the paper."
    ),
    "ar": (
        "IMPORTANT — This paper is written in Arabic (العربية). "
        "Write ALL fields — title, core_contribution, application_domain, key_metrics, "
        "delta_from_prior, commercialization_topic, and search_keywords — in Arabic to match the paper."
    ),
    "ru": (
        "IMPORTANT — This paper is written in Russian (Русский). "
        "Write ALL fields — title, core_contribution, application_domain, key_metrics, "
        "delta_from_prior, commercialization_topic, and search_keywords — in Russian to match the paper."
    ),
    "en": "Output all fields in English.",
}


def extract_paper_contribution(pdf_path: str | Path) -> PaperContribution:
    """Extract structured contribution metadata from an academic PDF using LLM."""
    text = extract_pdf_text(pdf_path)
    doi_found   = _find_doi(text)
    arxiv_url   = _find_arxiv_url(text)

    paper_lang  = _detect_paper_language(text)
    lang_instr  = _LANG_INSTRUCTIONS[paper_lang]

    prompt = f"""You are analyzing an academic paper for its commercialization potential.
Task: extract the SPECIFIC technical innovation of THIS paper — not background, not prior work.

{lang_instr}

Paper text (key pages):
---
{text}
---

Return a JSON object with exactly these keys:
{{
  "title": "full paper title",
  "authors": "first author et al.",
  "core_contribution": "2-3 sentences describing what is specifically new in this paper",
  "application_domain": "target industry or application",
  "key_metrics": ["specific metric 1 with value", "comparison vs prior work 2"],
  "delta_from_prior": "1-2 sentences: what makes this different from existing solutions",
  "commercialization_topic": "focused topic for commercialization search, e.g. 'sulfide solid electrolyte with 25 mS/cm ionic conductivity for lithium metal EV batteries'",
  "search_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "abstract_excerpt": "first 250 characters of the abstract"
}}

Rules:
- core_contribution must describe THIS paper's novel contribution only
- commercialization_topic must be specific enough to distinguish from related work
- search_keywords should target patents and market applications, not general academic terms; use the same language as the paper
- Return valid JSON only — no markdown, no prose outside the JSON object"""

    data = _call_llm_json(prompt)

    # Priority: LLM-found DOI > regex DOI > arXiv URL > placeholder DOI
    if doi_found and not data.get("doi"):
        data["doi"] = doi_found
    if arxiv_url and not data.get("doi") and not data.get("url"):
        data["url"] = arxiv_url

    # Fallback placeholder DOI so EvidenceSource passes model validation
    if not data.get("doi") and not data.get("url"):
        data["doi"] = _placeholder_doi(str(data.get("title", "paper")))

    valid_fields = PaperContribution.model_fields.keys()
    return PaperContribution(**{k: v for k, v in data.items() if k in valid_fields})


def paper_to_evidence_source(
    pc: PaperContribution,
    url_checker: "UrlChecker | None" = None,  # noqa: F821
) -> "EvidenceSource":  # noqa: F821
    """Convert a PaperContribution into an EvidenceSource for pipeline injection as A1.

    The DOI and URL carried by `pc` were read out of the PDF's text by an LLM,
    not resolved through a search index the way every other source in the
    pipeline is (source_pipeline._web_source runs the same check before
    admitting anything). A misread digit or an outright hallucinated
    identifier is well within what PDF text extraction produces, so the
    locators are verified here before this source is presented as a citable
    reference — an unresolvable DOI cited at "high" credibility is worse than
    citing none at all, since a reader who follows it finds nothing while the
    scorer counts it as verified evidence either way.
    """
    from academic_agent.evidence import EvidenceSource, check_public_url

    if url_checker is None:
        url_checker = check_public_url

    # Prefer real DOI URL; placeholder DOIs get stored in the doi field only.
    # Always populate src_doi when available so dedup and citation-tracking work.
    _real_doi = pc.doi if (pc.doi and not pc.doi.startswith(_PLACEHOLDER_DOI_PREFIX)) else None
    if not _real_doi and pc.url:
        # Extract DOI from a doi.org URL the LLM returned in the url field.
        _m = re.match(r"https?://doi\.org/(10\.\d{4,9}/[^\s?#]+)", pc.url.strip())
        if _m:
            _real_doi = _m.group(1)

    if _real_doi:
        src_doi: str | None = _real_doi
        src_url: str | None = pc.url or f"https://doi.org/{_real_doi}"
    elif pc.url:
        src_doi = None
        src_url = pc.url
    else:
        src_doi = pc.doi  # placeholder, passes format check
        src_url = None

    if src_url is not None and not url_checker(str(src_url))[0]:
        # A doi.org link that does not resolve condemns the DOI itself, not
        # just the link. Any other URL failing says nothing about a DOI that
        # was extracted separately, so that one is re-checked below instead.
        if src_doi and str(src_url).startswith("https://doi.org/"):
            src_doi = None
        src_url = None

    if src_url is None and _real_doi and src_doi:
        _resolver = f"https://doi.org/{src_doi}"
        src_url = _resolver if url_checker(_resolver)[0] else None
        if src_url is None:
            src_doi = None

    # Nothing survived verification, but the upload itself is still real and
    # still has to reach the crew as A1 — fall back to the same synthetic id
    # used for a paper that never carried an identifier at all.
    if src_url is None and src_doi is None:
        src_doi = _placeholder_doi(pc.title or "Uploaded Paper")

    # An uploaded paper is a primary source whether or not its identifiers
    # check out, but "high" asserts a reader can go and verify it. With no
    # locator that resolves, that is not a claim this pipeline can make.
    verifiable = src_url is not None or not src_doi.startswith(_PLACEHOLDER_DOI_PREFIX)

    summary = f"{pc.core_contribution.rstrip('.')}. {pc.delta_from_prior}"

    return EvidenceSource(
        source_id="A1",
        title=pc.title or "Uploaded Paper",
        url=src_url,  # type: ignore[arg-type]
        doi=src_doi,
        publisher=pc.authors or "Uploaded",
        published_date=None,
        accessed_date=date.today(),
        source_type="academic_paper",
        credibility_tier="high" if verifiable else "medium",
        credibility_reason=(
            "Primary source uploaded directly by the researcher."
            if verifiable else
            "Primary source uploaded by the researcher; no independently "
            "resolvable DOI or URL was found in the paper."
        ),
        evidence_summary=summary[:500],
        citation_count=None,
    )
