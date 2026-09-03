"""Request and response models for the HTTP API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from academic_agent.run_spec import AssessmentMode, DecisionContext

#: "unknown" means the status file could not be read, not that the run
#: failed. It is deliberately not terminal: a client should retry rather than
#: tell the user their run died, because it may well have finished.
RunState = Literal["running", "completed", "failed", "cancelled", "timeout",
                   "unknown"]

BYOK_PROVIDERS = ("deepseek", "qwen", "openai", "anthropic")


class RunRequest(BaseModel):
    """Body for POST /api/runs."""

    topic: str = Field(min_length=3, max_length=300, description="Research topic to assess")
    language: str | None = Field(
        default=None,
        description="Force report language (e.g. 'Simplified Chinese'); auto-detected when omitted",
    )
    weight_profile: str | None = Field(
        default=None,
        description="Force scoring profile (industrial | biomedical | material_science "
                    "| clean_tech | software_ai); auto-detected when omitted",
    )
    paper_id: str | None = Field(
        default=None,
        description="Id returned by POST /api/papers, to anchor the run on an "
                    "uploaded paper rather than on the topic alone",
    )
    decision_context: DecisionContext | None = Field(
        default=None,
        description="Optional actor, asset, and decision gate. Omission produces "
                    "an orientation brief rather than actor-specific advice.",
    )

    # Bring-your-own-key: an alternative to the access code for a visitor who
    # is not the deployment owner. All three or none — a run either runs on
    # the deployment's own billed keys (gated by the access code) or entirely
    # on the requester's own, never a mix of the two.
    llm_provider: str | None = Field(
        default=None,
        description=f"Bring-your-own-key provider: one of {BYOK_PROVIDERS}. "
                    "Required together with llm_api_key and serper_api_key.",
    )
    llm_api_key: str | None = Field(default=None, description="Bring-your-own LLM API key.")
    serper_api_key: str | None = Field(default=None, description="Bring-your-own Serper API key.")

    @field_validator("topic", mode="before")
    @classmethod
    def _normalise_topic_before_length_check(cls, value: object) -> object:
        """Make the public request and durable RunSpec observe one topic.

        Browsers trim this field, but direct API clients bypass that seam and
        Pydantic's ``min_length`` counts whitespace as ordinary characters.
        Letting ``"   "`` through used to defer the rejection to RunSpec and
        turn malformed input into an internal 500.  Only strings are touched
        here so Pydantic still owns type and length errors.
        """
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _byok_is_all_or_nothing(self) -> "RunRequest":
        fields = (self.llm_provider, self.llm_api_key, self.serper_api_key)
        if any(fields) and not all(fields):
            raise ValueError(
                "llm_provider, llm_api_key and serper_api_key must be provided together, "
                "or all omitted to use the deployment's own keys."
            )
        if self.llm_provider is not None and self.llm_provider not in BYOK_PROVIDERS:
            raise ValueError(f"llm_provider must be one of {BYOK_PROVIDERS}.")
        return self

    @property
    def assessment_mode(self) -> AssessmentMode:
        return (self.decision_context or DecisionContext()).assessment_mode

    @property
    def byok(self) -> bool:
        return self.llm_provider is not None

class ResumeRunRequest(BaseModel):
    """Fresh credentials for POST /api/runs/{run_id}/resume."""

    # Recovery never persists credentials from the source run. A BYOK caller
    # must supply a complete fresh set, while an access-code caller leaves the
    # body empty and uses the deployment's configured providers.
    llm_provider: str | None = Field(
        default=None,
        description=f"Bring-your-own-key provider: one of {BYOK_PROVIDERS}.",
    )
    llm_api_key: str | None = Field(default=None, description="Fresh LLM API key.")
    serper_api_key: str | None = Field(default=None, description="Fresh Serper API key.")

    @model_validator(mode="after")
    def _byok_is_all_or_nothing(self) -> "ResumeRunRequest":
        fields = (self.llm_provider, self.llm_api_key, self.serper_api_key)
        if any(fields) and not all(fields):
            raise ValueError(
                "llm_provider, llm_api_key and serper_api_key must be provided together, "
                "or all omitted to use the deployment's own keys."
            )
        if self.llm_provider is not None and self.llm_provider not in BYOK_PROVIDERS:
            raise ValueError(f"llm_provider must be one of {BYOK_PROVIDERS}.")
        return self

    @property
    def byok(self) -> bool:
        return self.llm_provider is not None



class PaperExtraction(BaseModel):
    """Structured contribution extracted from an uploaded PDF.

    Mirrors PaperContribution, plus the id needed to reference it when
    starting a run. The fields are editable in the client: extraction is a
    model's reading of the paper, and the person who uploaded it is better
    placed to correct the topic than the model is.
    """

    paper_id: str
    title: str
    authors: str = ""
    doi: str | None = None
    url: str | None = None
    core_contribution: str
    application_domain: str
    key_metrics: list[str] = Field(default_factory=list)
    delta_from_prior: str = ""
    commercialization_topic: str
    search_keywords: list[str] = Field(default_factory=list)
    abstract_excerpt: str = ""


class StepEvent(BaseModel):
    """One line of steps.jsonl, surfaced for live progress."""

    ts: float | None = None
    type: str = ""
    agent_idx: int | None = None
    agent: str = ""
    thought: str = ""
    tool: str = ""


class RunProgress(BaseModel):
    """Everything a client needs to render live progress in one request.

    Combines status.json with the tail of steps.jsonl so a polling client
    makes one call per tick rather than three.
    """

    run_id: str
    state: RunState
    stage: str = ""
    # Carried here so a client that opens a run from a list has a title on
    # the first response rather than a placeholder until it guesses one.
    topic: str = ""
    pipeline_revision: str | None = Field(
        default=None,
        description="Immutable code identity recorded by the worker that executed "
                    "this run. None means the run predates revision persistence or "
                    "failed before identity could be recorded; it is never "
                    "backfilled from the current server deployment.",
    )
    done: bool = False
    error: str | None = None
    elapsed_seconds: int | None = None
    source_counts: dict[str, int] | None = None
    evidence_incomplete: bool = Field(
        default=False,
        description="Run finished but its per-agent evidence files could not be "
                    "written; the report stands, the audit trail behind its "
                    "citations does not.",
    )
    failed_domains: list[str] = Field(
        default_factory=list,
        description="Evidence domains whose retrieval backend failed, so the "
                    "assessment was produced without them. Distinct from a "
                    "domain that searched successfully and found nothing.",
    )
    usage: dict | None = Field(
        default=None,
        description="Tokens and estimated cost for the run, per agent and in "
                    "total. Absent for runs that predate cost accounting and "
                    "for runs that failed before the crew started.",
    )
    claim_grounding: dict | None = Field(
        default=None,
        description="How many of the run's quantitative claims could be "
                    "checked against the text of the sources they cite, how "
                    "many cited a figure absent from it, and how many could "
                    "not be checked at all. The last number bounds what the "
                    "other two mean. Status distinguishes completed, partial, "
                    "not-applicable, unavailable, and failed checks; None is "
                    "reserved for runs created before status was recorded.",
    )
    authority_coverage: dict | None = Field(
        default=None,
        description="Required regulator and clinical-registry coverage for applicable "
                    "biomedical topics. Incomplete is a review warning, not a failed run.",
    )
    component_coverage: dict | None = Field(
        default=None,
        description="Coverage of independently searchable components in a combined "
                    "system. Incomplete is advisory and never proves absence.",
    )
    evidence_gap_shadow: dict | None = Field(
        default=None,
        description="Zero-call phase-1 evidence-gap eligibility audit. States "
                    "distinguish disabled, checked, and failed evaluation; no "
                    "supplementary search is executed.",
    )
    decision_gate: dict | None = Field(
        default=None,
        description="Code-derived orientation, incomplete-context, or decision-support "
                    "state. None means the run predates this gate; it is not a pass.",
    )
    report_audit: dict | None = Field(
        default=None,
        description="Non-blocking threshold-provenance and citation material-scope "
                    "audit. None means the run predates the audit, not that it passed.",
    )
    quality_review: dict | None = Field(
        default=None,
        description="Whether the independent reviewer completed. 'partial' means "
                    "one or more exact targets were absent and those validated "
                    "draft passages were preserved; 'fallback' means the whole "
                    "review was unavailable rather than presenting it as a pass.",
    )
    consistency: dict | None = Field(
        default=None,
        description="Disagreements between the report's own recommendation and "
                    "the scorecard shipped beside it. Nothing else in the "
                    "pipeline compares the two.",
    )
    observability: dict | None = Field(
        default=None,
        description="OpenTelemetry setup and bounded-flush state for this "
                    "run. 'active' means configured, while delivery remains "
                    "an attempt because OTLP provides no persistence "
                    "acknowledgement. Absent for runs created before tracing.",
    )
    checkpointing: dict | None = Field(
        default=None,
        description="Durable node-output persistence state. 'degraded' means the "
                    "assessment may still finish but a later process cannot safely "
                    "reuse every validated node.",
    )
    recovery: dict | None = Field(
        default=None,
        description="Whether recovery was requested, which validated nodes were "
                    "reused, and the first node that still had to execute.",
    )
    output_language: str = "English"
    steps: list[StepEvent] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)


class RunAccepted(BaseModel):
    """Response for a successfully queued run."""

    run_id: str
    state: RunState
    topic: str
    assessment_mode: AssessmentMode
    resumed_from: str | None = None


class RunStatus(BaseModel):
    """Current state of a run, read from its status.json."""

    run_id: str
    state: RunState
    stage: str = ""
    topic: str = ""
    pipeline_revision: str | None = Field(
        default=None,
        description="Immutable code identity recorded by the worker that executed "
                    "this run. None means the run predates revision persistence or "
                    "failed before identity could be recorded; it is never "
                    "backfilled from the current server deployment.",
    )
    output_language: str = "English"
    error: str | None = None
    elapsed_seconds: int | None = None
    source_counts: dict[str, int] | None = None
    evidence_incomplete: bool = Field(
        default=False,
        description="Run finished but its per-agent evidence files could not be "
                    "written; the report stands, the audit trail behind its "
                    "citations does not.",
    )
    failed_domains: list[str] = Field(
        default_factory=list,
        description="Evidence domains whose retrieval backend failed, so the "
                    "assessment was produced without them. Distinct from a "
                    "domain that searched successfully and found nothing.",
    )
    usage: dict | None = Field(
        default=None,
        description="Tokens and estimated cost for the run, per agent and in "
                    "total. Absent for runs that predate cost accounting and "
                    "for runs that failed before the crew started.",
    )
    claim_grounding: dict | None = Field(
        default=None,
        description="How many of the run's quantitative claims could be "
                    "checked against the text of the sources they cite, how "
                    "many cited a figure absent from it, and how many could "
                    "not be checked at all. The last number bounds what the "
                    "other two mean. Status distinguishes completed, partial, "
                    "not-applicable, unavailable, and failed checks; None is "
                    "reserved for runs created before status was recorded.",
    )
    authority_coverage: dict | None = Field(
        default=None,
        description="Required regulator and clinical-registry coverage for applicable "
                    "biomedical topics. Incomplete is a review warning, not a failed run.",
    )
    component_coverage: dict | None = Field(
        default=None,
        description="Coverage of independently searchable components in a combined "
                    "system. Incomplete is advisory and never proves absence.",
    )
    evidence_gap_shadow: dict | None = Field(
        default=None,
        description="Zero-call phase-1 evidence-gap eligibility audit. States "
                    "distinguish disabled, checked, and failed evaluation; no "
                    "supplementary search is executed.",
    )
    decision_gate: dict | None = Field(
        default=None,
        description="Code-derived orientation, incomplete-context, or decision-support "
                    "state. None means the run predates this gate; it is not a pass.",
    )
    report_audit: dict | None = Field(
        default=None,
        description="Non-blocking threshold-provenance and citation material-scope "
                    "audit. None means the run predates the audit, not that it passed.",
    )
    quality_review: dict | None = Field(
        default=None,
        description="Whether the independent reviewer completed. 'partial' means "
                    "one or more exact targets were absent and those validated "
                    "draft passages were preserved; 'fallback' means the whole "
                    "review was unavailable rather than presenting it as a pass.",
    )
    consistency: dict | None = Field(
        default=None,
        description="Disagreements between the report's own recommendation and "
                    "the scorecard shipped beside it. Nothing else in the "
                    "pipeline compares the two.",
    )
    observability: dict | None = Field(
        default=None,
        description="OpenTelemetry setup and bounded-flush state for this "
                    "run. 'active' means configured, while delivery remains "
                    "an attempt because OTLP provides no persistence "
                    "acknowledgement. Absent for runs created before tracing.",
    )
    checkpointing: dict | None = Field(
        default=None,
        description="Durable node-output persistence state. 'degraded' means the "
                    "assessment may still finish but a later process cannot safely "
                    "reuse every validated node.",
    )
    recovery: dict | None = Field(
        default=None,
        description="Whether recovery was requested, which validated nodes were "
                    "reused, and the first node that still had to execute.",
    )
    artifacts: list[str] = Field(
        default_factory=list,
        description="Artifact names available via /api/runs/{run_id}/{name}",
    )


class RunSummary(BaseModel):
    """One entry in the run list."""

    run_id: str
    state: RunState
    topic: str
    started_at: str
    duration: str
    owner_label: str | None = Field(
        default=None,
        description="Which access code created this run — set only when the "
                    "requester holds ACCESS_CODE_ADMIN; every other viewer's "
                    "list is already scoped to their own code alone.",
    )


class RunList(BaseModel):
    runs: list[RunSummary]
    total: int


class HealthStatus(BaseModel):
    status: Literal["ok"]
    active_runs: int = Field(
        description="Worker subprocesses currently running. Kept separately "
                    "from active_paid_operations for API compatibility and "
                    "run-specific operational diagnostics.",
    )
    active_paid_operations: int = Field(
        description="All operations occupying the shared paid-provider/host "
                    "capacity: worker runs plus inline PDF extraction.",
    )
    max_concurrent: int
    retention_days: int = Field(
        default=0,
        description="Days a finished run is kept before automatic deletion; "
                    "0 means runs are kept indefinitely. Reported so a visitor can "
                    "see how long a run's extracted paper metadata and assessment "
                    "will live on this deployment. Raw PDFs are deleted immediately "
                    "after successful extraction.",
    )
    llm_provider: str | None = None


class ReadinessStatus(BaseModel):
    """Whether this container can actually run an assessment, not just serve.

    Separate from HealthStatus because the two answer different questions and
    a platform can only act on one of them. /health says the process is up;
    this says a submitted run would get past the first minute. A deployment
    missing its LLM key serves every page perfectly and fails every run.
    """

    ready: bool
    checks: dict[str, str] = Field(
        description="Check name -> 'ok' or the reason it is not. Named rather "
                    "than counted so an operator reading a failed deploy sees "
                    "which one to fix.",
    )
    llm_provider: str | None = None
    search_provider: str | None = None
