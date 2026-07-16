"""Structured evidence contracts and validation for research task outputs."""

import ipaddress
import re
import socket
from datetime import date
from functools import lru_cache
from typing import Any, Callable, Literal, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from crewai import TaskOutput
from pydantic import (
    BaseModel,
    Field,
    HttpUrl,
    ValidationError,
    field_serializer,
    field_validator,
    model_validator,
)

# Scoring weight profiles — weights must sum to 100.
# Keys: market, trl, patent, mrl, evidence
_WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "industrial": {
        "market": 35.0, "trl": 20.0, "patent": 20.0, "mrl": 15.0, "evidence": 10.0,
    },
    "biomedical": {
        "market": 25.0, "trl": 20.0, "patent": 15.0, "mrl": 30.0, "evidence": 10.0,
    },
    "material_science": {
        "market": 20.0, "trl": 30.0, "patent": 20.0, "mrl": 20.0, "evidence": 10.0,
    },
    "clean_tech": {
        # Renewable energy / grid storage / hydrogen — policy tailwinds make market
        # signals strong; TRL matters as energy systems have long deployment cycles.
        "market": 25.0, "trl": 30.0, "patent": 15.0, "mrl": 20.0, "evidence": 10.0,
    },
    "software_ai": {
        # Software/AI — deploys fast so market traction dominates; MRL near-trivial
        # (distribution cost zero); patent moats weak vs. trade-secret advantages.
        "market": 40.0, "trl": 30.0, "patent": 10.0, "mrl": 10.0, "evidence": 10.0,
    },
}
assert all(
    abs(sum(w.values()) - 100) < 0.01 for w in _WEIGHT_PROFILES.values()
), "All weight profiles must sum to 100"


SourceType = Literal[
    "academic_paper",
    "patent",
    "company_disclosure",
    "government",
    "standards_body",
    "research_institute",
    "market_report",
    "reputable_news",
    "other",
]
ClaimType = Literal["observed_fact", "estimate", "analyst_inference"]
Confidence = Literal["high", "medium", "low"]
CredibilityTier = Literal["high", "medium", "low"]
UrlChecker = Callable[[str], tuple[bool, str]]

_DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
_SOURCE_ID_PATTERN = re.compile(r"^[APM]\d+$")
_BRACKET_PATTERN = re.compile(r"\[([^\[\]]+)\]")
_SOURCE_TOKEN_PATTERN = re.compile(r"^[APM]\d+$")
_SOURCE_RANGE_PATTERN = re.compile(
    r"^([APM])(\d+)\s*[-–—]\s*(?:([APM])\s*)?(\d+)$"
)
_REFERENCE_ENTRY_PATTERN = re.compile(r"(?m)^\s*\[([APM]\d+)\]\s+")
_TABLE_SOURCE_CELL_PATTERN = re.compile(r"\|\s*[APM]\d+(?:\s*,\s*[APM]\d+)*\s*\|")
_NUMERIC_CLAIM_PATTERN = re.compile(
    r"(?<!\[)\b"
    r"(?:\d{1,3}(?:,\d{3})+"                          # thousands-separated: 1,000  10,000
    r"|(?!(?:1[89]\d{2}|20\d{2}|21\d{2})\b)\d+(?:\.\d+)?)"  # integers/decimals, excluding years
    r"(?:\s?(?:%|x|×|USD|AUD|EUR|million|billion|trillion|M|B))?\b",
    re.IGNORECASE,
)
_PLACEHOLDER_HOSTS = {
    "example.com",
    "www.example.com",
    "example.org",
    "www.example.org",
    "example.net",
    "www.example.net",
    "localhost",
}
_BLOCKED_HOST_SUFFIXES = (".invalid", ".local", ".localhost", ".test")
_REQUIRED_REPORT_HEADINGS = (
    "# Academic Commercialization Assessment:",
    "## Executive Summary",
    "## 1. Technology Overview & Maturity",
    "## 2. Patent Landscape & White Spaces",
    "## 3. Target Industries & Use Cases",
    "## 4. Competitive Landscape",
    "## 5. Commercialization Opportunities & Recommendations",
    "## Evidence Limitations",
    "## References",
)


# Localized patent disclaimer text and the phrases used to verify its presence.
# All variants keep "freedom-to-operate" in Latin so _is_substantive_claim_line()
# can detect and skip it without language-specific logic.
_PATENT_DISCLAIMERS: dict[str, dict] = {
    "English":             {"text": "Patent analysis is preliminary research, not legal advice or a freedom-to-operate opinion.",                                                                                          "check": ("not legal advice",                  "freedom-to-operate")},
    "Simplified Chinese":  {"text": "专利分析为初步研究，不构成法律意见或自由实施（Freedom-to-Operate）意见。",                                                                                                            "check": ("不构成法律意见",                     "freedom-to-operate")},
    "Traditional Chinese": {"text": "專利分析為初步研究，不構成法律意見或自由實施（Freedom-to-Operate）意見。",                                                                                                            "check": ("不構成法律意見",                     "freedom-to-operate")},
    "Japanese":            {"text": "特許分析は予備的調査であり、法的意見ではありません。自由実施権（Freedom-to-Operate）の意見でもありません。",                                                                      "check": ("法的意見ではありません",              "freedom-to-operate")},
    "Korean":              {"text": "특허 분석은 예비 조사이며, 법적 의견이 아닙니다. 자유 실시(Freedom-to-Operate) 의견도 아닙니다.",                                                                                      "check": ("법적 의견이 아닙니다",               "freedom-to-operate")},
    "German":              {"text": "Die Patentanalyse ist eine vorläufige Recherche und stellt keine Rechtsberatung oder Freedom-to-Operate-Stellungnahme dar.",                                                         "check": ("keine rechtsberatung",               "freedom-to-operate")},
    "French":              {"text": "L'analyse de brevets est une recherche préliminaire et ne constitue pas un avis juridique ou une opinion Freedom-to-Operate.",                                                       "check": ("pas un avis juridique",              "freedom-to-operate")},
    "Spanish":             {"text": "El análisis de patentes es una investigación preliminar y no constituye asesoramiento legal ni una opinión Freedom-to-Operate.",                                                     "check": ("no constituye asesoramiento legal",  "freedom-to-operate")},
    "Italian":             {"text": "L'analisi dei brevetti è una ricerca preliminare e non costituisce una consulenza legale o un parere Freedom-to-Operate.",                                                           "check": ("non costituisce una consulenza",     "freedom-to-operate")},
    "Portuguese":          {"text": "A análise de patentes é uma pesquisa preliminar e não constitui aconselhamento jurídico ou parecer Freedom-to-Operate.",                                                            "check": ("não constitui aconselhamento",       "freedom-to-operate")},
    "Russian":             {"text": "Анализ патентов является предварительным исследованием и не является юридической консультацией или заключением Freedom-to-Operate.",                                               "check": ("не является юридической",           "freedom-to-operate")},
    "Arabic":              {"text": "تحليل براءات الاختراع بحث أولي وليس رأياً قانونياً أو رأياً بشأن حرية العمل (Freedom-to-Operate).",                                                                             "check": ("وليس رأياً قانونياً",               "freedom-to-operate")},
}


