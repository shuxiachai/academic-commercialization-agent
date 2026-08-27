"""Provider-assisted claim-scope gate for disconnected OpenAlex studies.

Precision v2 required every concept to occur as an exact phrase in a title or
abstract.  Its first unseen run exposed a mechanical recall limit, but the
returned rows were not human-labelled, so simply weakening that conjunction
would be tuning against unknown truth.  This candidate adds a second,
inspectable channel: OpenAlex topic and keyword labels may bridge at most one
required concept while at least one required concept must still be supported
by source text and anchored in the title.

The provider labels are therefore evidence about document *aboutness*, not a
replacement for the paper's text and not proof that a claim is true.  Every
match records its channel and provider score.  The only safe negative action is
ABSTAIN; this module neither drops sources nor enters the production worker.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from academic_agent.openalex_precision import _contains_phrase, _phrase_key, _tokens
from academic_agent.tools.evidence_search import ToolEvidenceCandidate


ClaimScopeAction = Literal["ACCEPT", "ABSTAIN"]
AboutnessKind = Literal["topic", "keyword"]
ClaimScopeAbstentionReason = Literal[
    "missing_required_groups",
    "insufficient_supporting_groups",
    "insufficient_exact_required_groups",
    "missing_title_anchor",
    "too_many_provider_only_required_groups",
]

_GROUP_ID_PATTERN = r"^[a-z][a-z0-9_]{2,63}$"


class OpenAlexAboutnessSignal(BaseModel):
    """One source-native OpenAlex topic or keyword assignment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: AboutnessKind
    provider_id: str = Field(min_length=10, max_length=300)
    display_name: str = Field(min_length=2, max_length=300)
    score: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)


class OpenAlexClaimScopeCandidate(BaseModel):
    """Evidence candidate plus the exact provider metadata used by the gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence: ToolEvidenceCandidate
    aboutness: tuple[OpenAlexAboutnessSignal, ...] = Field(max_length=100)

    @model_validator(mode="after")
    def _validate_unique_signals(self) -> "OpenAlexClaimScopeCandidate":
        identities = tuple((item.kind, item.provider_id) for item in self.aboutness)
        if len(identities) != len(set(identities)):
            raise ValueError("OpenAlex aboutness signals must be unique by kind and ID")
        return self

    def sha256(self) -> str:
        """Bind the decision to evidence text and provider aboutness metadata."""

        payload = self.model_dump_json(exclude_none=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ClaimScopeConceptGroup(BaseModel):
    """One independent concept with text and provider-label vocabularies."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str = Field(pattern=_GROUP_ID_PATTERN)
    text_phrases: tuple[str, ...] = Field(min_length=1, max_length=8)
    provider_terms: tuple[str, ...] = Field(min_length=1, max_length=8)

    @field_validator("text_phrases", "provider_terms")
    @classmethod
    def _validate_phrases(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_phrase_key(value) for value in values)
        if len(normalized) != len(set(normalized)):
            raise ValueError("concept group contains duplicate normalized phrases")
        return values


class OpenAlexClaimScopeProfile(BaseModel):
    """Frozen, explainable authorization rule for one academic query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    required_groups: tuple[ClaimScopeConceptGroup, ...] = Field(
        min_length=2,
        max_length=4,
    )
    supporting_groups: tuple[ClaimScopeConceptGroup, ...] = Field(
        min_length=2,
        max_length=8,
    )
    minimum_supporting_groups: int = Field(ge=1, le=8)
    minimum_exact_required_groups: int = Field(ge=1, le=4)
    minimum_title_required_groups: int = Field(ge=1, le=4)
    maximum_provider_only_required_groups: int = Field(ge=0, le=1)
    provider_score_floor: float = Field(ge=0.5, le=1.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _validate_independent_groups(self) -> "OpenAlexClaimScopeProfile":
        groups = (*self.required_groups, *self.supporting_groups)
        group_ids = tuple(group.group_id for group in groups)
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("claim-scope concept group IDs must be unique")

        # Cross-group duplicates let one lexical hit masquerade as independent
        # scope coverage.  Text and provider vocabularies are checked
        # separately because the same phrase may legitimately be the text and
        # provider representation of one concept.
        for field_name in ("text_phrases", "provider_terms"):
            owners: dict[str, str] = {}
            for group in groups:
                for phrase in getattr(group, field_name):
                    key = _phrase_key(phrase)
                    previous = owners.get(key)
                    if previous is not None:
                        raise ValueError(
                            f"normalized {field_name} phrase appears in multiple "
                            f"groups: {key!r} in {previous!r} and {group.group_id!r}"
                        )
                    owners[key] = group.group_id

        if self.minimum_supporting_groups > len(self.supporting_groups):
            raise ValueError(
                "minimum_supporting_groups exceeds the supporting-group count"
            )
        if self.minimum_exact_required_groups > len(self.required_groups):
            raise ValueError(
                "minimum_exact_required_groups exceeds the required-group count"
            )
        if self.minimum_title_required_groups > len(self.required_groups):
            raise ValueError(
                "minimum_title_required_groups exceeds the required-group count"
            )
        if self.maximum_provider_only_required_groups >= len(self.required_groups):
            raise ValueError(
                "provider-only allowance must leave at least one required text group"
            )
        return self

    def sha256(self) -> str:
        payload = self.model_dump_json(exclude_none=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ProviderAboutnessMatch(BaseModel):
    """The exact provider signal and frozen term that produced one match."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: AboutnessKind
    provider_id: str
    display_name: str
    score: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    matched_term: str


