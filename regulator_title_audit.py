"""Audit regulator-source title structure over frozen source collections.

This command never retrieves a page and never normalizes production evidence.
It measures only a deliberately narrow set of structural title failures, then
keeps a zero official-source denominator distinct from a clean result.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, HttpUrl

from academic_agent.source_pipeline import SourceCollection


AuthorityScope = Literal["regulatory", "clinical_registry", "out_of_scope"]
TitleStatus = Literal["clean", "review_required", "out_of_scope"]
ReasonCode = Literal[
    "empty_title",
    "host_or_url_only",
    "encoding_replacement_character",
    "fragmented_single_letter_tokens",
]

# This is an audit protocol, not a live policy object. Freezing the exact host
# set makes a result reproducible even if production later adds another
# regulator. The protocol records that these values matched production on
# 2026-08-25; changing them requires a new schema version, not a silent rerun.
REGULATORY_DOMAINS = frozenset(
    {
        "fda.gov",
        "ema.europa.eu",
        "mhra.gov.uk",
        "tga.gov.au",
        "pmda.go.jp",
    }
)
CLINICAL_REGISTRY_DOMAINS = frozenset(
    {
        "clinicaltrials.gov",
        "clinicaltrialsregister.eu",
        "euclinicaltrials.eu",
        "isrctn.com",
        "anzctr.org.au",
    }
)

CASE_FIELDS = (
    "dataset",
    "fixture",
    "fixture_sha256",
    "source_domain",
    "source_id",
    "authority_scope",
    "host",
    "title",
    "url",
    "status",
    "reason_codes",
    "provenance",
    "expected_scope",
    "expected_status",
    "expected_reason_codes",
    "matches_expectation",
)


class RegulatorTitleAuditError(ValueError):
    """Raised when an audit would accept partial or ambiguous input."""


class FrozenChallengeCase(BaseModel):
    """One disclosed post-hoc or synthetic title-quality regression case."""

    case_id: str = Field(min_length=3)
    provenance: Literal[
        "observed_production",
        "synthetic_negative_control",
        "synthetic_positive_control",
        "synthetic_scope_control",
    ]
    run_id: str | None = None
    source_id: str = Field(min_length=2)
    # Empty is allowed here because the challenge contract must be able to
    # prove that the screen catches an empty title. Valid SourceCollection
    # records already reject it earlier through EvidenceSource.
    title: str
    url: HttpUrl
    expected_scope: AuthorityScope
    expected_status: TitleStatus
    expected_reason_codes: list[ReasonCode] = Field(default_factory=list)


class FrozenChallenge(BaseModel):
    """Versioned challenge whose labels are evaluated without network access."""

    schema_version: Literal[1]
    measurement_design: str = Field(min_length=10)
    cases: list[FrozenChallengeCase] = Field(min_length=1)


def _host_matches(host: str, domains: frozenset[str]) -> bool:
    """Match exact hosts or subdomains without trusting attacker suffixes."""

    normalized = host.removeprefix("www.").lower()
    return any(
        normalized == domain or normalized.endswith(f".{domain}")
        for domain in domains
    )


def authority_scope_for_url(url: str) -> AuthorityScope:
    """Return the frozen authority scope for a URL."""

    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return "out_of_scope"
    if _host_matches(host, REGULATORY_DOMAINS):
        return "regulatory"
    if _host_matches(host, CLINICAL_REGISTRY_DOMAINS):
        return "clinical_registry"
    return "out_of_scope"


def _is_host_or_url_only(title: str, url: str, host: str) -> bool:
    """Detect only identities, not merely short or generic regulator titles."""

    normalized_title = title.strip().lower().rstrip("/")
    normalized_url = url.strip().lower().rstrip("/")
    bare_url = re.sub(r"^https?://", "", normalized_url)
    bare_host = host.removeprefix("www.")
    return normalized_title in {
        normalized_url,
        bare_url,
        host,
        bare_host,
        f"www.{bare_host}",
    }


def assess_title(title: str, url: str) -> tuple[TitleStatus, list[ReasonCode]]:
    """Apply the frozen precision-first structural title screen.

    A clean result is intentionally modest: it means that none of four
    structural failure signatures fired. It does not establish semantic title
    correctness or correspondence to the linked record.
    """

    scope = authority_scope_for_url(url)
    if scope == "out_of_scope":
        return "out_of_scope", []

    stripped = title.strip()
    reasons: list[ReasonCode] = []
    host = (urlsplit(url).hostname or "").lower()
    if not stripped:
        reasons.append("empty_title")
    elif _is_host_or_url_only(stripped, url, host):
        reasons.append("host_or_url_only")

    if "\ufffd" in title:
        reasons.append("encoding_replacement_character")

    # The known FDA failure contains four isolated b/I fragments followed by
    # the source host. Requiring all three signals avoids treating product
    # codes, 510(k), initials, punctuation, or one-letter trial arms as enough
    # evidence of corruption.
    alpha_tokens = re.findall(r"[A-Za-z]+", title)
    single_letter_tokens = sum(len(token) == 1 for token in alpha_tokens)
    title_lower = title.lower()
    visible_host = host.removeprefix("www.")
    if (
        single_letter_tokens >= 4
        and single_letter_tokens * 2 >= len(alpha_tokens)
        and bool(visible_host)
        and visible_host in title_lower
    ):
        reasons.append("fragmented_single_letter_tokens")

    return ("review_required" if reasons else "clean"), reasons


def discover_collections(fixtures: Path) -> list[Path]:
    """Find either run artifacts or tracked flat benchmark fixtures.

    The live benchmark stores one ``validated_sources.json`` per direct child.
    A clean clone retains ten equivalent SourceCollection snapshots as direct
    JSON files. Supporting both layouts lets the 30-run census use the original
    artifacts while CI can exercise the same parser over tracked evidence.
    """

    run_artifacts = sorted(fixtures.glob("*/validated_sources.json"))
    flat_fixtures = sorted(
        path
        for path in fixtures.glob("*.json")
        if path.name != "manifest.json"
    )
    paths = run_artifacts + flat_fixtures
    if not paths:
        raise RegulatorTitleAuditError(
            f"no source collections found directly under {fixtures}"
        )
    return paths


def _fixture_name(fixtures: Path, path: Path) -> str:
    relative = path.relative_to(fixtures)
    if path.name == "validated_sources.json":
        return relative.parent.as_posix()
    return relative.as_posix()


def _read_collection(path: Path) -> tuple[SourceCollection, str]:
    try:
        payload = path.read_bytes()
        collection = SourceCollection.model_validate_json(payload)
    except (OSError, ValueError) as exc:
        raise RegulatorTitleAuditError(f"could not load {path}: {exc}") from exc
    return collection, hashlib.sha256(payload).hexdigest()


def _all_sources(collection: SourceCollection):
    yield from (("academic", source) for source in collection.academic_sources)
    yield from (("patent", source) for source in collection.patent_sources)
    yield from (("market", source) for source in collection.market_sources)


def _benchmark_rows(
    fixtures: Path,
    path: Path,
    fixture_sha256: str,
    collection: SourceCollection,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_domain, source in _all_sources(collection):
        if source.url is None:
            continue
        url = str(source.url)
        scope = authority_scope_for_url(url)
        if scope == "out_of_scope":
            continue
        status, reasons = assess_title(source.title, url)
        rows.append(
            {
                "dataset": "benchmark",
                "fixture": _fixture_name(fixtures, path),
                "fixture_sha256": fixture_sha256,
                "source_domain": source_domain,
                "source_id": source.source_id,
                "authority_scope": scope,
                "host": (urlsplit(url).hostname or "").lower(),
                "title": source.title,
                "url": url,
                "status": status,
                "reason_codes": "|".join(reasons),
                "provenance": "stored_source_collection",
                "expected_scope": "",
                "expected_status": "",
                "expected_reason_codes": "",
                "matches_expectation": "",
            }
        )
    return rows


def _read_challenge(path: Path) -> tuple[FrozenChallenge, str]:
    try:
        payload = path.read_bytes()
        challenge = FrozenChallenge.model_validate_json(payload)
    except (OSError, ValueError) as exc:
        raise RegulatorTitleAuditError(f"could not load challenge {path}: {exc}") from exc
    return challenge, hashlib.sha256(payload).hexdigest()


def _challenge_rows(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    challenge, challenge_sha256 = _read_challenge(path)
    rows: list[dict[str, Any]] = []
    for case in challenge.cases:
        url = str(case.url)
        scope = authority_scope_for_url(url)
        status, reasons = assess_title(case.title, url)
        expected_reasons = list(case.expected_reason_codes)
        matches = (
            scope == case.expected_scope
            and status == case.expected_status
            and reasons == expected_reasons
        )
        rows.append(
            {
                "dataset": "challenge",
                "fixture": case.case_id,
                "fixture_sha256": challenge_sha256,
                "source_domain": "challenge",
                "source_id": case.source_id,
                "authority_scope": scope,
                "host": (urlsplit(url).hostname or "").lower(),
                "title": case.title,
                "url": url,
                "status": status,
                "reason_codes": "|".join(reasons),
                "provenance": case.provenance,
                "expected_scope": case.expected_scope,
                "expected_status": case.expected_status,
                "expected_reason_codes": "|".join(expected_reasons),
                "matches_expectation": matches,
            }
        )

    matched = sum(bool(row["matches_expectation"]) for row in rows)
    result = {
        "state": "matched" if matched == len(rows) else "failed",
        "case_count": len(rows),
        "matched_expectation_count": matched,
        "sha256": challenge_sha256,
        "measurement_design": challenge.measurement_design,
    }
    return result, rows


def evaluate_audit(
    fixtures: Path,
    *,
    expected_count: int | None = None,
    challenge_path: Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Census frozen titles and optionally run the disclosed challenge."""

    paths = discover_collections(fixtures)
    if expected_count is not None and len(paths) != expected_count:
        raise RegulatorTitleAuditError(
            f"fixture count is {len(paths)}, expected exactly {expected_count}"
        )

    rows: list[dict[str, Any]] = []
    fixture_manifest: list[dict[str, Any]] = []
    affected_fixtures: set[str] = set()
    for path in paths:
        collection, fixture_sha256 = _read_collection(path)
        fixture = _fixture_name(fixtures, path)
        fixture_rows = _benchmark_rows(
            fixtures,
            path,
            fixture_sha256,
            collection,
        )
        rows.extend(fixture_rows)
        if fixture_rows:
            affected_fixtures.add(fixture)
        fixture_manifest.append(
            {
                "fixture": fixture,
                "sha256": fixture_sha256,
                "official_source_count": len(fixture_rows),
            }
        )

    benchmark_rows = list(rows)
    flagged = sum(row["status"] == "review_required" for row in benchmark_rows)
    if not benchmark_rows:
        benchmark_state = "not_assessable_zero_denominator"
    elif flagged:
        benchmark_state = "review_required"
    else:
        benchmark_state = "checked_no_structural_flags"

    challenge_result: dict[str, Any] = {
        "state": "not_run",
        "case_count": 0,
        "matched_expectation_count": 0,
        "sha256": None,
        "measurement_design": None,
    }
    if challenge_path is not None:
        challenge_result, challenge_rows = _challenge_rows(challenge_path)
        rows.extend(challenge_rows)

    scope_counts = Counter(row["authority_scope"] for row in benchmark_rows)
    reason_counts = Counter(
        reason
        for row in benchmark_rows
        for reason in str(row["reason_codes"]).split("|")
        if reason
    )
    unique_urls = {str(row["url"]) for row in benchmark_rows}
    checks = [
        {
            "name": "loaded_expected_fixture_count",
            "passed": expected_count is None or len(paths) == expected_count,
            "observed": len(paths),
            "requirement": (
                "at least one"
                if expected_count is None
                else f"exactly {expected_count}"
            ),
        },
        {
            "name": "every_fixture_manifested",
            "passed": len(fixture_manifest) == len(paths),
            "observed": len(fixture_manifest),
            "requirement": len(paths),
        },
        {
            "name": "challenge_expectations_match",
            "passed": challenge_result["state"] in {"not_run", "matched"},
            "observed": challenge_result["state"],
            "requirement": "not_run or matched",
        },
    ]
    contract_checks_passed = all(bool(check["passed"]) for check in checks)
    result = {
        "schema_version": 1,
        "protocol": "regulator-source-title-quality-v1",
        "measurement_design": (
            "retrospective_development_census_plus_disclosed_challenge"
        ),
        "collection_count": len(paths),
        "fixture_manifest": fixture_manifest,
        "benchmark": {
            "state": benchmark_state,
            "official_source_count": len(benchmark_rows),
            "unique_official_url_count": len(unique_urls),
            "affected_collection_count": len(affected_fixtures),
            "clean_source_count": len(benchmark_rows) - flagged,
            "review_required_source_count": flagged,
            "scope_counts": dict(sorted(scope_counts.items())),
            "reason_counts": dict(sorted(reason_counts.items())),
        },
        "challenge": challenge_result,
        "checks": checks,
        "contract_checks_passed": contract_checks_passed,
        "network_calls": 0,
        "production_mutations": 0,
        "normalization_applied": False,
        "measurement_limit": (
            "A zero denominator is not a clean pass. Structural screens do not "
            "establish semantic title correctness, source truth, prevalence, "
            "or held-out precision and recall."
        ),
    }
    return result, rows


def write_audit(
    output: Path,
    result: dict[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    """Persist aggregate and case evidence without replacing a prior audit."""

    if output.exists():
        raise RegulatorTitleAuditError(
            f"refusing to overwrite audit output: {output}"
        )
    output.mkdir(parents=True)
    (output / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with (output / "cases.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CASE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixtures", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected-count", type=int, default=None)
    parser.add_argument("--challenge", type=Path, default=None)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    result, rows = evaluate_audit(
        args.fixtures,
        expected_count=args.expected_count,
        challenge_path=args.challenge,
    )
    write_audit(args.output, result, rows)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not result["contract_checks_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
