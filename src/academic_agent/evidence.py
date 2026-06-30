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
from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


SourceType = Literal[
    "academic_paper",
    "patent",
    "company_disclosure",
    "government",
    "standards_body",
    "market_report",
    "reputable_news",
    "other",
]
ClaimType = Literal["observed_fact", "estimate", "analyst_inference"]
Confidence = Literal["high", "medium", "low"]
UrlChecker = Callable[[str], tuple[bool, str]]

_DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
_SOURCE_ID_PATTERN = re.compile(r"^[APM]\d+$")
_BRACKET_PATTERN = re.compile(r"\[([^\[\]]+)\]")
_SOURCE_TOKEN_PATTERN = re.compile(r"^[APM]\d+$")
_SOURCE_RANGE_PATTERN = re.compile(
    r"^([APM])(\d+)\s*[-–—]\s*(?:([APM])\s*)?(\d+)$"
)
_REFERENCE_ENTRY_PATTERN = re.compile(r"(?m)^\s*\[([APM]\d+)\]\s+")
_NUMERIC_CLAIM_PATTERN = re.compile(
    r"(?<!\[)\b(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)"
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
    evidence_summary: str = Field(
        min_length=20,
        description="A concise paraphrase of what this source actually supports.",
    )

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
            raise ValueError("Published date cannot be in the future.")
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
    sources: list[EvidenceSource] = Field(min_length=3)
    limitations: list[str] = Field(min_length=1)


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
                except (HTTPError, URLError, TimeoutError) as get_exc:
                    return False, f"GET fallback failed: {get_exc}"
            return False, f"HTTP status {exc.code}"
        except (URLError, TimeoutError, OSError) as exc:
            return False, f"request failed: {exc}"

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

    unused_sources = source_id_set - referenced_ids
    if unused_sources:
        errors.append(
            "Every listed source must support at least one finding; unused sources: "
            f"{', '.join(sorted(unused_sources))}."
        )

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
    if not isinstance(output.pydantic, EvidenceReport):
        return (
            False,
            "Return valid structured EvidenceReport data. Do not return free-form "
            "markdown or prose.",
        )

    errors = validate_evidence_report(output.pydantic, expected_prefix)
    if not errors:
        errors.extend(validate_source_reachability(output.pydantic))
    if errors:
        return False, "Evidence validation failed:\n- " + "\n- ".join(errors)

    return True, output


def validate_academic_evidence(output: TaskOutput) -> tuple[bool, Any]:
    return _evidence_guardrail(output, "A")


def validate_patent_evidence(output: TaskOutput) -> tuple[bool, Any]:
    return _evidence_guardrail(output, "P")


def validate_market_evidence(output: TaskOutput) -> tuple[bool, Any]:
    return _evidence_guardrail(output, "M")


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
    if stripped.startswith("|") and line_index + 1 < len(lines):
        if re.fullmatch(r"[\s|:-]+", lines[line_index + 1].strip()):
            return False
    without_citations = _BRACKET_PATTERN.sub("", stripped)
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", without_citations)
    return len(words) >= 5


def validate_final_report(
    markdown: str,
    allowed_sources: dict[str, EvidenceSource],
) -> list[str]:
    """Validate citation integrity in the final Markdown report."""

    errors: list[str] = []
    for heading in _REQUIRED_REPORT_HEADINGS:
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

    body_lines = body.splitlines()
    in_limitations = False
    for line_index, line in enumerate(body_lines):
        line_number = line_index + 1
        stripped = line.strip()
        if stripped.startswith("## "):
            in_limitations = stripped == "## Evidence Limitations"
        if not stripped or stripped.startswith("#") or re.fullmatch(r"[-|:\s]+", stripped):
            continue

        line_ids, line_citation_errors = parse_citation_ids(stripped)
        if line_citation_errors:
            continue
        if _NUMERIC_CLAIM_PATTERN.search(stripped) and not line_ids:
            errors.append(
                f"Numeric claim on report line {line_number} has no inline citation."
            )
        elif _is_substantive_claim_line(body_lines, line_index, in_limitations) and not line_ids:
            errors.append(
                f"Substantive claim on report line {line_number} has no inline citation."
            )

    lowered = markdown.lower()
    if "not legal advice" not in lowered or "freedom-to-operate" not in lowered:
        errors.append(
            "The report must state that patent analysis is not legal advice or a "
            "freedom-to-operate opinion."
        )

    return errors


def make_final_report_guardrail(
    context_tasks: Sequence[Any],
) -> Callable[[TaskOutput], tuple[bool, Any]]:
    """Create a final-report guardrail bound to completed evidence tasks."""

    def validate_report(output: TaskOutput) -> tuple[bool, Any]:
        allowed_sources = collect_context_sources(context_tasks)
        if not allowed_sources:
            return False, "No validated evidence sources are available in task context."
        errors = validate_final_report(output.raw, allowed_sources)
        if errors:
            return False, "Final report validation failed:\n- " + "\n- ".join(errors)
        return True, output

    return validate_report