class ClaimScopeConceptMatch(BaseModel):
    """Channel-level provenance for one concept group."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str
    exact_title_phrases: tuple[str, ...]
    exact_summary_phrases: tuple[str, ...]
    provider_aboutness: tuple[ProviderAboutnessMatch, ...]

    @property
    def matched(self) -> bool:
        return bool(
            self.exact_title_phrases
            or self.exact_summary_phrases
            or self.provider_aboutness
        )

    @property
    def exact_text_matched(self) -> bool:
        return bool(self.exact_title_phrases or self.exact_summary_phrases)


class OpenAlexClaimScopeDecision(BaseModel):
    """One label-blind ACCEPT/ABSTAIN decision with auditable provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: ClaimScopeAction
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_matches: tuple[ClaimScopeConceptMatch, ...]
    supporting_matches: tuple[ClaimScopeConceptMatch, ...]
    missing_required_groups: tuple[str, ...]
    exact_required_groups: tuple[str, ...]
    title_required_groups: tuple[str, ...]
    provider_only_required_groups: tuple[str, ...]
    abstention_reasons: tuple[ClaimScopeAbstentionReason, ...]

    @model_validator(mode="after")
    def _validate_action_shape(self) -> "OpenAlexClaimScopeDecision":
        if self.action == "ACCEPT":
            if self.missing_required_groups or self.abstention_reasons:
                raise ValueError("ACCEPT cannot carry missing groups or reasons")
        elif not self.abstention_reasons:
            raise ValueError("ABSTAIN requires at least one explicit reason")
        return self


def _matching_phrases(
    field_tokens: tuple[str, ...],
    phrases: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        phrase
        for phrase in phrases
        if _contains_phrase(field_tokens, _tokens(phrase))
    )


def _group_match(
    group: ClaimScopeConceptGroup,
    candidate: OpenAlexClaimScopeCandidate,
    *,
    provider_score_floor: float,
) -> ClaimScopeConceptMatch:
    title_tokens = _tokens(candidate.evidence.title)
    summary_tokens = _tokens(candidate.evidence.evidence_summary)
    provider_matches: list[ProviderAboutnessMatch] = []
    for signal in candidate.aboutness:
        if signal.score < provider_score_floor:
            continue
        signal_tokens = _tokens(signal.display_name)
        for term in group.provider_terms:
            if _contains_phrase(signal_tokens, _tokens(term)):
                provider_matches.append(
                    ProviderAboutnessMatch(
                        kind=signal.kind,
                        provider_id=signal.provider_id,
                        display_name=signal.display_name,
                        score=signal.score,
                        matched_term=term,
                    )
                )
                break
    return ClaimScopeConceptMatch(
        group_id=group.group_id,
        exact_title_phrases=_matching_phrases(title_tokens, group.text_phrases),
        exact_summary_phrases=_matching_phrases(summary_tokens, group.text_phrases),
        provider_aboutness=tuple(provider_matches),
    )


def evaluate_openalex_claim_scope(
    candidate: OpenAlexClaimScopeCandidate,
    profile: OpenAlexClaimScopeProfile,
) -> OpenAlexClaimScopeDecision:
    """Apply the frozen provider-assisted rule without a relevance label."""

    required = tuple(
        _group_match(
            group,
            candidate,
            provider_score_floor=profile.provider_score_floor,
        )
        for group in profile.required_groups
    )
    supporting = tuple(
        _group_match(
            group,
            candidate,
            provider_score_floor=profile.provider_score_floor,
        )
        for group in profile.supporting_groups
    )
    missing_required = tuple(item.group_id for item in required if not item.matched)
    exact_required = tuple(
        item.group_id for item in required if item.exact_text_matched
    )
    title_required = tuple(
        item.group_id for item in required if item.exact_title_phrases
    )
    provider_only_required = tuple(
        item.group_id
        for item in required
        if item.provider_aboutness and not item.exact_text_matched
    )
    matched_supporting_count = sum(item.matched for item in supporting)

    reasons: list[ClaimScopeAbstentionReason] = []
    if missing_required:
        reasons.append("missing_required_groups")
    if matched_supporting_count < profile.minimum_supporting_groups:
        reasons.append("insufficient_supporting_groups")
    if len(exact_required) < profile.minimum_exact_required_groups:
        reasons.append("insufficient_exact_required_groups")
    if len(title_required) < profile.minimum_title_required_groups:
        reasons.append("missing_title_anchor")
    if len(provider_only_required) > profile.maximum_provider_only_required_groups:
        reasons.append("too_many_provider_only_required_groups")

    return OpenAlexClaimScopeDecision(
        action="ABSTAIN" if reasons else "ACCEPT",
        candidate_sha256=candidate.sha256(),
        profile_sha256=profile.sha256(),
        required_matches=required,
        supporting_matches=supporting,
        missing_required_groups=missing_required,
        exact_required_groups=exact_required,
        title_required_groups=title_required,
        provider_only_required_groups=provider_only_required,
        abstention_reasons=tuple(reasons),
    )
