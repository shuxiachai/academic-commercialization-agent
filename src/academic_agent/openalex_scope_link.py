"""Role-structured scope-link gate for disconnected OpenAlex studies.

Claim-scope v3 could accept a paper after its core process and application
matched together with generic performance evidence while a topic-defining
material or operating context was absent.  Moving the same numeric threshold
would not express that defect.  This candidate gives those differentiators an
independent role and requires source-text evidence that links one to an exact
core concept inside the same title or abstract sentence.

OpenAlex topics and keywords may still bridge at most one required concept,
but they can never satisfy a scope group, a supporting group, or a scope link.
The only negative action is ABSTAIN.  This module is experimental and is not
imported by the production worker.
"""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from academic_agent.openalex_claim_scope import (
    OpenAlexClaimScopeCandidate,
    ProviderAboutnessMatch,
)
from academic_agent.openalex_precision import _contains_phrase, _phrase_key, _tokens


ScopeLinkAction = Literal["ACCEPT", "ABSTAIN"]
ScopeLinkRole = Literal["required", "scope", "supporting"]
ScopeLinkField = Literal["title", "abstract_sentence"]
ScopeLinkAbstentionReason = Literal[
    "missing_required_groups",
    "insufficient_exact_required_groups",
    "too_many_provider_only_required_groups",
    "insufficient_scope_groups",
    "missing_scope_link",
    "insufficient_supporting_groups",
    "missing_title_anchor",
]

_GROUP_ID_PATTERN = r"^[a-z][a-z0-9_]{2,63}$"
# Sentence splitting is deliberately conservative.  A false split can only
# remove a link and produce ABSTAIN; joining clauses across punctuation would
# invent a relationship and is the higher-risk error for a precision gate.
_SENTENCE_BOUNDARY = re.compile(r"(?:[.!?;]+|\r?\n+)\s*")