def _patent_disclaimer(output_language: str) -> tuple[str, tuple[str, str]]:
    """Return (disclaimer_text, (check_phrase1, check_phrase2)) for the given language."""
    entry = _PATENT_DISCLAIMERS.get(output_language, _PATENT_DISCLAIMERS["English"])
    return str(entry["text"]), tuple(entry["check"])  # type: ignore[return-value]


def normalize_doi(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    normalized = re.sub(
        r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    return normalized.rstrip(".,;")


def canonicalize_url(value: str | HttpUrl) -> str:
    parsed = urlsplit(str(value).strip())
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if port and not (
        (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    ):
        host = f"{host}:{port}"
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((scheme, host, path, parsed.query, ""))


class EvidenceSource(BaseModel):
    """A source that can be traced back to an external record."""

    source_id: str = Field(
        min_length=2,
        description="Task-unique source identifier such as A1, P1, or M1.",
    )
    title: str = Field(min_length=5)
    url: HttpUrl | None = None
    doi: str | None = None
    publisher: str = Field(min_length=2)
    published_date: date | None = None
    accessed_date: date
    source_type: SourceType
    credibility_tier: CredibilityTier = "medium"
    credibility_reason: str = Field(
        default="Source credibility has not been independently graded.",
        min_length=10,
    )
    evidence_summary: str = Field(
        min_length=1,
        description="A concise paraphrase of what this source actually supports.",
    )

    @field_validator("evidence_summary")
    @classmethod
    def _evidence_summary_length(cls, v: str) -> str:
        # CJK scripts carry ~3× information density of Latin; apply a lower floor.
        cjk = sum(
            1 for c in v
            if "一" <= c <= "鿿"   # CJK Unified Ideographs
            or "぀" <= c <= "ヿ"   # Hiragana / Katakana
            or "가" <= c <= "힣"   # Hangul syllables
        )
        min_len = 20 if cjk / max(len(v), 1) > 0.25 else 60
        if len(v) < min_len:
            raise ValueError(
                f"evidence_summary must be at least {min_len} characters "
                f"(got {len(v)})"
            )
        return v
    citation_count: int | None = Field(
        default=None,
        description="Number of times this source has been cited (OpenAlex cited_by_count or S2 citationCount).",
    )

    @field_serializer("url")
    def serialize_url(self, value: HttpUrl | None) -> str | None:
        return str(value) if value is not None else None

    @field_serializer("published_date", "accessed_date")
    def serialize_date(self, value: date | None) -> str | None:
        return value.isoformat() if value is not None else None

    @field_validator("doi", mode="before")
    @classmethod
    def validate_doi(cls, value: str | None) -> str | None:
        normalized = normalize_doi(value)
        if normalized is not None and not _DOI_PATTERN.fullmatch(normalized):
            raise ValueError("DOI must match the canonical form 10.xxxx/suffix.")
        return normalized

    @model_validator(mode="after")
    def validate_source(self) -> "EvidenceSource":
        today = date.today()
        if self.url is None and not self.doi:
            raise ValueError("Each source must include a real URL or DOI.")
        if self.accessed_date > today:
            raise ValueError("Accessed date cannot be in the future.")
        if self.published_date is not None and self.published_date > today:
            # Silently clear rather than crash — market snippets often contain
            # forecast years (e.g. "by 2030") that get parsed as publish dates.
            self.published_date = None
        return self


class EvidenceFinding(BaseModel):
    """A research conclusion explicitly connected to supporting sources."""

    finding_id: str = Field(min_length=2)
    category: str = Field(min_length=2)
    claim: str = Field(min_length=20)
    claim_type: ClaimType
    source_ids: list[str] = Field(min_length=1)
    confidence: Confidence
    commercial_implication: str = Field(min_length=10)
    limitations: str | None = None


class EvidenceReport(BaseModel):
    """Structured output shared by the academic, patent, and market tasks."""

    topic: str = Field(min_length=3)
    scope_summary: str = Field(min_length=20)
    search_queries: list[str] = Field(min_length=1)
    findings: list[EvidenceFinding] = Field(min_length=3)
    sources: list[EvidenceSource] = Field(min_length=2)
    limitations: list[str] = Field(min_length=1)


class EvidenceAnalysis(BaseModel):
    """LLM-authored analysis that cannot create or alter source metadata."""

    scope_summary: str = Field(min_length=20)
    findings: list[EvidenceFinding] = Field(min_length=3)
    limitations: list[str] = Field(min_length=1)


class CommercializationScore(BaseModel):
    """Quantitative readiness scorecard produced by the scoring agent."""

    # Raw scores written by LLM on a ×10 integer scale.
    # Guardrail divides by 10 before computing the formula and before saving,
    # so the output JSON always contains the normalized float (e.g. 7.3 not 73).
    trl_score: int = Field(ge=10, le=90)   # 10–90 integer → 1.0–9.0 after ÷10
    trl_rationale: str = Field(min_length=20)
    trl_source_ids: list[str] = Field(min_length=1, description="Source IDs (A/M prefix) that drove the TRL assessment")
    mrl_score: int = Field(ge=10, le=100)  # 10–100 integer → 1.0–10.0 after ÷10
    mrl_rationale: str = Field(min_length=20)
    mrl_source_ids: list[str] = Field(min_length=1, description="Source IDs (A/M prefix) that drove the MRL assessment")
    patent_strength: int = Field(ge=10, le=50)   # 10–50 integer → 1.0–5.0 after ÷10
    patent_rationale: str = Field(min_length=20)
    patent_source_ids: list[str] = Field(min_length=1, description="Source IDs (P prefix) that drove the patent strength score")
    market_accessibility: int = Field(ge=10, le=50)  # 10–50 integer → 1.0–5.0 after ÷10
    market_rationale: str = Field(min_length=20)
    market_source_ids: list[str] = Field(min_length=1, description="Source IDs (M prefix) that drove the market accessibility score")
    evidence_confidence: int = Field(ge=10, le=50)   # 10–50 integer → 1.0–5.0 after ÷10
    evidence_rationale: str = Field(min_length=20)
    evidence_source_ids: list[str] = Field(min_length=1, description="All source IDs informing the overall evidence confidence score")
    overall_score: float = Field(ge=0.0, le=100.0)
    scoring_rationale: str = Field(min_length=20)
    key_risks: list[str] = Field(min_length=1, max_length=5)
    key_opportunities: list[str] = Field(min_length=1, max_length=5)


_BARE_BENCHMARK_RE = re.compile(
    r"\b(benchmark)\s+(?=\(?\s*TRL\b)",
    re.IGNORECASE,
)


def _tag_bare_benchmark_refs(rationale: str) -> str:
    """Replace bare 'benchmark (TRL …)' with 'calibration anchor (TRL …)'.

    The scorer's backstory embeds canonical calibration anchors (LFP, solid-state
    batteries, etc.).  When the LLM writes "consistent with the … benchmark (TRL X)"
    without labelling its source, readers cannot tell whether the number comes from
    an evidence source or from the internal rubric.  This function normalises the
    phrasing to 'calibration anchor' so the distinction is unambiguous.
    """
    return _BARE_BENCHMARK_RE.sub("calibration anchor ", rationale)


def _extract_market_size_billions(market_task: Any) -> list[float]:
    """Extract market-size numerical values (normalised to billions USD) from a completed market task."""
    output = getattr(market_task, "output", None)
    if output is None:
        return []
    report = getattr(output, "pydantic", None)
    if not isinstance(report, EvidenceReport):
        try:
            report = EvidenceReport.model_validate_json(getattr(output, "raw", ""))
        except Exception:
            return []

    bn_pat = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(?:bn|billion)", re.IGNORECASE)
    mn_pat = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(?:mn|million)", re.IGNORECASE)
    values: list[float] = []

    def _parse(text: str) -> None:
        for m in bn_pat.findall(text):
            try:
                values.append(float(m.replace(",", "")))
            except ValueError:
                pass
        for m in mn_pat.findall(text):
            try:
                values.append(float(m.replace(",", "")) / 1000)
            except ValueError:
                pass

    for finding in report.findings:
        _parse(finding.claim)
        if finding.limitations:
            _parse(finding.limitations)
    for source in report.sources:
        _parse(source.evidence_summary)

    return [v for v in values if v > 0]


def _trl_label(trl: float) -> str:
    """Map a TRL float (1.0–9.0) to a single-level standard label."""
    _LABELS = {
        1: "TRL 1 (basic principles observed)",
        2: "TRL 2 (technology concept formulated)",
        3: "TRL 3 (experimental proof of concept)",
        4: "TRL 4 (component validated in laboratory)",
        5: "TRL 5 (component validated in relevant environment)",
        6: "TRL 6 (system prototype demonstrated in relevant environment)",
        7: "TRL 7 (system prototype in operational environment)",
        8: "TRL 8 (system complete and qualified)",
        9: "TRL 9 (actual system proven in operational environment)",
    }
    stage = min(9, max(1, round(trl)))
    return _LABELS[stage]


def make_scoring_guardrail(
    weight_profile: str = "industrial",
    *,
    known_source_ids: frozenset[str] | None = None,
    market_task: Any = None,
) -> Callable[[TaskOutput], tuple[bool, Any]]:
    """Validate scoring task output and deterministically recompute overall_score.

    Uses the weight profile selected during source collection so that biomedical
    and material-science topics are scored with domain-appropriate weights.
    When known_source_ids is provided, cited IDs are checked to exist in the
    source collection — preventing hallucinated source references.
    """
    weights = _WEIGHT_PROFILES.get(weight_profile, _WEIGHT_PROFILES["industrial"])

    def validate_score(output: TaskOutput) -> tuple[bool, Any]:
        try:
            score = CommercializationScore.model_validate_json(output.raw)
        except (ValidationError, ValueError) as exc:
            return (
                False,
                "Return exactly one valid JSON object matching the scoring schema "
                f"with no Markdown fences or prose. Validation error: {exc}",
            )

        id_errors: list[str] = []
        for field, ids in (
            ("trl_source_ids", score.trl_source_ids),
            ("mrl_source_ids", score.mrl_source_ids),
            ("patent_source_ids", score.patent_source_ids),
            ("market_source_ids", score.market_source_ids),
            ("evidence_source_ids", score.evidence_source_ids),
        ):
            bad_format = [sid for sid in ids if not _SOURCE_ID_PATTERN.fullmatch(sid)]
            if bad_format:
                id_errors.append(
                    f"{field} contains invalid source IDs: {bad_format}. "
                    "Use IDs exactly as they appear in the context (e.g. A1, P2, M3)."
                )
            elif known_source_ids is not None:
                phantom = [sid for sid in ids if sid not in known_source_ids]
                if phantom:
                    id_errors.append(
                        f"{field} references source IDs not present in the context: {phantom}. "
                        f"Valid IDs are: {sorted(known_source_ids)}."
                    )
        if id_errors:
            return False, " ".join(id_errors)

        # Normalize raw ×10 integer scores to their actual scales.
        trl = score.trl_score / 10        # 10–90  → 1.0–9.0
        mrl = score.mrl_score / 10        # 10–100 → 1.0–10.0
        pat = score.patent_strength / 10  # 10–50  → 1.0–5.0
        mkt = score.market_accessibility / 10
        evi = score.evidence_confidence / 10

        # Market size variance check: if estimates spread >5× cap market score at 3.5.
        market_uncertainty: str | None = None
        if market_task is not None:
            sizes = _extract_market_size_billions(market_task)
            if len(sizes) >= 2:
                min_s, max_s = min(sizes), max(sizes)
                if min_s > 0 and max_s / min_s > 5:
                    ratio = max_s / min_s
                    market_uncertainty = (
                        f"high ({ratio:.0f}× spread: {min_s:.2g}–{max_s:.2g} bn USD)"
                    )
                    mkt = min(mkt, 3.5)

        # Deterministically recompute overall_score using the active weight profile.
        mkt_c = (mkt / 5) * weights["market"]
        trl_c = (trl / 9) * weights["trl"]
        mrl_c = (mrl / 10) * weights["mrl"]
        pat_c = (pat / 5) * weights["patent"]
        evi_c = (evi / 5) * weights["evidence"]
        correct_overall = round(mkt_c + trl_c + mrl_c + pat_c + evi_c, 1)
        # Store the calculation as a dedicated field so scoring_rationale stays
        # as clean natural-language text and is not polluted with debug formulas.
        score_formula = (
            f"({mkt}/5)×{weights['market']}={mkt_c:.2f}"
            f" + ({trl}/9)×{weights['trl']}={trl_c:.2f}"
            f" + ({mrl}/10)×{weights['mrl']}={mrl_c:.2f}"
            f" + ({pat}/5)×{weights['patent']}={pat_c:.2f}"
            f" + ({evi}/5)×{weights['evidence']}={evi_c:.2f}"
            f" = {correct_overall}  [{weight_profile}]"
        )
        rationale = _tag_bare_benchmark_refs(score.scoring_rationale)
        auto_corrected = correct_overall != score.overall_score

        # Rebuild output with normalized float scores (not the raw ×10 integers).
        import json as _json
        out_dict = score.model_dump()
        out_dict.update({
            "trl_score": trl,
            "trl_label": _trl_label(trl),
            "mrl_score": mrl,
            "patent_strength": pat,
            "market_accessibility": mkt,
            "evidence_confidence": evi,
            "overall_score": correct_overall,
            "scoring_rationale": rationale,
            "score_formula": score_formula,
            "auto_corrected": auto_corrected,
            "market_uncertainty": market_uncertainty,
        })
        output.pydantic = None
        output.raw = _json.dumps(out_dict)
        return True, output

    return validate_score


def _host_is_public(host: str) -> tuple[bool, str]:
    normalized = host.rstrip(".").lower()
    if (
        normalized in _PLACEHOLDER_HOSTS
        or normalized.endswith(_BLOCKED_HOST_SUFFIXES)
    ):
        return False, f"blocked or placeholder host: {host}"

    try:
        addresses = {
            item[4][0] for item in socket.getaddrinfo(normalized, None, proto=socket.IPPROTO_TCP)
        }
    except socket.gaierror as exc:
        return False, f"DNS resolution failed: {exc}"

    if not addresses:
        return False, "host resolved to no addresses"

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            return False, f"host resolves to non-public address {address}"
    return True, ""


def _validate_public_url(value: str) -> tuple[bool, str]:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"}:
        return False, "only HTTP and HTTPS URLs are allowed"
    if not parsed.hostname:
        return False, "URL has no hostname"
    if parsed.username or parsed.password:
        return False, "URLs containing credentials are not allowed"
    return _host_is_public(parsed.hostname)


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@lru_cache(maxsize=512)
def check_public_url(value: str) -> tuple[bool, str]:
    """Check a URL without following redirects into private network locations."""

    current = value
    opener = build_opener(_NoRedirectHandler)
    headers = {"User-Agent": "AcademicAgentEvidenceVerifier/1.0"}

    for _ in range(5):
        safe, reason = _validate_public_url(current)
        if not safe:
            return False, reason

        # Reject URLs with spaces or non-ASCII characters before attempting HTTP.
        try:
            current.encode("ascii")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return False, "URL contains non-ASCII characters"
        if " " in current:
            return False, "URL contains spaces"

        request = Request(current, method="HEAD", headers=headers)
        try:
            with opener.open(request, timeout=8) as response:
                status = response.status
                if 200 <= status < 400:
                    return True, ""
                return False, f"HTTP status {status}"
        except HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308}:
                location = exc.headers.get("Location")
                if not location:
                    return False, f"redirect status {exc.code} without Location"
                current = urljoin(current, location)
                continue
            if exc.code in {401, 403}:
                return True, ""
            if exc.code == 405:
                try:
                    get_request = Request(
                        current,
                        method="GET",
                        headers={**headers, "Range": "bytes=0-0"},
                    )
                    with opener.open(get_request, timeout=8) as response:
                        return (200 <= response.status < 400, "")
                except (HTTPError, URLError, TimeoutError, Exception) as get_exc:
                    return False, f"GET fallback failed: {get_exc}"
            return False, f"HTTP status {exc.code}"
        except (URLError, TimeoutError, OSError) as exc:
            return False, f"request failed: {exc}"
        except Exception as exc:
            return False, f"URL check error: {type(exc).__name__}: {exc}"

    return False, "too many redirects"


def validate_evidence_report(
    report: EvidenceReport,
    expected_prefix: str,
) -> list[str]:
    """Return structural evidence-integrity errors."""

    errors: list[str] = []
    source_ids = [source.source_id for source in report.sources]
    source_id_set = set(source_ids)

    if len(source_ids) != len(source_id_set):
        errors.append("Source IDs must be unique within the task output.")

    seen_urls: dict[str, str] = {}
    seen_dois: dict[str, str] = {}
    for source in report.sources:
        if not _SOURCE_ID_PATTERN.fullmatch(source.source_id):
            errors.append(
                f"Source ID {source.source_id!r} must use the format A1, P1, or M1."
            )
        elif not source.source_id.startswith(expected_prefix):
            errors.append(
                f"Source ID {source.source_id!r} must start with {expected_prefix!r}."
            )

        if source.url is not None:
            canonical_url = canonicalize_url(str(source.url))
            previous = seen_urls.get(canonical_url)
            if previous:
                errors.append(
                    f"Sources {previous} and {source.source_id} use the same URL."
                )
            seen_urls[canonical_url] = source.source_id

        if source.doi:
            normalized_doi = source.doi.lower()
            previous = seen_dois.get(normalized_doi)
            if previous:
                errors.append(
                    f"Sources {previous} and {source.source_id} use the same DOI."
                )
            seen_dois[normalized_doi] = source.source_id

    referenced_ids: set[str] = set()
    finding_ids: set[str] = set()
    for finding in report.findings:
        if finding.finding_id in finding_ids:
            errors.append(f"Finding ID {finding.finding_id!r} is duplicated.")
        finding_ids.add(finding.finding_id)

        if len(finding.source_ids) != len(set(finding.source_ids)):
            errors.append(
                f"Finding {finding.finding_id} contains duplicate source IDs."
            )

        unknown_ids = set(finding.source_ids) - source_id_set
        if unknown_ids:
            errors.append(
                f"Finding {finding.finding_id} references unknown sources: "
                f"{', '.join(sorted(unknown_ids))}."
            )
        referenced_ids.update(finding.source_ids)

        if finding.claim_type != "observed_fact" and not finding.limitations:
            errors.append(
                f"Finding {finding.finding_id} is an estimate or inference and must "
                "state its limitations."
            )

    # NOTE: we intentionally do NOT fail on unreferenced sources.
    # Agents may collect candidate sources and select the most relevant ones;
    # forcing every collected source to appear in a finding produces fabricated
    # citations.  The important integrity check is the reverse: every source ID
    # that *is* referenced must exist (enforced above at the unknown_ids check).

    return errors


def validate_source_reachability(
    report: EvidenceReport,
    url_checker: UrlChecker = check_public_url,
) -> list[str]:
    """Verify that each source has at least one reachable public locator."""

    errors: list[str] = []
    for source in report.sources:
        locators: list[str] = []
        if source.url is not None:
            locators.append(str(source.url))
        if source.doi:
            locators.append(f"https://doi.org/{source.doi}")

        failures: list[str] = []
        for locator in locators:
            reachable, reason = url_checker(locator)
            if reachable:
                break
            failures.append(f"{locator}: {reason}")
        else:
            errors.append(
                f"Source {source.source_id} has no reachable public locator "
                f"({'; '.join(failures)})."
            )
    return errors


def _evidence_guardrail(
    output: TaskOutput,
    expected_prefix: str,
) -> tuple[bool, Any]:
    report = output.pydantic
    if not isinstance(report, EvidenceReport):
        try:
            report = EvidenceReport.model_validate_json(output.raw)
        except (ValidationError, ValueError) as exc:
            return (
                False,
                "Return exactly one valid JSON object matching the EvidenceReport "
                f"schema, without Markdown fences or prose. Validation error: {exc}",
            )

    output.pydantic = report
    output.raw = report.model_dump_json()

    errors = validate_evidence_report(report, expected_prefix)
    if not errors:
        errors.extend(validate_source_reachability(report))
    if errors:
        return False, "Evidence validation failed:\n- " + "\n- ".join(errors)

    return True, output


def validate_academic_evidence(output: TaskOutput) -> tuple[bool, Any]:
    return _evidence_guardrail(output, "A")


def validate_patent_evidence(output: TaskOutput) -> tuple[bool, Any]:
    return _evidence_guardrail(output, "P")


def validate_market_evidence(output: TaskOutput) -> tuple[bool, Any]:
    return _evidence_guardrail(output, "M")


def make_evidence_guardrail(
    expected_prefix: str,
    topic: str,
    sources: Sequence[EvidenceSource],
    search_queries: Sequence[str],
) -> Callable[[TaskOutput], tuple[bool, Any]]:
    """Bind immutable, prevalidated sources to an LLM-authored analysis."""

    validated_sources = list(sources)
    validated_queries = list(search_queries)

    def validate_analysis(output: TaskOutput) -> tuple[bool, Any]:
        try:
            analysis = EvidenceAnalysis.model_validate_json(output.raw)
        except (ValidationError, ValueError) as exc:
            return (
                False,
                "Return exactly one valid JSON object matching the analysis schema "
                f"without a sources field. Validation error: {exc}",
            )

        report = EvidenceReport(
            topic=topic,
            scope_summary=analysis.scope_summary,
            search_queries=validated_queries,
            findings=analysis.findings,
            sources=validated_sources,
            limitations=analysis.limitations,
        )
        errors = validate_evidence_report(report, expected_prefix)
        if errors:
            return False, "Evidence validation failed:\n- " + "\n- ".join(errors)

        output.pydantic = report
        output.raw = report.model_dump_json()
        return True, output

    return validate_analysis


def collect_context_sources(context_tasks: Sequence[Any]) -> dict[str, EvidenceSource]:
    sources: dict[str, EvidenceSource] = {}
    for task in context_tasks:
        output = getattr(task, "output", None)
        report = getattr(output, "pydantic", None)
        if not isinstance(report, EvidenceReport):
            continue
        for source in report.sources:
            sources[source.source_id] = source
    return sources


def parse_citation_ids(text: str) -> tuple[list[str], list[str]]:
    """Parse individual, grouped, and same-prefix range citations."""

    source_ids: list[str] = []
    errors: list[str] = []
    for content in _BRACKET_PATTERN.findall(text):
        if not re.search(r"[APM]\d+", content):
            continue
        for part in re.split(r"\s*[,;]\s*", content.strip()):
            if _SOURCE_TOKEN_PATTERN.fullmatch(part):
                source_ids.append(part)
                continue

            range_match = _SOURCE_RANGE_PATTERN.fullmatch(part)
            if range_match:
                prefix, start_text, end_prefix, end_text = range_match.groups()
                start = int(start_text)
                end = int(end_text)
                if end_prefix and end_prefix != prefix:
                    errors.append(f"Cross-prefix citation range is invalid: [{part}].")
                elif end < start or end - start > 50:
                    errors.append(f"Citation range is invalid or too large: [{part}].")
                else:
                    source_ids.extend(
                        f"{prefix}{number}" for number in range(start, end + 1)
                    )
                continue

            errors.append(f"Malformed citation block: [{content}].")
            break

    return source_ids, errors


def _is_substantive_claim_line(
    lines: list[str],
    line_index: int,
    in_limitations: bool,
) -> bool:
    stripped = lines[line_index].strip()
    if in_limitations or not stripped or stripped.startswith("#"):
        return False
    if re.fullmatch(r"[-|:\s]+", stripped):
        return False
    if "not legal advice" in stripped.lower() or "freedom-to-operate" in stripped.lower():
        return False
    # Introductory lines ending with colon are list/section openers, not standalone claims
    if stripped.endswith(":"):
        return False
    if stripped.startswith("|") and line_index + 1 < len(lines):
        if re.fullmatch(r"[\s|:-]+", lines[line_index + 1].strip()):
            return False
        # Table data rows with a dedicated source-ID cell are implicitly cited
        if _TABLE_SOURCE_CELL_PATTERN.search(stripped):
            return False
    without_citations = _BRACKET_PATTERN.sub("", stripped)
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", without_citations)
    cjk_chars = len(re.findall(r"[一-鿿぀-ヿ가-힯]", without_citations))
    return len(words) >= 5 or cjk_chars >= 10


def _validate_high_risk_claims(
    body: str,
    allowed_sources: dict[str, EvidenceSource],
) -> list[str]:
    """Apply deterministic policies where semantic overstatement is high risk."""

    errors: list[str] = []
    fleet_terms = {"truck", "trucks", "bus", "buses", "fleet", "fleets"}

    for line_number, line in enumerate(body.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lowered = stripped.lower()
        line_ids, citation_errors = parse_citation_ids(stripped)
        if citation_errors:
            continue

        noncanonical_labels = [
            content
            for content in _BRACKET_PATTERN.findall(stripped)
            if "limitation" in content.lower()
            and not re.search(r"\b[APM]\d+\b", content)
        ]
        for label in noncanonical_labels:
            errors.append(f"Noncanonical citation label on report line {line_number}: [{label}].")
        if re.search(
            r"\b(?:freedom-to-operate opportunit|without infringing|non[- ]infringing|clear freedom to operate)",
            lowered,
        ):
            errors.append(
                f"Patent legal overclaim on report line {line_number}: "
                "a preliminary patent scan cannot establish freedom to operate."
            )

        mentioned_fleet_terms = {
            term for term in fleet_terms if re.search(rf"\b{term}\b", lowered)
        }
        if mentioned_fleet_terms and line_ids:
            cited_text_parts: list[str] = []
            for source_id in line_ids:
                source = allowed_sources.get(source_id)
                if source is None:
                    continue
                cited_text_parts.extend([source.title, source.evidence_summary])
            cited_text = " ".join(cited_text_parts).lower()
            if not any(
                re.search(rf"\b{term}\b", cited_text)
                for term in mentioned_fleet_terms
            ):
                errors.append(
                    f"Unsupported use-case claim on report line {line_number}: "
                    "the cited source summaries do not mention the claimed fleet, "
                    "truck, or bus application."
                )

    government_ids = sorted(
        source_id
        for source_id, source in allowed_sources.items()
        if source.source_type in {"government", "standards_body"}
    )
    if government_ids and re.search(
        r"\bno government(?:al)?\s+(?:or\s+independent(?:\s+third-party)?\s+)?(?:verification|evidence|sources?)\b",
        body,
        flags=re.IGNORECASE,
    ):
        errors.append(
            "Source contradiction: report broadly claims no government verification "
            "despite validated government or standards sources: "
            + ", ".join(government_ids)
            + "."
        )

    return errors
def validate_final_report(
    markdown: str,
    allowed_sources: dict[str, EvidenceSource],
    *,
    required_headings: tuple[str, ...] | None = None,
    output_language: str = "English",
) -> list[str]:
    """Validate citation integrity in the final Markdown report."""

    # _canonical_reference_section always writes "## References" in English,
    # so swap the localized References heading for the canonical English form.
    if required_headings:
        headings_to_check = required_headings[:-1] + ("## References",)
    else:
        headings_to_check = _REQUIRED_REPORT_HEADINGS
    errors: list[str] = []
    for heading in headings_to_check:
        if heading not in markdown:
            errors.append(f"Missing required heading: {heading}")

    reference_marker = "## References"
    if reference_marker not in markdown:
        return errors

    body, references = markdown.split(reference_marker, maxsplit=1)
    body_ids_list, citation_errors = parse_citation_ids(body)
    errors.extend(citation_errors)
    body_ids = set(body_ids_list)
    reference_ids_list = _REFERENCE_ENTRY_PATTERN.findall(references)
    reference_ids = set(reference_ids_list)
    allowed_ids = set(allowed_sources)

    all_reference_ids, reference_citation_errors = parse_citation_ids(references)
    errors.extend(reference_citation_errors)
    unexpected_reference_format = set(all_reference_ids) - reference_ids
    if unexpected_reference_format:
        errors.append(
            "Each References entry must start with one canonical [source_id]: "
            f"{', '.join(sorted(unexpected_reference_format))}."
        )

    if not body_ids:
        errors.append("The report body contains no source citations.")
    unknown_body_ids = body_ids - allowed_ids
    if unknown_body_ids:
        errors.append(
            "Report body cites unknown source IDs: "
            f"{', '.join(sorted(unknown_body_ids))}."
        )
    unknown_reference_ids = reference_ids - allowed_ids
    if unknown_reference_ids:
        errors.append(
            "References contain unknown source IDs: "
            f"{', '.join(sorted(unknown_reference_ids))}."
        )
    missing_references = body_ids - reference_ids
    if missing_references:
        errors.append(
            "Cited source IDs missing from References: "
            f"{', '.join(sorted(missing_references))}."
        )
    uncited_references = reference_ids - body_ids
    if uncited_references:
        errors.append(
            "References contain uncited source IDs: "
            f"{', '.join(sorted(uncited_references))}."
        )

    duplicates = sorted(
        source_id
        for source_id in reference_ids
        if reference_ids_list.count(source_id) != 1
    )
    if duplicates:
        errors.append(
            "Each reference ID must appear exactly once in References: "
            f"{', '.join(duplicates)}."
        )

    reference_lines = references.splitlines()
    for source_id in reference_ids & allowed_ids:
        source = allowed_sources[source_id]
        matching_lines = [
            line for line in reference_lines if f"[{source_id}]" in line
        ]
        if len(matching_lines) != 1:
            continue
        line = matching_lines[0]
        locators = []
        if source.url is not None:
            locators.append(str(source.url))
        if source.doi:
            locators.extend([source.doi, f"https://doi.org/{source.doi}"])
        if locators and not any(locator in line for locator in locators):
            errors.append(
                f"Reference [{source_id}] does not include its validated URL or DOI."
            )

    localized_ev_lim = (
        required_headings[-2]
        if required_headings and len(required_headings) >= 2
        else None
    )
    _ev_lim_headings = {"## Evidence Limitations"}
    if localized_ev_lim:
        _ev_lim_headings.add(localized_ev_lim)

    body_lines = body.splitlines()
    in_limitations = False
    for line_index, line in enumerate(body_lines):
        line_number = line_index + 1
        stripped = line.strip()
        if stripped.startswith("## "):
            in_limitations = stripped in _ev_lim_headings
        if not stripped or stripped.startswith("#") or re.fullmatch(r"[-|:\s]+", stripped):
            continue
        # Markdown unordered list items ("- …" or "* …")
        if re.match(r"^[-*]\s", stripped):
            continue
        # Bold headers: "**1. Title**", "**Use Case 1: Title**",
        # "**Recommendation 1 (High Priority): Title**"
        if re.fullmatch(r"\*\*(?:(?:\w+\s+){1,3})?\d+(?:\s*\([^)]+\))?[.:]\s*.+\*\*", stripped):
            continue
        # Numbered list items ("1. …") — ordinal markers, not numeric claims
        if re.match(r"^\d+\.\s", stripped):
            continue

        line_ids, line_citation_errors = parse_citation_ids(stripped)
        if line_citation_errors:
            continue
        # Table rows with a dedicated source-ID cell are implicitly cited
        table_row_with_source = (
            stripped.startswith("|") and _TABLE_SOURCE_CELL_PATTERN.search(stripped)
        )
        if not in_limitations and _NUMERIC_CLAIM_PATTERN.search(stripped) and not line_ids:
            if not table_row_with_source and not stripped.endswith(":"):
                errors.append(
                    f"Numeric claim on report line {line_number} has no inline citation."
                )
        elif _is_substantive_claim_line(body_lines, line_index, in_limitations) and not line_ids:
            errors.append(
                f"Substantive claim on report line {line_number} has no inline citation."
            )

    lowered = markdown.lower()
    _, check_phrases = _patent_disclaimer(output_language)
    if not all(phrase.lower() in lowered for phrase in check_phrases):
        errors.append(
            "The report must state that patent analysis is not legal advice or a "
            "freedom-to-operate opinion."
        )

    errors.extend(_validate_high_risk_claims(body, allowed_sources))

    return errors


def collect_context_finding_sources(
    context_tasks: Sequence[Any],
) -> dict[str, list[str]]:
    """Map internal finding IDs to their validated source IDs."""

    finding_sources: dict[str, list[str]] = {}
    for task in context_tasks:
        output = getattr(task, "output", None)
        report = getattr(output, "pydantic", None)
        if not isinstance(report, EvidenceReport):
            continue
        for finding in report.findings:
            finding_sources[finding.finding_id] = list(finding.source_ids)
    return finding_sources


def _normalize_parenthetical_citations(
    markdown: str,
    allowed_sources: dict[str, EvidenceSource],
) -> str:
    """Convert parenthetical source IDs such as (A1, P2) to canonical brackets."""

    pattern = re.compile(
        r"\((\s*[APM]\d+(?:\s*(?:[,;]|[-–—])\s*(?:[APM]\s*)?\d+)*\s*)\)"
    )

    def replace(match: re.Match[str]) -> str:
        source_ids, errors = parse_citation_ids(f"[{match.group(1)}]")
        if errors or not source_ids:
            return match.group(0)
        if any(source_id not in allowed_sources for source_id in source_ids):
            return match.group(0)
        return "[" + ", ".join(dict.fromkeys(source_ids)) + "]"

    return pattern.sub(replace, markdown)

def _normalize_report_citations(
    markdown: str,
    allowed_sources: dict[str, EvidenceSource],
    finding_sources: dict[str, list[str]],
) -> tuple[str, list[str]]:
    """Convert model citation variants into canonical source-ID citations."""

    normalization_errors: list[str] = []
    source_fragment = re.compile(r"\b[APM]\d+\b")
    finding_fragment = re.compile(r"\b[APM]F\d+\b")

    def append_unique(target: list[str], values: Sequence[str]) -> None:
        for value in values:
            if value not in target:
                target.append(value)

    def replace_block(match: re.Match[str]) -> str:
        content = match.group(1)
        if not re.search(r"\b[APM](?:F)?\d+", content):
            return match.group(0)

        source_ids: list[str] = []
        recognized = False
        for raw_part in re.split(r"\s*[,;]\s*", content.strip()):
            part = re.sub(
                r"\s+limitations?\s*$",
                "",
                raw_part.strip(),
                flags=re.IGNORECASE,
            )

            if part in finding_sources:
                recognized = True
                append_unique(source_ids, finding_sources[part])
                continue

            range_match = _SOURCE_RANGE_PATTERN.fullmatch(part)
            if range_match:
                recognized = True
                prefix, start_text, end_prefix, end_text = range_match.groups()
                if end_prefix and end_prefix != prefix:
                    normalization_errors.append(
                        f"Cross-prefix citation range is invalid: [{part}]."
                    )
                    return match.group(0)
                start = int(start_text)
                end = int(end_text)
                if end < start or end - start > 50:
                    normalization_errors.append(
                        f"Citation range is invalid or too large: [{part}]."
                    )
                    return match.group(0)
                append_unique(
                    source_ids,
                    [f"{prefix}{number}" for number in range(start, end + 1)],
                )
                continue

            if _SOURCE_TOKEN_PATTERN.fullmatch(part):
                recognized = True
                append_unique(source_ids, [part])
                continue

            findings = finding_fragment.findall(part)
            sources = source_fragment.findall(part)
            if findings or sources:
                recognized = True
            for finding_id in findings:
                mapped = finding_sources.get(finding_id)
                if mapped is not None:
                    append_unique(source_ids, mapped)
            append_unique(source_ids, sources)

        if not recognized:
            return match.group(0)
        if not source_ids:
            return ""

        unknown_ids = [
            source_id for source_id in source_ids if source_id not in allowed_sources
        ]
        if unknown_ids:
            normalization_errors.append(
                "Report body cites unknown source IDs: "
                + ", ".join(sorted(set(unknown_ids)))
                + "."
            )
        return "[" + ", ".join(source_ids) + "]"

    normalized = _BRACKET_PATTERN.sub(replace_block, markdown)
    return normalized, normalization_errors


_REF_LEGEND: dict[str, str] = {
    "Simplified Chinese":  "*文献编码说明：**A** = 学术论文 · **P** = 专利 · **M** = 市场/行业来源*",
    "Traditional Chinese": "*文獻編碼說明：**A** = 學術論文 · **P** = 專利 · **M** = 市場/產業來源*",
    "Japanese":            "*引用コード：**A** = 学術論文 · **P** = 特許 · **M** = 市場/業界情報*",
    "Korean":              "*참고문헌 코드：**A** = 학술 논문 · **P** = 특허 · **M** = 시장/업계 자료*",
}
_REF_LEGEND_EN = "*Reference codes: **A** = Academic paper · **P** = Patent · **M** = Market/industry source*"


def _canonical_reference_section(
    markdown: str,
    sources: dict[str, EvidenceSource],
    localized_ref_heading: str | None = None,
    output_language: str = "English",
) -> str:
    """Replace model-authored references with deterministic cited records."""

    # Strip the model's reference section (localized heading first, then English fallback)
    split_markers = []
    if localized_ref_heading and localized_ref_heading != "## References":
        split_markers.append(localized_ref_heading)
    split_markers.append("## References")
    body = markdown
    for marker in split_markers:
        if marker in body:
            body = body.split(marker, maxsplit=1)[0]
            break
    body = body.rstrip()
    cited_ids, _ = parse_citation_ids(body)
    cited_sources = {
        source_id: sources[source_id]
        for source_id in dict.fromkeys(cited_ids)
        if source_id in sources
    }
    prefix_order = {"A": 0, "P": 1, "M": 2}

    def sort_key(source_id: str) -> tuple[int, int]:
        return prefix_order.get(source_id[0], 99), int(source_id[1:])

    entries: list[str] = []
    for source_id in sorted(cited_sources, key=sort_key):
        source = cited_sources[source_id]
        published = (
            source.published_date.isoformat()
            if source.published_date is not None
            else "n.d."
        )
        locator = (
            str(source.url)
            if source.url is not None
            else f"https://doi.org/{source.doi}"
        )
        entries.append(
            f"[{source_id}] {source.title}. {source.publisher}. "
            f"Published: {published}. Accessed: {source.accessed_date.isoformat()}. "
            f"Type: {source.source_type}. Credibility: {source.credibility_tier}. "
            f"Rationale: {source.credibility_reason}. {locator}"
        )

    legend = _REF_LEGEND.get(output_language, _REF_LEGEND_EN)
    return f"{body}\n\n## References\n\n{legend}\n\n" + "\n\n".join(entries) + "\n"


def _repair_high_risk_phrasing(
    markdown: str,
    allowed_sources: dict[str, EvidenceSource],
) -> str:
    """Downgrade unsafe certainty without inventing replacement evidence."""

    repaired = re.sub(
        r"\bfreedom-to-operate opportunities\b",
        "areas requiring a dedicated freedom-to-operate analysis",
        markdown,
        flags=re.IGNORECASE,
    )
    repaired = re.sub(
        r"\bwithout infringing existing patents\b",
        "subject to a dedicated freedom-to-operate analysis",
        repaired,
        flags=re.IGNORECASE,
    )
    repaired = re.sub(
        r"\bnon[- ]infringing path\b|\bclear freedom to operate\b",
        "path requiring dedicated patent counsel review",
        repaired,
        flags=re.IGNORECASE,
    )
    repaired = re.sub(
        r"\[(?![^\]]*\b[APM]\d+\b)[^\]]*\blimitations?\b[^\]]*\]",
        "",
        repaired,
        flags=re.IGNORECASE,
    )

    has_government_source = any(
        source.source_type in {"government", "standards_body"}
        for source in allowed_sources.values()
    )
    if has_government_source:
        repaired = re.sub(
            r"\bno government(?:al)?\s+or\s+independent(?:\s+third-party)?\s+verification(?:\s+of\s+claims)?\b",
            (
                "Government sources were reviewed, but specific commercial claims "
                "may still lack independent verification"
            ),
            repaired,
            flags=re.IGNORECASE,
        )

    return repaired

def normalize_final_report(
    markdown: str,
    allowed_sources: dict[str, EvidenceSource],
    finding_sources: dict[str, list[str]],
    required_headings: tuple[str, ...] | None = None,
    output_language: str = "English",
) -> tuple[str, list[str]]:
    """Deterministically repair common model formatting errors."""

    # Normalise the Evidence Limitations heading (English form only)
    normalized = re.sub(
        r"(?m)^##\s+(?:\d+\.\s*)?Evidence Limitations\s*$",
        "## Evidence Limitations",
        markdown,
    )
    normalized = _normalize_parenthetical_citations(normalized, allowed_sources)
    normalized, errors = _normalize_report_citations(
        normalized,
        allowed_sources,
        finding_sources,
    )
    normalized = _repair_high_risk_phrasing(normalized, allowed_sources)

    disclaimer_text, check_phrases = _patent_disclaimer(output_language)
    lowered = normalized.lower()
    if not all(phrase.lower() in lowered for phrase in check_phrases):
        localized_ev_lim = (
            required_headings[-2] if required_headings and len(required_headings) >= 2
            else None
        )
        # localized_ref_hdg is the translated "## References" heading (e.g. "## 参考文献").
        # Inserting before it keeps the disclaimer inside the body that
        # _canonical_reference_section retains after splitting at this marker.
        localized_ref_hdg = (
            required_headings[-1] if required_headings and len(required_headings) >= 1
            else None
        )
        # Normalize localized heading: LLMs sometimes add a section number prefix
        # (e.g. "## 5. 証拠の限界") that won't match the stored "## 証拠の限界".
        if localized_ev_lim:
            heading_body = re.escape(localized_ev_lim.lstrip("# ").strip())
            normalized = re.sub(
                r"(?m)^##\s+(?:\d+\.\s*)?" + heading_body + r"\s*$",
                localized_ev_lim,
                normalized,
            )
        markers = []
        if localized_ev_lim and localized_ev_lim != "## Evidence Limitations":
            markers.append(localized_ev_lim)
        markers.append("## Evidence Limitations")
        if localized_ref_hdg and localized_ref_hdg not in markers:
            markers.append(localized_ref_hdg)   # e.g. "## 参考文献" for Japanese
        markers.append("## References")
        inserted = False
        for marker in markers:
            if marker in normalized:
                normalized = normalized.replace(
                    marker,
                    f"{disclaimer_text}\n\n{marker}",
                    1,
                )
                inserted = True
                break
        if not inserted:
            # Ultimate fallback: find the references section by detecting a ## heading
            # immediately followed by citation entries [A/P/M n], insert before it.
            m = re.search(r"(?m)^##[^\n]+\n+\[(?:A|P|M)\d", normalized)
            if m:
                pos = m.start()
                normalized = (
                    normalized[:pos] + disclaimer_text + "\n\n" + normalized[pos:]
                )
            else:
                # Absolute last resort: prepend to body so _canonical_reference_section
                # retains it (it only strips from the References heading onward).
                normalized = disclaimer_text + "\n\n" + normalized.lstrip()

    localized_ref = (
        required_headings[-1]
        if required_headings and len(required_headings) >= 1
        else None
    )
    normalized = _canonical_reference_section(normalized, allowed_sources, localized_ref, output_language)
    return normalized, errors


def _append_quality_control_warnings(
    markdown: str,
    warnings: Sequence[str],
) -> str:
    """Preserve a usable report while making non-blocking defects explicit."""

    unique_warnings = list(dict.fromkeys(warnings))
    if not unique_warnings:
        return markdown

    displayed = unique_warnings[:12]
    warning_lines = [f"- {warning}" for warning in displayed]
    remaining = len(unique_warnings) - len(displayed)
    if remaining:
        warning_lines.append(
            f"- {remaining} additional automated warnings were omitted for brevity."
        )
    warning_block = (
        "### Automated Quality-Control Warnings\n\n"
        "These statements remain in the report as analyst output but require "
        "manual verification before commercial, investment, or legal use.\n\n"
        + "\n".join(warning_lines)
        + "\n\n"
    )
    marker = "## References"
    if marker not in markdown:
        return markdown
    return markdown.replace(marker, warning_block + marker, 1)

def make_final_report_guardrail(
    context_tasks: Sequence[Any],
    *,
    required_headings: tuple[str, ...] | None = None,
    output_language: str = "English",
) -> Callable[[TaskOutput], tuple[bool, Any]]:
    """Normalize the report, then enforce citation and high-risk claim policies."""

    def validate_report(output: TaskOutput) -> tuple[bool, Any]:
        allowed_sources = collect_context_sources(context_tasks)
        finding_sources = collect_context_finding_sources(context_tasks)
        if not allowed_sources:
            return False, "No validated evidence sources are available in task context."
        if len(output.raw.strip()) < 500:
            return False, "Final report is too short to be usable."

        normalized, normalization_errors = normalize_final_report(
            output.raw,
            allowed_sources,
            finding_sources,
            required_headings=required_headings,
            output_language=output_language,
        )

        output.raw = normalized
        errors = validate_final_report(
            normalized, allowed_sources,
            required_headings=required_headings,
            output_language=output_language,
        )
        critical_prefixes = (
            "Missing required heading:",
            "The report body contains no source citations.",
            "Report body cites unknown source IDs:",
            "Malformed citation block:",
            "Cross-prefix citation range",
            "Citation range is invalid",
            "The report must state that patent analysis",
        )
        critical_errors = list(normalization_errors)
        critical_errors.extend(
            error
            for error in errors
            if error.startswith(critical_prefixes)
        )
        critical_errors = list(dict.fromkeys(critical_errors))
        if critical_errors:
            return (
                False,
                "Final report has blocking validation errors:\n- "
                + "\n- ".join(critical_errors),
            )

        return True, output

    return validate_report


_REVIEWER_REQUIRED_HEADINGS = ("## executive summary", "## references")


def make_reviewer_guardrail(
    report_task: Any,
    *,
    localized_headings: tuple[str, ...] | None = None,
    output_language: str = "English",
) -> Callable[[TaskOutput], tuple[bool, Any]]:
    """Light guardrail for Task 5: prevent regression from Task 4's validated output.

    Checks three things only — structural completeness is already guaranteed by
    Task 4's guardrail; this one just ensures the reviewer didn't accidentally
    break what was already correct:

    1. Length: reviewed report >= 500 chars AND >= 80 % of Task 4 length.
    2. Required headings (Executive Summary, References) still present.
    3. No inline citation IDs ([A*] [P*] [M*]) from Task 4 were removed.
    """

    def validate_review(output: TaskOutput) -> tuple[bool, Any]:
        task4_out = getattr(report_task, "output", None)
        task4_text: str = task4_out.raw if task4_out else ""
        task4_len = len(task4_text.strip())

        reviewed = output.raw.strip()
        reviewed_len = len(reviewed)

        errors: list[str] = []

        # 1. Length regression
        if reviewed_len < 500:
            errors.append(
                f"Report is too short ({reviewed_len} chars). "
                "Return the complete corrected report, not a summary."
            )
        elif task4_len > 0 and reviewed_len < int(task4_len * 0.8):
            pct = reviewed_len / task4_len
            errors.append(
                f"Report shrank too much ({reviewed_len} chars vs {task4_len} in draft, "
                f"{pct:.0%} retained). Apply corrections in place; do not omit sections."
            )

        # 2. Required headings (use localized equivalents when provided)
        # localized_headings order: [title, exec_summary, ..., evidence_limits, references]
        # References is always written in English by _canonical_reference_section,
        # so check both the localized form and the English "## references".
        if localized_headings and len(localized_headings) >= 2:
            exec_summary_heading = localized_headings[1].lower()
            localized_ref = localized_headings[-1].lower()
            reviewer_headings_pairs = [
                (exec_summary_heading,),
                (localized_ref, "## references"),  # accept either form
            ]
        else:
            reviewer_headings_pairs = [(h,) for h in _REVIEWER_REQUIRED_HEADINGS]
        reviewed_lower = reviewed.lower()
        for candidates in reviewer_headings_pairs:
            if not any(c in reviewed_lower for c in candidates):
                errors.append(
                    f"Required section '{candidates[0].lstrip('# ')}' is missing. "
                    "Do not remove any sections from the report."
                )

        # 3. Citation ID regression — only count IDs inside square brackets to
        # avoid false matches with non-citation tokens like "P2/P3型" or "A1规格".
        def _bracket_ids(text: str) -> set[str]:
            ids: set[str] = set()
            for group in re.findall(r"\[([^\]]+)\]", text):
                ids.update(re.findall(r"[APM]\d+", group))
            return ids

        if task4_text:
            task4_ids = _bracket_ids(task4_text)
            reviewed_ids = _bracket_ids(reviewed)
            missing = task4_ids - reviewed_ids
            if missing:
                errors.append(
                    f"Inline citation IDs removed by reviewer: {sorted(missing)}. "
                    "All citations from the draft must be preserved."
                )

        if errors:
            return (
                False,
                "Reviewer output has blocking issues:\n- " + "\n- ".join(errors),
            )

        # Re-insert patent disclaimer if the reviewer removed or re-translated it.
        _disclaimer, _check_phrases = _patent_disclaimer(output_language)
        reviewed_lower_check = output.raw.lower()
        if not all(phrase.lower() in reviewed_lower_check for phrase in _check_phrases):
            # Find insertion point: localized Evidence Limitations heading or English fallback
            ev_lim_candidates = []
            if localized_headings and len(localized_headings) >= 2:
                ev_lim_candidates.append(localized_headings[-2])  # localized form
            ev_lim_candidates.append("## Evidence Limitations")
            raw = output.raw
            for marker in ev_lim_candidates:
                if marker in raw:
                    output.raw = raw.replace(marker, f"{_disclaimer}\n\n{marker}", 1)
                    break

        return True, output

    return validate_review
