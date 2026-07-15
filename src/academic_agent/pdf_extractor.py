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


def extract_pdf_text(pdf_path: str | Path, max_chars: int = 7000) -> str:
    """Extract text from the highest-signal pages of a PDF (first 3 + last 2)."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise RuntimeError(
            "pypdfium2 is required. Install with: pip install pypdfium2"
        )

    doc = pdfium.PdfDocument(str(pdf_path))
    n = len(doc)
    key_pages = list(dict.fromkeys(
        list(range(min(3, n))) + list(range(max(0, n - 2), n))
    ))

    parts: list[str] = []
    for i in key_pages:
        page = doc[i]
        tp = page.get_textpage()
        text = tp.get_text_range().strip()
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
    return json.loads(content)


def extract_paper_contribution(pdf_path: str | Path) -> PaperContribution:
    """Extract structured contribution metadata from an academic PDF using LLM."""
    text = extract_pdf_text(pdf_path)
    doi_found   = _find_doi(text)
    arxiv_url   = _find_arxiv_url(text)

    prompt = f"""You are analyzing an academic paper for its commercialization potential.
Task: extract the SPECIFIC technical innovation of THIS paper — not background, not prior work.

Paper text (key pages):
---
{text}
---

Return a JSON object with exactly these keys:
{{
  "title": "full paper title",
  "authors": "first author et al.",
  "core_contribution": "2-3 sentences describing what is specifically new in this paper",
  "application_domain": "target industry or application (e.g. 'energy storage', 'cancer diagnostics', 'autonomous vehicles')",
  "key_metrics": ["specific metric 1 with value", "comparison vs prior work 2"],
  "delta_from_prior": "1-2 sentences: what makes this different from existing solutions",
  "commercialization_topic": "focused topic for commercialization search, e.g. 'sulfide solid electrolyte with 25 mS/cm ionic conductivity for lithium metal EV batteries'",
  "search_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "abstract_excerpt": "first 250 characters of the abstract"
}}

Rules:
- core_contribution must describe THIS paper's novel contribution only
- commercialization_topic must be specific enough to distinguish from related work
- search_keywords should target patents and market applications, not general academic terms
- Return valid JSON only — no markdown, no prose outside the JSON object"""

    data = _call_llm_json(prompt)

    # Priority: LLM-found DOI > regex DOI > arXiv URL > placeholder DOI
    if doi_found and not data.get("doi"):
        data["doi"] = doi_found
    if arxiv_url and not data.get("doi") and not data.get("url"):
        data["url"] = arxiv_url

    # Fallback placeholder DOI so EvidenceSource passes model validation
    if not data.get("doi") and not data.get("url"):
        title_hash = hashlib.md5(str(data.get("title", "paper")).encode()).hexdigest()[:10]
        data["doi"] = f"10.0000/uploaded-{title_hash}"

    valid_fields = PaperContribution.model_fields.keys()
    return PaperContribution(**{k: v for k, v in data.items() if k in valid_fields})


def paper_to_evidence_source(pc: PaperContribution) -> "EvidenceSource":  # noqa: F821
    """Convert a PaperContribution into an EvidenceSource for pipeline injection as A1."""
    from academic_agent.evidence import EvidenceSource

    # Prefer real DOI URL; placeholder DOIs get stored in the doi field only
    if pc.url:
        src_url: str | None = pc.url
        src_doi: str | None = None
    elif pc.doi and not pc.doi.startswith("10.0000/uploaded-"):
        src_url = f"https://doi.org/{pc.doi}"
        src_doi = None
    else:
        src_url = None
        src_doi = pc.doi  # placeholder, passes format check

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
        credibility_tier="high",
        credibility_reason="Primary source uploaded directly by the researcher.",
        evidence_summary=summary[:500],
        citation_count=None,
    )