def _validate_unique_phrases(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(_phrase_key(value) for value in values)
    if len(normalized) != len(set(normalized)):
        raise ValueError("concept group contains duplicate normalized phrases")
    return values


class ScopeLinkRequiredGroup(BaseModel):
    """Core concept with exact-text and bounded provider vocabularies."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str = Field(pattern=_GROUP_ID_PATTERN)
    text_phrases: tuple[str, ...] = Field(min_length=1, max_length=8)
    provider_terms: tuple[str, ...] = Field(min_length=1, max_length=8)

    _validate_text = field_validator("text_phrases")(_validate_unique_phrases)
    _validate_provider = field_validator("provider_terms")(
        _validate_unique_phrases
    )


class ScopeLinkTextGroup(BaseModel):
    """Scope or supporting concept that must occur in source text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str = Field(pattern=_GROUP_ID_PATTERN)
    text_phrases: tuple[str, ...] = Field(min_length=1, max_length=8)

    _validate_text = field_validator("text_phrases")(_validate_unique_phrases)


class OpenAlexScopeLinkProfile(BaseModel):
    """Frozen authorization rule for one role-structured academic query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    required_groups: tuple[ScopeLinkRequiredGroup, ...] = Field(
        min_length=2,
        max_length=4,
    )
    scope_groups: tuple[ScopeLinkTextGroup, ...] = Field(
        min_length=1,
        max_length=4,
    )
    supporting_groups: tuple[ScopeLinkTextGroup, ...] = Field(
        min_length=2,
        max_length=8,
    )
    minimum_exact_required_groups: int = Field(ge=1, le=4)
    maximum_provider_only_required_groups: int = Field(ge=0, le=1)
    minimum_scope_groups: int = Field(ge=1, le=4)
    minimum_linked_scope_groups: int = Field(ge=1, le=4)
    minimum_supporting_groups: int = Field(ge=1, le=8)
    minimum_title_anchor_groups: int = Field(ge=1, le=8)
    provider_score_floor: float = Field(
        ge=0.5,
        le=1.0,
        allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def _validate_independent_roles(self) -> "OpenAlexScopeLinkProfile":
        groups = (*self.required_groups, *self.scope_groups, *self.supporting_groups)
        group_ids = tuple(group.group_id for group in groups)
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("scope-link concept group IDs must be unique")

        # A single text hit must not count as two independent roles.  This is
        # especially important at the required/scope boundary: allowing the
        # same phrase on both sides would manufacture the relation v4 exists
        # to measure.
        text_owners: dict[str, str] = {}
        for group in groups:
            for phrase in group.text_phrases:
                key = _phrase_key(phrase)
                previous = text_owners.get(key)
                if previous is not None:
                    raise ValueError(
                        "normalized text phrase appears in multiple groups: "
                        f"{key!r} in {previous!r} and {group.group_id!r}"
                    )
                text_owners[key] = group.group_id

        provider_owners: dict[str, str] = {}
        for group in self.required_groups:
            for term in group.provider_terms:
                key = _phrase_key(term)
                previous = provider_owners.get(key)
                if previous is not None:
                    raise ValueError(
                        "normalized provider term appears in multiple required "
                        f"groups: {key!r} in {previous!r} and {group.group_id!r}"
                    )
                provider_owners[key] = group.group_id

        if self.minimum_exact_required_groups > len(self.required_groups):
            raise ValueError(
                "minimum_exact_required_groups exceeds the required-group count"
            )
        if self.maximum_provider_only_required_groups >= len(
            self.required_groups
        ):
            raise ValueError(
                "provider-only allowance must leave at least one required text group"
            )
        if self.minimum_scope_groups > len(self.scope_groups):
            raise ValueError("minimum_scope_groups exceeds the scope-group count")
        if self.minimum_linked_scope_groups > len(self.scope_groups):
            raise ValueError(
                "minimum_linked_scope_groups exceeds the scope-group count"
            )
        if self.minimum_supporting_groups > len(self.supporting_groups):
            raise ValueError(
                "minimum_supporting_groups exceeds the supporting-group count"
            )
        if self.minimum_title_anchor_groups > (
            len(self.required_groups) + len(self.scope_groups)
        ):
            raise ValueError(
                "minimum_title_anchor_groups exceeds required plus scope groups"
            )
        return self

    def sha256(self) -> str:
        """Bind all role assignments, phrases and thresholds."""

        payload = self.model_dump_json(exclude_none=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ScopeLinkGroupMatch(BaseModel):
    """Channel-level provenance for one concept role."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str
    role: ScopeLinkRole
    exact_title_phrases: tuple[str, ...]
    exact_summary_phrases: tuple[str, ...]
    provider_aboutness: tuple[ProviderAboutnessMatch, ...]

    @property
    def exact_text_matched(self) -> bool:
        return bool(self.exact_title_phrases or self.exact_summary_phrases)

    @property
    def matched(self) -> bool:
        return bool(self.exact_text_matched or self.provider_aboutness)


class ScopeLinkEvidence(BaseModel):
    """One inspectable same-segment relation between required and scope roles."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    required_group_id: str
    scope_group_id: str
    field: ScopeLinkField
    sentence_index: int = Field(ge=0)
    required_phrases: tuple[str, ...] = Field(min_length=1)
    scope_phrases: tuple[str, ...] = Field(min_length=1)


class OpenAlexScopeLinkDecision(BaseModel):
    """One label-blind ACCEPT/ABSTAIN decision with relation provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: ScopeLinkAction
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_matches: tuple[ScopeLinkGroupMatch, ...]
    scope_matches: tuple[ScopeLinkGroupMatch, ...]
    supporting_matches: tuple[ScopeLinkGroupMatch, ...]
    missing_required_groups: tuple[str, ...]
    exact_required_groups: tuple[str, ...]
    provider_only_required_groups: tuple[str, ...]
    exact_scope_groups: tuple[str, ...]
    linked_scope_groups: tuple[str, ...]
    title_anchor_groups: tuple[str, ...]
    link_evidence: tuple[ScopeLinkEvidence, ...]
    abstention_reasons: tuple[ScopeLinkAbstentionReason, ...]

    @model_validator(mode="after")
    def _validate_action_shape(self) -> "OpenAlexScopeLinkDecision":
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


def _provider_matches(
    group: ScopeLinkRequiredGroup,
    candidate: OpenAlexClaimScopeCandidate,
    *,
    provider_score_floor: float,
) -> tuple[ProviderAboutnessMatch, ...]:
    matches: list[ProviderAboutnessMatch] = []
    for signal in candidate.aboutness:
        if signal.score < provider_score_floor:
            continue
        signal_tokens = _tokens(signal.display_name)
        for term in group.provider_terms:
            if _contains_phrase(signal_tokens, _tokens(term)):
                matches.append(
                    ProviderAboutnessMatch(
                        kind=signal.kind,
                        provider_id=signal.provider_id,
                        display_name=signal.display_name,
                        score=signal.score,
                        matched_term=term,
                    )
                )
                break
    return tuple(matches)


def _group_match(
    group: ScopeLinkRequiredGroup | ScopeLinkTextGroup,
    role: ScopeLinkRole,
    candidate: OpenAlexClaimScopeCandidate,
    *,
    provider_score_floor: float,
) -> ScopeLinkGroupMatch:
    title_tokens = _tokens(candidate.evidence.title)
    summary_tokens = _tokens(candidate.evidence.evidence_summary)
    provider_aboutness: tuple[ProviderAboutnessMatch, ...] = ()
    if isinstance(group, ScopeLinkRequiredGroup):
        provider_aboutness = _provider_matches(
            group,
            candidate,
            provider_score_floor=provider_score_floor,
        )
    return ScopeLinkGroupMatch(
        group_id=group.group_id,
        role=role,
        exact_title_phrases=_matching_phrases(
            title_tokens,
            group.text_phrases,
        ),
        exact_summary_phrases=_matching_phrases(
            summary_tokens,
            group.text_phrases,
        ),
        provider_aboutness=provider_aboutness,
    )


def _summary_sentences(value: str) -> tuple[tuple[str, ...], ...]:
    """Tokenize non-empty abstract sentences in their original order."""

    return tuple(
        tokens
        for segment in _SENTENCE_BOUNDARY.split(value)
        if (tokens := _tokens(segment))
    )


def _link_evidence(
    candidate: OpenAlexClaimScopeCandidate,
    profile: OpenAlexScopeLinkProfile,
) -> tuple[ScopeLinkEvidence, ...]:
    segments: tuple[tuple[ScopeLinkField, int, tuple[str, ...]], ...] = (
        ("title", 0, _tokens(candidate.evidence.title)),
        *tuple(
            ("abstract_sentence", index, tokens)
            for index, tokens in enumerate(
                _summary_sentences(candidate.evidence.evidence_summary)
            )
        ),
    )
    links: list[ScopeLinkEvidence] = []
    for field, sentence_index, tokens in segments:
        required_hits = tuple(
            (group.group_id, _matching_phrases(tokens, group.text_phrases))
            for group in profile.required_groups
        )
        scope_hits = tuple(
            (group.group_id, _matching_phrases(tokens, group.text_phrases))
            for group in profile.scope_groups
        )
        for required_group_id, required_phrases in required_hits:
            if not required_phrases:
                continue
            for scope_group_id, scope_phrases in scope_hits:
                if not scope_phrases:
                    continue
                links.append(
                    ScopeLinkEvidence(
                        required_group_id=required_group_id,
                        scope_group_id=scope_group_id,
                        field=field,
                        sentence_index=sentence_index,
                        required_phrases=required_phrases,
                        scope_phrases=scope_phrases,
                    )
                )
    return tuple(links)


def evaluate_openalex_scope_link(
    candidate: OpenAlexClaimScopeCandidate,
    profile: OpenAlexScopeLinkProfile,
) -> OpenAlexScopeLinkDecision:
    """Apply the frozen role and same-segment contract without a label."""

    required = tuple(
        _group_match(
            group,
            "required",
            candidate,
            provider_score_floor=profile.provider_score_floor,
        )
        for group in profile.required_groups
    )
    scope = tuple(
        _group_match(
            group,
            "scope",
            candidate,
            provider_score_floor=profile.provider_score_floor,
        )
        for group in profile.scope_groups
    )
    supporting = tuple(
        _group_match(
            group,
            "supporting",
            candidate,
            provider_score_floor=profile.provider_score_floor,
        )
        for group in profile.supporting_groups
    )
    links = _link_evidence(candidate, profile)

    missing_required = tuple(item.group_id for item in required if not item.matched)
    exact_required = tuple(
        item.group_id for item in required if item.exact_text_matched
    )
    provider_only_required = tuple(
        item.group_id
        for item in required
        if item.provider_aboutness and not item.exact_text_matched
    )
    exact_scope = tuple(item.group_id for item in scope if item.exact_text_matched)
    linked_scope = tuple(
        item.group_id
        for item in scope
        if any(link.scope_group_id == item.group_id for link in links)
    )
    title_anchors = tuple(
        item.group_id
        for item in (*required, *scope)
        if item.exact_title_phrases
    )
    matched_supporting_count = sum(
        item.exact_text_matched for item in supporting
    )

    reasons: list[ScopeLinkAbstentionReason] = []
    if missing_required:
        reasons.append("missing_required_groups")
    if len(exact_required) < profile.minimum_exact_required_groups:
        reasons.append("insufficient_exact_required_groups")
    if len(provider_only_required) > profile.maximum_provider_only_required_groups:
        reasons.append("too_many_provider_only_required_groups")
    if len(exact_scope) < profile.minimum_scope_groups:
        reasons.append("insufficient_scope_groups")
    if len(linked_scope) < profile.minimum_linked_scope_groups:
        reasons.append("missing_scope_link")
    if matched_supporting_count < profile.minimum_supporting_groups:
        reasons.append("insufficient_supporting_groups")
    if len(title_anchors) < profile.minimum_title_anchor_groups:
        reasons.append("missing_title_anchor")

    return OpenAlexScopeLinkDecision(
        action="ABSTAIN" if reasons else "ACCEPT",
        candidate_sha256=candidate.sha256(),
        profile_sha256=profile.sha256(),
        required_matches=required,
        scope_matches=scope,
        supporting_matches=supporting,
        missing_required_groups=missing_required,
        exact_required_groups=exact_required,
        provider_only_required_groups=provider_only_required,
        exact_scope_groups=exact_scope,
        linked_scope_groups=linked_scope,
        title_anchor_groups=title_anchors,
        link_evidence=links,
        abstention_reasons=tuple(reasons),
    )
