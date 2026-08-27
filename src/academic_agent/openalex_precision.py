"""Conjunctive academic-candidate gate for production-disconnected studies.

The existing evidence-gap quarantine uses a broad additive relevance score.
That score is useful for recall, but one completed human review showed that
unrelated papers can accumulate several generic topic words.  This module
implements the separately pre-registered precision-v2 candidate: trusted
concept groups must be supported together, otherwise the result is ABSTAIN.

Nothing in the production worker imports this module.  In particular, an
ABSTAIN decision is not an assertion that a source is irrelevant and must not
be translated into a production DROP without an independent unseen study.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from academic_agent.tools.evidence_search import ToolEvidenceCandidate


PrecisionAction = Literal["ACCEPT", "ABSTAIN"]
AbstentionReason = Literal[
    "missing_required_groups",
    "insufficient_supporting_groups",
    "missing_title_anchor",
]

_TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
_GROUP_ID_PATTERN = r"^[a-z][a-z0-9_]{2,63}$"


def _tokens(value: str) -> tuple[str, ...]:
    """Return stable Unicode token boundaries without stemming or expansion.

    NFKC makes compatibility forms deterministic, while complete-token
    matching prevents a short frozen phrase such as ``pet`` from matching
    ``carpet``.  Stemming and semantic similarity are deliberately absent:
    they would add an unmeasured source of false acceptance to a precision
    gate whose safe fallback is abstention.
    """

    normalized = unicodedata.normalize("NFKC", value).casefold()
    return tuple(_TOKEN_PATTERN.findall(normalized))


def _phrase_key(value: str) -> str:
    tokens = _tokens(value)
    if not tokens:
        raise ValueError("concept phrase must contain at least one token")
    if len(tokens) > 8:
        raise ValueError("concept phrase may contain at most eight tokens")
    return " ".join(tokens)


def _contains_phrase(tokens: tuple[str, ...], phrase: tuple[str, ...]) -> bool:
    if len(phrase) > len(tokens):
        return False
    width = len(phrase)
    return any(tokens[index : index + width] == phrase for index in range(len(tokens) - width + 1))


class AcademicConceptGroup(BaseModel):
    """Alternative phrases that all represent one independent concept."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str = Field(pattern=_GROUP_ID_PATTERN)
    phrases: tuple[str, ...] = Field(min_length=1, max_length=8)

    @field_validator("phrases")
    @classmethod
    def _validate_phrases(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_phrase_key(value) for value in values)
        if len(normalized) != len(set(normalized)):
            raise ValueError("concept group contains duplicate normalized phrases")
        return values

    def normalized_phrases(self) -> tuple[tuple[str, ...], ...]:
        """Expose validated phrase tokens in their frozen declaration order."""

        return tuple(_tokens(value) for value in self.phrases)


class AcademicPrecisionProfile(BaseModel):
    """Trusted concept contract for one experimental academic query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    required_groups: tuple[AcademicConceptGroup, ...] = Field(
        min_length=2,
        max_length=6,
    )
    supporting_groups: tuple[AcademicConceptGroup, ...] = Field(
        min_length=2,
        max_length=8,
    )
    minimum_supporting_groups: int = Field(ge=1, le=8)
    minimum_title_required_groups: int = Field(ge=1, le=6)

    @model_validator(mode="after")
    def _validate_independent_groups(self) -> "AcademicPrecisionProfile":
        groups = (*self.required_groups, *self.supporting_groups)
        ids = tuple(group.group_id for group in groups)
        if len(ids) != len(set(ids)):
            raise ValueError("concept group IDs must be unique")

        # One exact phrase cannot satisfy two supposedly independent groups.
        # This check caught a defect in the first frozen fixture before any
        # candidate output existed; retaining it here prevents recurrence.
        phrase_owners: dict[str, str] = {}
        for group in groups:
            for phrase in group.phrases:
                key = _phrase_key(phrase)
                previous = phrase_owners.get(key)
                if previous is not None:
                    raise ValueError(
                        "normalized phrase appears in multiple concept groups: "
                        f"{key!r} in {previous!r} and {group.group_id!r}"
                    )
                phrase_owners[key] = group.group_id

        if self.minimum_supporting_groups > len(self.supporting_groups):
            raise ValueError(
                "minimum_supporting_groups exceeds the supporting-group count"
            )
        if self.minimum_title_required_groups > len(self.required_groups):
            raise ValueError(
                "minimum_title_required_groups exceeds the required-group count"
            )
        return self

    def sha256(self) -> str:
        """Return a stable identity for the complete trusted profile."""

        payload = self.model_dump_json(exclude_none=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AcademicPrecisionDecision(BaseModel):
    """One label-blind decision with every concept-group feature exposed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: PrecisionAction
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    matched_required_groups: tuple[str, ...]
    missing_required_groups: tuple[str, ...]
    matched_supporting_groups: tuple[str, ...]
    title_required_groups: tuple[str, ...]
    abstention_reasons: tuple[AbstentionReason, ...]

    @model_validator(mode="after")
    def _validate_action_shape(self) -> "AcademicPrecisionDecision":
        if self.action == "ACCEPT":
            if self.missing_required_groups or self.abstention_reasons:
                raise ValueError("ACCEPT cannot carry missing groups or reasons")
        elif not self.abstention_reasons:
            raise ValueError("ABSTAIN requires at least one explicit reason")
        return self


def _group_matches(
    group: AcademicConceptGroup,
    *fields: tuple[str, ...],
) -> bool:
    return any(
        _contains_phrase(field, phrase)
        for phrase in group.normalized_phrases()
        for field in fields
    )


def _candidate_sha256(candidate: ToolEvidenceCandidate) -> str:
    payload = candidate.model_dump_json(exclude_none=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def evaluate_academic_candidate(
    candidate: ToolEvidenceCandidate,
    profile: AcademicPrecisionProfile,
) -> AcademicPrecisionDecision:
    """Apply the frozen ACCEPT/ABSTAIN rule without receiving a human label."""

    title_tokens = _tokens(candidate.title)
    summary_tokens = _tokens(candidate.evidence_summary)

    matched_required = tuple(
        group.group_id
        for group in profile.required_groups
        if _group_matches(group, title_tokens, summary_tokens)
    )
    missing_required = tuple(
        group.group_id
        for group in profile.required_groups
        if group.group_id not in matched_required
    )
    matched_supporting = tuple(
        group.group_id
        for group in profile.supporting_groups
        if _group_matches(group, title_tokens, summary_tokens)
    )
    title_required = tuple(
        group.group_id
        for group in profile.required_groups
        if _group_matches(group, title_tokens)
    )

    reasons: list[AbstentionReason] = []
    if missing_required:
        reasons.append("missing_required_groups")
    if len(matched_supporting) < profile.minimum_supporting_groups:
        reasons.append("insufficient_supporting_groups")
    if len(title_required) < profile.minimum_title_required_groups:
        reasons.append("missing_title_anchor")

    return AcademicPrecisionDecision(
        action="ABSTAIN" if reasons else "ACCEPT",
        candidate_sha256=_candidate_sha256(candidate),
        profile_sha256=profile.sha256(),
        matched_required_groups=matched_required,
        missing_required_groups=missing_required,
        matched_supporting_groups=matched_supporting,
        title_required_groups=title_required,
        abstention_reasons=tuple(reasons),
    )
