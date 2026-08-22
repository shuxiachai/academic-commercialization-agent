"""Evaluate the frozen patent topic-slot review candidate without network calls.

The human audit measures whether patents already accepted by retrieval are
topically relevant.  This module evaluates one deliberately conservative
candidate over those same frozen cases.  It does not alter retrieval: `REVIEW`
means "show an operator why this source is ambiguous", and `DROP` remains an
offline experiment until a separate held-out study supports production use.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import patent_relevance_eval as patent_eval


Action = Literal["KEEP", "REVIEW", "DROP"]

CANDIDATE_ID = "patent-topic-slot-review-v1"
ACTIONS: tuple[Action, ...] = ("KEEP", "REVIEW", "DROP")
WINDOW_RADIUS = 180
MORPHOLOGICAL_PREFIX_LENGTH = 6

# These words route a search but do not describe either the invention or its
# intended application.  Keeping this set short is deliberate: a false review
# is less harmful than an automatic drop, but a screen that reviews everything
# creates no operational value and fails the pre-registered workload gate.
TOPIC_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "application",
        "applications",
        "commercial",
        "commercialization",
        "deployment",
        "for",
        "in",
        "of",
        "system",
        "systems",
        "technology",
        "the",
        "to",
        "using",
        "with",
    }
)

# The markers are intentionally phrase-level.  A bare word such as "including"
# occurs in genuine claim summaries too often to be a precise warning.  Every
# marker was frozen in the pre-registration before the candidate was run.
WEAK_CONTEXT_MARKERS = (
    "variety of applications",
    "applications such as",
    "applications include",
    "applied to a variety",
    "merely by way of example",
    "including but not limited",
    "any other complex",
    "description of related techniques",
    "background",
    "has included",
    "other sources",
)

DECISION_FIELDS = (
    "case_id",
    "corpus",
    "topic",
    "action",
    "reason",
    "technology_anchor",
    "application_tokens",
    "technology_in_title",
    "technology_in_evidence",
    "application_in_title",
    "application_in_evidence",
    "weak_context_markers",
    "human_label",
)

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class PatentCandidateError(ValueError):
    """Raised when candidate metrics would describe a drifting or partial audit."""


@dataclass(frozen=True)
class CandidateDecision:
    """One label-blind decision and the features needed to audit it."""

    case_id: str
    corpus: str
    topic: str
    action: Action
    reason: str
    technology_anchor: str
    application_tokens: tuple[str, ...]
    technology_in_title: bool
    technology_in_evidence: bool
    application_in_title: bool
    application_in_evidence: bool
    weak_context_markers: tuple[str, ...]


def _normalise_token(token: str) -> str:
    """Apply only inflections that are safe for short technical phrases."""

    value = token.casefold()
    if len(value) > 4 and value.endswith("ies"):
        return value[:-3] + "y"
    if len(value) > 4 and value.endswith("s") and not value.endswith("ss"):
        return value[:-1]
    return value


def _meaningful_tokens(text: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for raw in _TOKEN_PATTERN.findall(text.casefold().replace("-", " ")):
        token = _normalise_token(raw)
        if len(token) < 3 or token in TOPIC_STOP_WORDS:
            continue
        # Repeated topic words add no independent evidence but would make the
        # same support window satisfy the application slot more than once.
        if token not in tokens:
            tokens.append(token)
    return tuple(tokens)


def _topic_slots(topic: str) -> tuple[str, tuple[str, ...]]:
    lower = topic.casefold()
    if " for " in lower:
        technology_phrase, application_phrase = lower.split(" for ", 1)
    else:
        technology_phrase, application_phrase = lower, ""
    technology_tokens = _meaningful_tokens(technology_phrase)
    if not technology_tokens:
        raise PatentCandidateError(f"topic has no technology anchor: {topic!r}")
    return technology_tokens[-1], _meaningful_tokens(application_phrase)


def _token_matches(anchor: str, observed: str) -> bool:
    if anchor == observed:
        return True
    # This handles common pairs such as computing/computer,
    # discovery/discover, industrial/industry, and vaccine/vaccination.  Six
    # characters is long enough to avoid turning generic three-letter stems
    # into support while remaining language-model independent.
    return (
        len(anchor) >= MORPHOLOGICAL_PREFIX_LENGTH
        and len(observed) >= MORPHOLOGICAL_PREFIX_LENGTH
        and anchor[:MORPHOLOGICAL_PREFIX_LENGTH]
        == observed[:MORPHOLOGICAL_PREFIX_LENGTH]
    )


def _normalised_text(text: str) -> str:
    return " ".join(_TOKEN_PATTERN.findall(text.casefold().replace("-", " ")))


def _has_token(text: str, anchor: str) -> bool:
    return any(
        _token_matches(anchor, _normalise_token(raw))
        for raw in _TOKEN_PATTERN.findall(text)
    )


def _support_windows(text: str, required: tuple[str, ...]) -> tuple[str, ...]:
    """Return bounded windows that contain every required application token."""

    if not required:
        return ()
    normalised = _normalised_text(text)
    windows: list[str] = []
    for match in _TOKEN_PATTERN.finditer(normalised):
        if not _token_matches(required[0], _normalise_token(match.group())):
            continue
        start = max(0, match.start() - WINDOW_RADIUS)
        end = min(len(normalised), match.end() + WINDOW_RADIUS)
        window = normalised[start:end]
        if all(_has_token(window, token) for token in required) and window not in windows:
            windows.append(window)
    return tuple(windows)


def screen_case(case: patent_eval.PatentCase) -> CandidateDecision:
    """Apply the frozen rule without receiving a human label or rationale."""

    technology_anchor, application_tokens = _topic_slots(case.topic)
    title = _normalised_text(case.title)
    evidence = _normalised_text(case.evidence_summary)
    technology_in_title = _has_token(title, technology_anchor)
    technology_in_evidence = _has_token(evidence, technology_anchor)
    title_windows = _support_windows(title, application_tokens)
    evidence_windows = _support_windows(evidence, application_tokens)
    weak_markers = tuple(
        marker
        for marker in WEAK_CONTEXT_MARKERS
        if any(marker in window for window in evidence_windows)
    )

    if not (technology_in_title or technology_in_evidence):
        action: Action = "DROP"
        reason = (
            f"technology anchor {technology_anchor!r} is absent from title and evidence"
        )
    elif application_tokens and not (title_windows or evidence_windows):
        action = "REVIEW"
        reason = (
            "application slot has no bounded support: "
            + " ".join(application_tokens)
        )
    elif application_tokens and not title_windows and weak_markers:
        action = "REVIEW"
        reason = (
            "application support appears only in evidence with weak-context marker(s): "
            + ", ".join(weak_markers)
        )
    else:
        action = "KEEP"
        if not application_tokens:
            reason = "technology anchor is supported; topic has no application slot"
        elif title_windows:
            reason = "technology and application slots are supported in the title"
        else:
            reason = "technology slot and focused application evidence are supported"

    return CandidateDecision(
        case_id=case.case_id,
        corpus=case.corpus,
        topic=case.topic,
        action=action,
        reason=reason,
        technology_anchor=technology_anchor,
        application_tokens=application_tokens,
        technology_in_title=technology_in_title,
        technology_in_evidence=technology_in_evidence,
        application_in_title=bool(title_windows),
        application_in_evidence=bool(evidence_windows),
        weak_context_markers=weak_markers,
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PatentCandidateError(f"could not read JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PatentCandidateError(f"{path} must contain a JSON object")
    return value


def _complete_labels(labels_path: Path, manifest_path: Path) -> dict[str, str]:
    summary = patent_eval.summarize_labels(labels_path, manifest_path)
    if summary["protocol_status"] != "complete":
        raise PatentCandidateError(
            "candidate evaluation requires a complete human label set; "
            f"completed={summary['completed_case_count']}/{summary['case_count']}"
        )
    try:
        with labels_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:
        raise PatentCandidateError(f"could not read labels from {labels_path}: {exc}") from exc
    return {row["case_id"]: row["label"].strip().upper() for row in rows}


def _label_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(row["human_label"]) for row in rows)
    return {label: counts[label] for label in sorted(patent_eval.LABELS)}


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    action_counts = Counter(str(row["action"]) for row in rows)
    labels = _label_counts(rows)
    by_action = {
        action: _label_counts([row for row in rows if row["action"] == action])
        for action in ACTIONS
    }
    kept = [row for row in rows if row["action"] == "KEEP"]
    kept_counts = _label_counts(kept)
    keep_count = len(kept)

    # None, rather than zero, distinguishes "the candidate kept nothing" from
    # "the candidate kept evidence and none of it was relevant".
    keep_direct_precision = (
        kept_counts["RELEVANT"] / keep_count if keep_count else None
    )
    keep_usable_precision = (
        (kept_counts["RELEVANT"] + kept_counts["WEAK"]) / keep_count
        if keep_count
        else None
    )
    return {
        "case_count": total,
        "action_counts": {action: action_counts[action] for action in ACTIONS},
        "human_label_counts": labels,
        "human_labels_by_action": by_action,
        "keep_direct_precision": keep_direct_precision,
        "keep_usable_precision": keep_usable_precision,
        "relevant_review_count": by_action["REVIEW"]["RELEVANT"],
        "relevant_drop_count": by_action["DROP"]["RELEVANT"],
        "weak_review_or_drop_count": (
            by_action["REVIEW"]["WEAK"] + by_action["DROP"]["WEAK"]
        ),
        "irrelevant_review_or_drop_count": (
            by_action["REVIEW"]["IRRELEVANT"]
            + by_action["DROP"]["IRRELEVANT"]
        ),
        "manual_review_load": action_counts["REVIEW"] / total if total else None,
    }


def _gate(
    name: str,
    passed: bool,
    observed: Any,
    requirement: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "passed": passed,
        "observed": observed,
        "requirement": requirement,
    }


def evaluate_candidate(
    fixture_dir: Path,
    labels_path: Path,
    manifest_path: Path,
    *,
    challenge_paths: Iterable[Path] = (),
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Screen frozen cases first, then join labels only for aggregate metrics."""

    manifest = _read_json(manifest_path)
    manifest_cases = manifest.get("cases")
    if not isinstance(manifest_cases, list) or not manifest_cases:
        raise PatentCandidateError(f"{manifest_path} has no cases")
    cases = patent_eval.discover_cases(fixture_dir, challenge_paths)
    frozen_hashes = {
        str(case.get("case_id", "")): str(case.get("content_sha256", ""))
        for case in manifest_cases
    }
    current_hashes = {case.case_id: case.content_sha256 for case in cases}
    if current_hashes != frozen_hashes:
        missing = sorted(set(frozen_hashes) - set(current_hashes))
        extra = sorted(set(current_hashes) - set(frozen_hashes))
        changed = sorted(
            case_id
            for case_id in set(current_hashes) & set(frozen_hashes)
            if current_hashes[case_id] != frozen_hashes[case_id]
        )
        raise PatentCandidateError(
            "candidate cases do not match frozen manifest; "
            f"missing={missing}, extra={extra}, changed={changed}"
        )

    # Decisions are completed before labels are loaded.  This ordering is the
    # executable counterpart of screen_case's label-free function signature.
    decisions = [screen_case(case) for case in cases]
    labels = _complete_labels(labels_path, manifest_path)
    rows: list[dict[str, Any]] = []
    for decision in decisions:
        row = asdict(decision)
        row["application_tokens"] = "|".join(decision.application_tokens)
        row["weak_context_markers"] = "|".join(decision.weak_context_markers)
        row["human_label"] = labels[decision.case_id]
        rows.append(row)

    overall = _metrics(rows)
    by_corpus = {
        corpus: _metrics([row for row in rows if row["corpus"] == corpus])
        for corpus in sorted({str(row["corpus"]) for row in rows})
    }
    baseline_direct = overall["human_label_counts"]["RELEVANT"] / len(rows)
    keep_direct = overall["keep_direct_precision"]
    precision_improvement = (
        keep_direct - baseline_direct if keep_direct is not None else None
    )
    irrelevant_total = overall["human_label_counts"]["IRRELEVANT"]
    gates = [
        _gate(
            "zero_relevant_auto_drops",
            overall["relevant_drop_count"] == 0,
            overall["relevant_drop_count"],
            "equals 0",
        ),
        _gate(
            "capture_all_irrelevant",
            overall["irrelevant_review_or_drop_count"] == irrelevant_total,
            overall["irrelevant_review_or_drop_count"],
            f"equals {irrelevant_total}",
        ),
        _gate(
            "capture_at_least_six_weak",
            overall["weak_review_or_drop_count"] >= 6,
            overall["weak_review_or_drop_count"],
            "at least 6",
        ),
        _gate(
            "improve_keep_direct_precision_by_two_points",
            precision_improvement is not None and precision_improvement >= 0.02,
            precision_improvement,
            "at least 0.02",
        ),
        _gate(
            "review_no_more_than_twenty_cases",
            overall["action_counts"]["REVIEW"] <= 20,
            overall["action_counts"]["REVIEW"],
            "at most 20",
        ),
        _gate(
            "match_all_frozen_case_hashes",
            len(current_hashes) == len(frozen_hashes),
            len(current_hashes),
            f"equals {len(frozen_hashes)}",
        ),
    ]
    result = {
        "schema_version": 1,
        "candidate_id": CANDIDATE_ID,
        "protocol_status": "complete",
        "measurement_design": "post_hoc_development_not_held_out",
        "case_count": len(rows),
        "candidate_spec": {
            "window_radius": WINDOW_RADIUS,
            "morphological_prefix_length": MORPHOLOGICAL_PREFIX_LENGTH,
            "topic_stop_words": sorted(TOPIC_STOP_WORDS),
            "weak_context_markers": list(WEAK_CONTEXT_MARKERS),
        },
        "baseline": {
            "accept_action": "KEEP",
            "case_count": len(rows),
            "direct_relevance": baseline_direct,
            "usable_relevance": (
                overall["human_label_counts"]["RELEVANT"]
                + overall["human_label_counts"]["WEAK"]
            )
            / len(rows),
        },
        "metrics": overall,
        "by_corpus": by_corpus,
        "precision_improvement": precision_improvement,
        "gates": gates,
        "qualified_for_held_out_challenge": all(gate["passed"] for gate in gates),
        "production_change_authorized": False,
        "measurement_limit": (
            "Label-aware post-hoc development on accepted sources; this does not "
            "measure retrieval recall or validate production filtering."
        ),
    }
    return result, rows


def write_evaluation(
    output_dir: Path,
    result: dict[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    """Write both the aggregate result and every decision at one boundary."""

    if output_dir.exists():
        raise PatentCandidateError(f"refusing to overwrite candidate output: {output_dir}")
    output_dir.mkdir(parents=True)
    with (output_dir / "decisions.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=DECISION_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixtures", type=Path)
    parser.add_argument("labels", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--challenge", action="append", default=[], type=Path)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    result, rows = evaluate_candidate(
        args.fixtures,
        args.labels,
        args.manifest,
        challenge_paths=args.challenge,
    )
    write_evaluation(args.output, result, rows)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
