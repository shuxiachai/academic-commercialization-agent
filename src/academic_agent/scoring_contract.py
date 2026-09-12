"""Current scoring citation admission, separate from frozen experiment bytes.

The historical evidence module is a hash-locked dependency of paid experiments.
Do not re-lock those protocols merely to evolve production validation. The Crew
uses this wrapper; historical runners retain their original implementation.
This checks citation identity/category, not semantic support or calibration.
"""

from collections.abc import Callable
import json
from typing import Any

from crewai import TaskOutput
from pydantic import ValidationError

from academic_agent.evidence import (
    CommercializationScore, make_scoring_guardrail as legacy_scoring_guardrail,
    parse_citation_ids,
)
from academic_agent.market_cap_audit import capture_cap


def make_scoring_guardrail(
    weight_profile: str = "industrial", *,
    known_source_ids: frozenset[str] | None = None,
    market_task: Any = None, all_sources: list[Any] | None = None,
) -> Callable[[TaskOutput], tuple[bool, Any]]:
    """Reject mechanical citation defects before unchanged normalization/formula."""
    legacy = legacy_scoring_guardrail(
        weight_profile, known_source_ids=known_source_ids,
        market_task=market_task, all_sources=all_sources,
    )

    def validate_score(output: TaskOutput) -> tuple[bool, Any]:
        try:
            score = CommercializationScore.model_validate_json(output.raw)
        except (ValidationError, ValueError):
            # Preserve the existing schema-error contract, not a second repair.
            return legacy(output)
        errors: list[str] = []
        for field, prefix in (("patent_source_ids", "P"), ("market_source_ids", "M")):
            wrong = [sid for sid in getattr(score, field) if not sid.startswith(prefix)]
            if wrong:
                errors.append(f"{field} has wrong domain: {wrong}; use {prefix} sources.")
        for field in ("trl_source_ids", "mrl_source_ids"):
            ids = getattr(score, field)
            # A strict P prohibition rejected 2/30 baseline scorecards: process
            # patents supplemented academic/market manufacturing evidence. Require
            # an A/M anchor, but do not falsely accuse those mixed references.
            if ids and not any(sid.startswith(("A", "M")) for sid in ids):
                errors.append(f"{field} has wrong domain: include an A/M anchor.")
        if known_source_ids is not None:
            prose = " ".join([
                score.trl_rationale, score.mrl_rationale, score.patent_rationale,
                score.market_rationale, score.evidence_rationale, score.scoring_rationale,
                *score.key_risks, *score.key_opportunities,
            ])
            cited, malformed = parse_citation_ids(prose)
            phantom = sorted(set(cited) - known_source_ids)
            if phantom:
                errors.append(f"Score prose references IDs absent from context: {phantom}.")
            if malformed:
                errors.append(f"Score prose contains malformed citations: {malformed}.")
        if errors:
            return False, " ".join(errors)
        # Capture BEFORE the frozen factory mutates/normalizes TaskOutput.
        # Its schema dump discards model-invented audit fields; code overwrites
        # the receipt only after a successful validation. No second scoring
        # policy, retrospective estimate or extra provider request is involved.
        before = score.market_accessibility / 10
        ok, result = legacy(output)
        if ok:
            payload = json.loads(result.raw)
            payload["market_cap_audit"] = capture_cap(before, payload)
            result.raw = json.dumps(payload)
        return ok, result

    return validate_score
