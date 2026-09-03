"""Non-secret, durable input contract for one assessment run.

The API used to retain the topic in ``status.json`` but not the language,
weight-profile choice, or extracted paper contribution that shaped retrieval.
That was enough to display a failed run and not enough to reproduce it safely.
A recovery process must never guess those missing values: a guess can make an
old checkpoint appear applicable to a different request and skip a paid node.

``RunSpec`` is therefore persisted beside every new run before its worker is
started.  It deliberately contains the extracted paper contribution rather
than the uploaded PDF or a path into the short-lived upload store.  The
contribution is already an input to the pipeline, is bounded JSON, and lets a
child recovery run survive upload pruning without retaining another PDF copy.
Provider credentials are not model fields and Pydantic rejects any extra key,
so BYOK secrets cannot enter this artifact by accident.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


RUN_SPEC_FILENAME = ".run-spec.json"
RESUME_SNAPSHOT_DIRECTORY = ".resume-source"

AssessmentMode = Literal[
    "orientation",
    "decision_context_incomplete",
    "decision_support",
]
ThresholdProvenance = Literal[
    "not_established",
    "user_supplied_unapproved",
    "owner_approved",
]

_DECISION_CONTEXT_FIELDS = (
    "asset_description",
    "target_application",
    "decision_owner",
    "decision_type",
    "jurisdiction",
    "time_horizon",
    "constraints",
    "success_criteria",
    "success_criteria_authority",
)
_DECISION_CONTEXT_CORE_FIELDS = _DECISION_CONTEXT_FIELDS[:4]


class DecisionContext(BaseModel):
    """Optional actor-and-gate context for one commercialization decision.

    A research topic is sufficient for evidence retrieval, but not for an
    actor-specific recommendation. Keeping this as a separate bounded model
    lets the API accept a useful orientation run without pretending that an
    omitted owner, asset, or decision was checked and found unnecessary.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_description: str | None = Field(default=None, max_length=500)
    target_application: str | None = Field(default=None, max_length=500)
    decision_owner: str | None = Field(default=None, max_length=300)
    decision_type: str | None = Field(default=None, max_length=300)
    jurisdiction: str | None = Field(default=None, max_length=300)
    time_horizon: str | None = Field(default=None, max_length=300)
    constraints: str | None = Field(default=None, max_length=1200)

    success_criteria: str | None = Field(default=None, max_length=1200)
    success_criteria_authority: Literal["owner_approved"] | None = None

    @field_validator(*_DECISION_CONTEXT_FIELDS, mode="before")
    @classmethod
    def _normalise_optional_text(cls, value: object) -> object:
        """Collapse layout-only whitespace before length and identity checks."""

        if not isinstance(value, str):
            return value
        normalized = " ".join(value.split())
        return normalized or None

    @model_validator(mode="after")
    def _approval_requires_criteria(self) -> "DecisionContext":
        """Do not let a bare checkbox manufacture an approved threshold.

        The authority flag is deliberately not a general confidence control.
        It describes only the success criteria supplied in the same immutable
        request, so persisting it without those criteria would create an
        approval claim with no object.
        """

        if self.success_criteria_authority and self.success_criteria is None:
            raise ValueError(
                "success_criteria_authority requires supplied success_criteria"
            )
        return self

    @property
    def provided_fields(self) -> tuple[str, ...]:
        return tuple(
            name for name in _DECISION_CONTEXT_FIELDS if getattr(self, name) is not None
        )

    @property
    def missing_core_fields(self) -> tuple[str, ...]:
        return tuple(
            name
            for name in _DECISION_CONTEXT_CORE_FIELDS
            if getattr(self, name) is None
        )

    @property
    def assessment_mode(self) -> AssessmentMode:
        if not self.provided_fields:
            return "orientation"
        if self.missing_core_fields:
            return "decision_context_incomplete"
        return "decision_support"

    @property
    def threshold_provenance(self) -> ThresholdProvenance:
        if self.success_criteria is None:
            return "not_established"
        if self.success_criteria_authority == "owner_approved":
            return "owner_approved"
        return "user_supplied_unapproved"

    def gate_snapshot(self) -> dict[str, object]:
        """Expose coverage and authority, not duplicated user prose."""

        mode = self.assessment_mode
        return {
            "status": "checked",
            "mode": mode,
            "provided_fields": list(self.provided_fields),
            "missing_core_fields": list(self.missing_core_fields),
            "go_no_go_allowed": mode == "decision_support",
            "threshold_provenance": {
                "status": self.threshold_provenance,
                "criteria_supplied": self.success_criteria is not None,
                "owner_approval_declared": (
                    self.success_criteria_authority == "owner_approved"
                ),
            },
        }

    def crew_inputs(self) -> dict[str, str]:
        """Build the exact untrusted input block interpolated into two tasks."""

        supplied = self.model_dump(mode="json", exclude_none=True)
        mode = self.assessment_mode
        if mode == "orientation":
            guidance = (
                "ORIENTATION MODE. No actor-specific decision context was supplied. "
                "Produce an evidence-linked orientation brief. Explicitly state that "
                "GO/NO_GO is not assessed, and write 'not established' rather than "
                "inventing an owner, budget, timeline, jurisdiction, or threshold."
            )
        elif mode == "decision_context_incomplete":
            missing = ", ".join(self.missing_core_fields)
            guidance = (
                "INCOMPLETE DECISION CONTEXT. Use the supplied context, but explicitly "
                "state that GO/NO_GO is not assessed because these core fields are "
                f"missing: {missing}. Never infer the missing values from the topic."
            )
        else:
            guidance = (
                "DECISION SUPPORT MODE. Address the supplied actor-specific decision. "
                "A GO, NO_GO, or DEFER conclusion is permitted, but every gate must be "
                "bounded by retrieved evidence; write 'not established' for unsupported "
                "cost, time, jurisdiction, or threshold details."
            )
        if self.threshold_provenance == "owner_approved":
            threshold_guidance = (
                "The supplied success criteria were explicitly declared "
                "owner-approved. Preserve their meaning exactly and identify "
                "them as owner-approved; do not add or silently tighten them."
            )
        elif self.threshold_provenance == "user_supplied_unapproved":
            threshold_guidance = (
                "Success criteria were supplied without an owner-approval "
                "declaration. Identify them as user-supplied and pending "
                "approval; never call them approved."
            )
        else:
            threshold_guidance = (
                "No success criteria were supplied. Any threshold introduced "
                "by the report must be explicitly labelled an analyst proposal "
                "requiring owner confirmation, never a mandatory gate."
            )
        guidance = (
            f"{guidance} {threshold_guidance} A cited external benchmark is "
            "evidence, not proof that a decision owner approved it as a gate."
        )
        return {
            "assessment_mode": mode,
            "decision_context_json": json.dumps(
                supplied,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            "decision_mode_guidance": guidance,
        }


class RunSpec(BaseModel):
    """Frozen request values needed to repeat or resume a run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Version 1 remains readable so old failed runs can still be inspected and
    # resumed as orientation runs. Version 2 introduced decision context;
    # version 3 distinguishes user-supplied success criteria from an explicit
    # owner-approval declaration, so recovery cannot silently change authority.
    schema_version: Literal[1, 2, 3] = 3
    topic: str = Field(min_length=1, max_length=300)
    language: str | None = Field(default=None, max_length=100)
    weight_profile: str | None = Field(default=None, max_length=100)
    paper_contribution: dict[str, Any] | None = None
    decision_context: DecisionContext | None = None

    @field_validator("topic")
    @classmethod
    def _strip_topic(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("topic must contain at least one non-space character")
        return stripped

    @field_validator("language", "weight_profile")
    @classmethod
    def _normalise_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("decision_context")
    @classmethod
    def _normalise_empty_decision_context(
        cls, value: DecisionContext | None,
    ) -> DecisionContext | None:
        # `{}` and an omitted object mean the same thing. Persisting one but not
        # the other would create two checkpoint identities for orientation mode.
        if value is not None and not value.provided_fields:
            return None
        return value

    @property
    def assessment_mode(self) -> AssessmentMode:
        return (self.decision_context or DecisionContext()).assessment_mode

    def decision_gate(self) -> dict[str, object]:
        return (self.decision_context or DecisionContext()).gate_snapshot()

    def decision_crew_inputs(self) -> dict[str, str]:
        return (self.decision_context or DecisionContext()).crew_inputs()

    def save(self, run_directory: Path | str) -> Path:
        """Atomically publish the spec before a worker can observe the run.

        This is not a cache write: losing it means a failed run cannot be
        resumed safely.  A same-directory replace keeps readers from seeing a
        truncated JSON document if the host dies during publication.
        """

        directory = Path(run_directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / RUN_SPEC_FILENAME
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        payload = (self.model_dump_json(indent=2) + "\n").encode("utf-8")
        try:
            with temporary.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                # The committed spec, or the original publication error, is
                # more useful than a cleanup failure for an unreferenced temp.
                pass
        return path

    @classmethod
    def load(cls, run_directory: Path | str) -> "RunSpec":
        """Load and strictly validate a previously persisted run contract."""

        path = Path(run_directory) / RUN_SPEC_FILENAME
        return cls.model_validate_json(path.read_bytes())
