"""Request and response models for the HTTP API."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from academic_agent.byok_model import BYOK_MODEL_PATTERN
from academic_agent.run_spec import AssessmentMode, DecisionContext, SearchPlan
from academic_agent.pdf_extractor import PDFInputCoverage

#: "unknown" means the status or terminal file could not be read, not that the run
#: failed. It is deliberately not terminal: a client should retry rather than
#: tell the user their run died, because it may well have finished.
RunState = Literal["running", "completed", "failed", "cancelled", "timeout",
                   "unknown"]

BYOK_PROVIDERS = ("deepseek", "qwen", "openai", "anthropic")

_BYOK_SHAPE = (
    "llm_provider, llm_api_key and llm_model, plus exactly one of "
    "tavily_api_key or serper_api_key, must be provided together, or all "
    "omitted to use the deployment's own keys."
)


def _blank_model_is_missing(value: object) -> object:
    """An empty model field is a missing model, not a bad name."""
    if isinstance(value, str) and not value.strip():
        return None
    return value.strip() if isinstance(value, str) else value


def _check_byok(provider, llm_key, serper_key, tavily_key, model) -> None:
    """One rule for every BYOK body: complete or absent, never a mix.

    A partial set must not fall back to operator billing, so anything short
    of a complete set is rejected. Exactly one search key: either service
    serves the run, and accepting both would leave the choice implicit.
    Tavily is offered because Serper refuses requests from some hosting
    providers, including the deployment's. The model is part of the set:
    there is no built-in default, so the visitor's key is only ever billed
    for a model the visitor named.
    """
    search_keys = [k for k in (serper_key, tavily_key) if k]
    if any((provider, llm_key, serper_key, tavily_key, model)):
        if not (provider and llm_key and model and len(search_keys) == 1):
            raise ValueError(_BYOK_SHAPE)
    if provider is not None and provider not in BYOK_PROVIDERS:
        raise ValueError(f"llm_provider must be one of {BYOK_PROVIDERS}.")
    if model is not None and not BYOK_MODEL_PATTERN.fullmatch(model):
        raise ValueError("llm_model must be a plain model identifier "
                         "(letters, digits and . _ - : only, at most 100 characters).")


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
    search_plan: SearchPlan | None = Field(
        default=None,
        description="Search interpretation confirmed from POST /api/plan, used "
                    "instead of planning again in the worker; omitted, the worker "
                    "plans the search itself.",
    )

    # Bring-your-own-key: an alternative to the access code for a visitor who
    # is not the deployment owner. Complete or absent: a run either runs on
    # the deployment's own billed keys (gated by the access code) or entirely
    # on the requester's own, never a mix of the two.
    llm_provider: str | None = Field(
        default=None,
        description=f"Bring-your-own-key provider: one of {BYOK_PROVIDERS}. "
                    "Required together with llm_api_key and one search key.",
    )
    llm_api_key: str | None = Field(default=None, description="Bring-your-own LLM API key.")
    llm_model: str | None = Field(
        default=None,
        description="Model for the bring-your-own LLM key. Required with llm_provider; "
                    "there is no default.",
    )
    tavily_api_key: str | None = Field(default=None, description="Bring-your-own Tavily API key.")
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

    _model_blank = field_validator("llm_model", mode="before")(classmethod(
        lambda cls, value: _blank_model_is_missing(value)))

    @model_validator(mode="after")
    def _byok_is_all_or_nothing(self) -> "RunRequest":
        _check_byok(self.llm_provider, self.llm_api_key, self.serper_api_key,
                    self.tavily_api_key, self.llm_model)
        return self

    @property
    def assessment_mode(self) -> AssessmentMode:
        return (self.decision_context or DecisionContext()).assessment_mode

    @property
    def byok(self) -> bool:
        return self.llm_provider is not None

class PlanRequest(BaseModel):
    """Body for POST /api/plan."""

    topic: str = Field(min_length=3, max_length=300, description="Research topic as the user typed it")
    # The same complete set a run sends. With it the preview runs on the
    # caller's own model key; an account must send it. The search key is part
    # of the set and is not used by a preview.
    llm_provider: str | None = Field(default=None, description=f"One of {BYOK_PROVIDERS}.")
    llm_api_key: str | None = Field(default=None, max_length=400)
    llm_model: str | None = Field(default=None)
    tavily_api_key: str | None = Field(default=None, max_length=400)
    serper_api_key: str | None = Field(default=None, max_length=400)

    @field_validator("topic", mode="before")
    @classmethod
    def _strip_topic(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    _model_blank = field_validator("llm_model", mode="before")(classmethod(
        lambda cls, value: _blank_model_is_missing(value)))

    @model_validator(mode="after")
    def _byok_is_all_or_nothing(self) -> "PlanRequest":
        _check_byok(self.llm_provider, self.llm_api_key, self.serper_api_key,
                    self.tavily_api_key, self.llm_model)
        return self

    @property
    def byok(self) -> bool:
        return self.llm_provider is not None


class PlanPreview(BaseModel):
    """How the planner reads a topic, for the user to confirm or edit."""

    planned: bool = Field(default=True, description="False when the model gave no answer: search_topic is "
                                                    "then the topic as typed, not a reading of it.")
    resolved: bool = Field(description="False when no technology or research subject could be identified.")
    search_topic: str = Field(description="English phrase sent to every retrieval backend.")
    aliases: list[str] = Field(description="Equivalent phrasings searched alongside it.")
    components: list[str] = Field(description="Building blocks searched separately for a combined system.")


class FeedbackRequest(BaseModel):
    """Body for POST /api/runs/{run_id}/feedback: one click, fixed words, no text."""

    model_config = {"extra": "forbid"}

    changed_view: Literal["yes", "no", "unsure"] = Field(
        description="Whether the report changed how the reader sees the decision.")
    part: Literal["scorecard", "report", "sources", "checks"] | None = Field(
        default=None, description="The part that mattered most, when the reader says.")


class DecisionQuestion(BaseModel):
    """Who decides and what, as the run's decision context gave them."""

    decision_owner: str | None = None
    decision_type: str | None = None


_Verdict = Literal["go", "conditional_go", "defer", "no_go"]


class DecisionStatement(BaseModel):
    """One sentence of the report that states a conclusion, as written."""

    verdict: _Verdict
    statement: str
    section: str = Field(description="The report's own top-level heading over the statement.")
    follows: list[str] = Field(
        default_factory=list,
        description="Up to two sentences after it in the same paragraph: the reasons "
                    "and conditions the writer put beside it. Quoted, not chosen.",
    )
    needle: str = Field(description="Text of the statement with no citation in it, for finding its paragraph on a page.")


class DecisionConclusion(BaseModel):
    """What the report states for the decision. Read from its text; never inferred."""

    status: Literal["stated", "conflicting", "not_stated"] = Field(
        description="'not_stated': no sentence ties GO, NO_GO, DEFER or a conditional GO to the "
                    "conclusion. That is a fact about the wording, not a finding that the "
                    "report is undecided. 'conflicting': statements name different conclusions.",
    )
    verdict: _Verdict | None = None
    statement: str | None = None
    section: str | None = None
    follows: list[str] = Field(default_factory=list)
    needle: str | None = None
    statements: list[DecisionStatement] = Field(default_factory=list)


class RunDecision(BaseModel):
    """GET /api/runs/{run_id}/decision: the question a run was asked and the report's answer."""

    run_id: str
    asked: bool = Field(
        description="True only for a completed run whose gate permitted an actor-specific "
                    "conclusion (decision_support). Otherwise nothing below is filled.",
    )
    question: DecisionQuestion | None = None
    conclusion: DecisionConclusion | None = None


class FeedbackState(BaseModel):
    """The caller's own recorded answer about a run, or none."""

    recorded: bool
    changed_view: Literal["yes", "no", "unsure"] | None = None
    part: Literal["scorecard", "report", "sources", "checks"] | None = None
    recorded_at: str | None = None


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
    llm_model: str | None = Field(
        default=None,
        description="Model for the fresh LLM key; required with llm_provider. A different "
                    "model from the source run re-executes its nodes: checkpoint identity "
                    "binds the model.",
    )
    tavily_api_key: str | None = Field(default=None, description="Fresh Tavily API key.")
    serper_api_key: str | None = Field(default=None, description="Fresh Serper API key.")

    _model_blank = field_validator("llm_model", mode="before")(classmethod(
        lambda cls, value: _blank_model_is_missing(value)))

    @model_validator(mode="after")
    def _byok_is_all_or_nothing(self) -> "ResumeRunRequest":
        _check_byok(self.llm_provider, self.llm_api_key, self.serper_api_key,
                    self.tavily_api_key, self.llm_model)
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
    auxiliary_usage: dict | None = None
    title: str
    authors: str = ""
    doi: str | None = None
    url: str | None = None
    candidate_doi: str | None = None
    candidate_url: str | None = None
    core_contribution: str
    application_domain: str
    key_metrics: list[str] = Field(default_factory=list)
    delta_from_prior: str = ""
    commercialization_topic: str
    search_keywords: list[str] = Field(default_factory=list)
    abstract_excerpt: str = ""
    input_coverage: PDFInputCoverage = Field(default_factory=PDFInputCoverage)
    locator_status: Literal[
        "text_candidate", "title_match_candidate", "conflicting_candidates",
        "no_public_candidate", "legacy_unverified",
    ] = "legacy_unverified"
    public_record_lookup: Literal["not_attempted", "matched", "no_match", "unavailable"] = "not_attempted"


class PaidReceipt(BaseModel):
    """Acceptance observation, not current run state or proof of zero cost."""

    operation: Literal["run", "resume", "paper"]
    state: Literal["pending", "unknown", "accepted", "failed"]
    resource_id: str | None = None
    status_code: int | None = None
    response: dict | None = None
    expires_at: float
    auxiliary_usage: dict | None = None


class StepEvent(BaseModel):
    """One line of steps.jsonl, surfaced for live progress.

    `llm_attempt` rows carry the provider-attempt fields. They are the only
    per-run record of an attempt the transport killed: usage counts successful
    requests, so a billed 150-second timeout followed by a retry shows there
    as one request and a stage twice as long as its answer.
    """

    ts: float | None = None
    type: str = ""
    agent_idx: int | None = None
    agent: str = ""
    thought: str = ""
    tool: str = ""
    call: int | None = Field(
        default=None,
        description="Which call on this node, from 1; a guardrail retry is a new call "
                    "whose attempts start at 1 again.")
    attempt: int | None = Field(
        default=None, description="Provider attempt number within the call, from 1.")
    outcome: str | None = Field(
        default=None,
        description="returned, timeout, error, adapted (a refused parameter resent), rate_limited "
                    "(a 429 that passes by waiting; a streamed node waits and asks again), empty (an "
                    "answer with no text; a streamed node asks up to three times in all), or cut "
                    "(the provider ended the answer at its output limit; the node fails).")
    duration_seconds: float | None = Field(
        default=None, description="Wall time of this one attempt.")
    retry: bool | None = Field(
        default=None, description="Whether another attempt followed this one.")
    error_type: str | None = Field(
        default=None, description="Exception class name when the attempt did not return.")


class StageTiming(BaseModel):
    stage: str = Field(description="The worker's stage label, as in `stage`.")
    started_at: AwareDatetime
    duration_seconds: int | None = Field(
        default=None,
        description="Until the next stage began or the run ended; so far while "
                    "`active`. None when the end is unknown. The last agent stage "
                    "includes report finalization.",
    )
    active: bool = Field(default=False, description="The stage the run is in now.")


class RunEta(BaseModel):
    remaining_seconds: int = Field(
        ge=0, description="The middle of the range below, for a client that shows one figure.",
    )
    low_seconds: int = Field(
        ge=0, description="What the fastest of the runs in the pool took from this point to its end.")
    high_seconds: int = Field(ge=0, description="What the slowest of them took.")
    basis_runs: int = Field(description="Recent completed runs the range is drawn from.")
    basis: Literal["stages", "total"] = Field(
        description="`stages`: the rest of the current stage plus every later stage, run by run. "
                    "`total`: whole-run times, where too few runs recorded their stages.",
    )
    model: str | None = Field(
        default=None,
        description="The model whose runs make the range; null when they are runs of other models.")
    same_model: bool = Field(
        default=False,
        description="True when the range is drawn from at least three completed runs on this run's own "
                    "model; false when there were too few and runs of any model stand in.")
    overdue: bool = Field(
        default=False,
        description="This run has been in its current stage longer than every run in the pool was; the "
                    "range is then what the later stages alone took.")


class EarlierRun(BaseModel):
    """A run this one was resumed from, with what its own record says it took."""

    run_id: str
    record: Literal["available", "missing"] = Field(
        description="`missing`: the earlier run was deleted or has expired; nothing is known of it but its id.")
    state: RunState | None = None
    elapsed_seconds: int | None = None
    total_tokens: int | None = None
    usage_state: Literal["complete", "lower_bound", "unavailable"] = "unavailable"
    cost_usd: float | None = None
    cost_complete: bool = False


class CombinedSpend(BaseModel):
    """This run and every run it continues, added up."""

    runs: int = Field(description="Runs in the chain, this one included.")
    elapsed_seconds: int | None = Field(description="The sum of the run times that are known.")
    elapsed_complete: bool = Field(description="False when a run's time is not known and is left out.")
    total_tokens: int | None = Field(description="The sum of the token counts on record.")
    usage_state: Literal["complete", "lower_bound", "unavailable"] = Field(
        description="`complete` only when every run's count is complete; `lower_bound` when any is a floor "
                    "or missing; `unavailable` when no run has a count.")
    cost_usd: float | None = None
    cost_complete: bool = False


class RunLineage(BaseModel):
    """For a resumed run: the runs it continues, nearest first, and the totals."""

    earlier: list[EarlierRun]
    combined: CombinedSpend


class DailyQuota(BaseModel):
    """Paid operations today against the caller's cap: the operator's budget
    for an access code, the account's own allowance for an account."""

    limit: int
    used: int
    remaining: int
    resets_at: AwareDatetime


class RunProgress(BaseModel):
    """Everything a client needs to render live progress in one request.

    Combines status.json with the tail of steps.jsonl so a polling client
    makes one call per tick rather than three.
    """

    run_id: str
    viewer_can_modify: bool | None = Field(
        default=None,
        description="Whether the server would accept a Cancel, Delete or Resume of this run from the caller of "
                    "this read: the same rule that guards those requests. Null when the run has no owner on record "
                    "(a keys-only run): its id is then the only credential, and the server cannot say whose it is. "
                    "For a page to hide what would be refused; it is not the boundary, the requests are guarded themselves.",
    )
    continued_by: str | None = Field(
        default=None,
        description="The newest run that was resumed from this one, for a run that stopped. Told only to a caller "
                    "who may modify this run (`viewer_can_modify` true): whoever is told can open that run, and a "
                    "reader holding only this run's link is not given another. Null otherwise, and when no run "
                    "continued this one.",
    )
    auxiliary_usage: dict | None = None
    state: RunState
    status_record_state: Literal["absent", "readable", "unreadable"] | None = None
    runtime_metadata_unreadable: list[str] = Field(
        default_factory=list,
        description="Selected usage/accounting/checkpoint/recovery fields that could not be read. "
                    "Safe defaults do not prove zero spend or successful reuse.",
    )
    audit_metadata_unreadable: list[str] = Field(
        default_factory=list,
        description="Code-owned field names whose audit summary could not be read. "
                    "Their null/default projection is not a passing check.",
    )
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
    error_code: str | None = Field(
        default=None,
        description="The recognised cause behind `error`, the same for every reader: timeout, "
                    "provider_auth, provider_free_quota, provider_billing, provider_model_unavailable, "
                    "provider_request_rejected, provider_rate_limited, insufficient_evidence, "
                    "provider_response_format, quality_checks, provider_unreachable, "
                    "provider_output_limit, provider_empty_answer or unknown; "
                    "cancelled and timeout_resumable for those two outcomes. None when there is "
                    "nothing to explain. `error` stays the sentence to show.",
    )
    funded_by: Literal["own_keys", "deployment"] | None = Field(
        default=None,
        description="Whose keys the run used: an account's own, or the deployment's under an "
                    "access code. None for a run nobody owns. It decides who can act on a failure.",
    )
    daily_charge_reason: Literal["launch_failed", "provider_unreachable"] | None = Field(
        default=None,
        description="Why a refunded charge was given back: launch_failed (no worker existed) or "
                    "provider_unreachable (the run failed because the model provider could not be "
                    "reached; at most three a day for each owner). None for every other state, and "
                    "for a refund recorded before reasons were.",
    )
    daily_charge: Literal["charged", "refunded", "not_charged", "not_recorded", "unreadable"] = Field(
        default="not_recorded",
        description="Whether this run spent one of its owner's daily paid operations: charged; "
                    "refunded (see daily_charge_reason); not_charged (own key, or no cap); "
                    "not_recorded (the run predates the marker); unreadable. A run that launched "
                    "and then failed stays charged, unless the provider could not be reached.",
    )
    elapsed_seconds: int | None = None
    stage_timings: list[StageTiming] = Field(
        default_factory=list,
        description="When each stage began and how long it took. Empty for runs "
                    "that predate stage timing.",
    )
    eta: RunEta | None = Field(
        default=None,
        description="For a running run, the range recent completed runs took from this "
                    "point to their end; None without at least three of them.",
    )
    llm_model: str | None = Field(
        default=None,
        description="The model the worker was configured with, as it recorded at its start; for a run "
                    "from before that record, the model its usage names. Null when neither says.")
    lineage: RunLineage | None = Field(
        default=None,
        description="For a run resumed from an earlier one: those runs and the combined time and usage. "
                    "Null for a run that was not a resume.")
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
        description="Observed Crew-node tokens and estimated cost, not the entire bill. "
                    "Scope/excluded stages are explicit on new runs. Absent on old runs and "
                    "for runs that failed before the crew started.",
    )
    usage_accounting: dict | None = Field(
        default=None,
        description="Temporal completeness of usage: complete, a durable "
                    "lower bound, or unavailable. This is independent of "
                    "whether every model had a known price.",
    )
    runtime_budget: dict | None = Field(
        default=None,
        description="Code-owned request timeout and finalization reserves "
                    "applied by this worker. None means the run predates "
                    "deadline persistence.",
    )
    terminal: dict | None = Field(
        default=None,
        description="Immutable process outcome metadata. record_state is "
                    "committed or unreadable; None means a live or historical "
                    "run without the terminal contract.",
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
    steps_next_cursor: int = Field(default=0, ge=0)
    steps_read_state: Literal["absent", "readable", "partial", "unavailable"] = "absent"
    steps_rejected: int = Field(default=0, ge=0, description="Rejected complete lines observed in this log, not failed tasks.")
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
    viewer_can_modify: bool | None = Field(
        default=None,
        description="Whether the server would accept a Cancel, Delete or Resume of this run from the caller of "
                    "this read: the same rule that guards those requests. Null when the run has no owner on record "
                    "(a keys-only run): its id is then the only credential, and the server cannot say whose it is. "
                    "For a page to hide what would be refused; it is not the boundary, the requests are guarded themselves.",
    )
    continued_by: str | None = Field(
        default=None,
        description="The newest run that was resumed from this one, for a run that stopped. Told only to a caller "
                    "who may modify this run (`viewer_can_modify` true): whoever is told can open that run, and a "
                    "reader holding only this run's link is not given another. Null otherwise, and when no run "
                    "continued this one.",
    )
    auxiliary_usage: dict | None = None
    state: RunState
    # A valid immutable terminal can coexist with an unreadable live status.
    # Surface that loss even when the stronger outcome still says completed.
    status_record_state: Literal["absent", "readable", "unreadable"] | None = None
    runtime_metadata_unreadable: list[str] = Field(
        default_factory=list,
        description="Selected usage/accounting/checkpoint/recovery fields that could not be read. "
                    "Safe defaults do not prove zero spend or successful reuse.",
    )
    audit_metadata_unreadable: list[str] = Field(
        default_factory=list,
        description="Code-owned field names whose audit summary could not be read. "
                    "Their null/default projection is not a passing check.",
    )
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
    error_code: str | None = Field(
        default=None,
        description="The recognised cause behind `error`, the same for every reader: timeout, "
                    "provider_auth, provider_free_quota, provider_billing, provider_model_unavailable, "
                    "provider_request_rejected, provider_rate_limited, insufficient_evidence, "
                    "provider_response_format, quality_checks, provider_unreachable, "
                    "provider_output_limit, provider_empty_answer or unknown; "
                    "cancelled and timeout_resumable for those two outcomes. None when there is "
                    "nothing to explain. `error` stays the sentence to show.",
    )
    funded_by: Literal["own_keys", "deployment"] | None = Field(
        default=None,
        description="Whose keys the run used: an account's own, or the deployment's under an "
                    "access code. None for a run nobody owns. It decides who can act on a failure.",
    )
    daily_charge_reason: Literal["launch_failed", "provider_unreachable"] | None = Field(
        default=None,
        description="Why a refunded charge was given back: launch_failed (no worker existed) or "
                    "provider_unreachable (the run failed because the model provider could not be "
                    "reached; at most three a day for each owner). None for every other state, and "
                    "for a refund recorded before reasons were.",
    )
    daily_charge: Literal["charged", "refunded", "not_charged", "not_recorded", "unreadable"] = Field(
        default="not_recorded",
        description="Whether this run spent one of its owner's daily paid operations: charged; "
                    "refunded (see daily_charge_reason); not_charged (own key, or no cap); "
                    "not_recorded (the run predates the marker); unreadable. A run that launched "
                    "and then failed stays charged, unless the provider could not be reached.",
    )
    elapsed_seconds: int | None = None
    stage_timings: list[StageTiming] = Field(
        default_factory=list,
        description="When each stage began and how long it took. Empty for runs "
                    "that predate stage timing.",
    )
    eta: RunEta | None = Field(
        default=None,
        description="For a running run, the range recent completed runs took from this "
                    "point to their end; None without at least three of them.",
    )
    llm_model: str | None = Field(
        default=None,
        description="The model the worker was configured with, as it recorded at its start; for a run "
                    "from before that record, the model its usage names. Null when neither says.")
    lineage: RunLineage | None = Field(
        default=None,
        description="For a run resumed from an earlier one: those runs and the combined time and usage. "
                    "Null for a run that was not a resume.")
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
        description="Observed Crew-node tokens and estimated cost, not the entire bill. "
                    "Scope/excluded stages are explicit on new runs. Absent on old runs and "
                    "for runs that failed before the crew started.",
    )
    usage_accounting: dict | None = Field(
        default=None,
        description="Temporal completeness of usage: complete, a durable "
                    "lower bound, or unavailable. This is independent of "
                    "whether every model had a known price.",
    )
    runtime_budget: dict | None = Field(
        default=None,
        description="Code-owned request timeout and finalization reserves "
                    "applied by this worker. None means the run predates "
                    "deadline persistence.",
    )
    terminal: dict | None = Field(
        default=None,
        description="Immutable process outcome metadata. record_state is "
                    "committed or unreadable; None means a live or historical "
                    "run without the terminal contract.",
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
    resumed_from: str | None = Field(
        default=None,
        description="The run this one was resumed from, so a list can show the two as one piece of work.")
    owner_label: str | None = Field(
        default=None,
        description="Which access code created this run — set only when the "
                    "requester holds ACCESS_CODE_ADMIN; every other viewer's "
                    "list is already scoped to their own code alone.",
    )


class ActiveRun(BaseModel):
    """A run of the caller's own account that is going now."""

    run_id: str
    topic: str


class RunList(BaseModel):
    runs: list[RunSummary]
    total: int
    active_runs: list[ActiveRun] = Field(
        default_factory=list,
        description="The calling account's own runs that are going now, newest first. Always the caller's, "
                    "also for an administrator whose list holds everyone's runs. Empty for a caller that is "
                    "not an account.")
    at_capacity: bool = Field(
        default=False,
        description="True when the calling account already has as many paid operations going as it may "
                    "(one, by default): starting another would be refused as `account_busy`.")


class MaintenanceTiming(BaseModel):
    """Dispatch/completion observations; null is unknown, not a zero duration."""

    current_started_at: AwareDatetime | None = Field(
        default=None, description="UTC dispatch time of the attempt without a completed observation. "
                                  "May include executor queueing; consult supervisor state too.",
    )
    current_elapsed_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    last_started_at: AwareDatetime | None = None
    last_finished_at: AwareDatetime | None = None
    last_duration_seconds: float | None = Field(
        default=None, ge=0, allow_inf_nan=False,
        description="Monotonic dispatch-to-observed-completion duration of the last completed attempt.",
    )
    last_finished_age_seconds: float | None = Field(
        default=None, ge=0, allow_inf_nan=False,
        description="Monotonic age of the last completed result, including failures. "
                    "Not a freshness verdict or SLO.",
    )


class CleanupSummary(BaseModel):
    """Last cleanup attempt, not a guarantee that every expired file is gone."""

    model_config = {"frozen": True}
    state: Literal["not_checked", "complete", "partial", "disabled", "absent", "unavailable"]
    scan_complete: bool | None = Field(
        default=None, description="False means observed counts cover only an incomplete scan; null means no scan.",
    )
    scanned: int | None = Field(default=None, ge=0, strict=True)
    deleted: int | None = Field(default=None, ge=0, strict=True)
    skipped: int | None = Field(default=None, ge=0, strict=True)
    failed: int | None = Field(default=None, ge=0, strict=True)
    skip_reasons: dict[Literal["fresh", "live", "unrelated"], int] = Field(default_factory=dict)
    failure_reasons: dict[Literal["metadata", "delete"], int] = Field(default_factory=dict)


class MaintenanceStatus(BaseModel):
    """Observed watchdog state, not proof that every retained artifact is healthy."""

    state: Literal["not_started", "running", "degraded", "failed", "stopped"]
    checks: dict[str, Literal["not_checked", "ok", "failed"]] = Field(
        default_factory=dict, description="Last completed result per stage, not proof of current freshness.",
    )
    observed_at: AwareDatetime | None = Field(
        default=None, description="UTC snapshot time, not the time the stages last completed.",
    )
    timings: dict[str, MaintenanceTiming] = Field(default_factory=dict)
    cleanup: dict[Literal["papers", "retention"], CleanupSummary] = Field(
        default_factory=dict, description="Last cleanup attempt paired with that stage's completion clocks. "
                                        "Legacy checks describe normal return, not complete deletion.",
    )


class MaintenanceDeferral(BaseModel):
    """Observation of a skipped dispatch, never a refreshed completion time."""

    reason: Literal["active_operation"]
    observed_at: AwareDatetime


class SourceLocatorStatus(BaseModel):
    """Configuration observation only, not credential, storage or provider readiness."""

    execution: Literal["enabled", "disabled"]
    budget: Literal["configured", "disabled"]
    deferred_maintenance: dict[
        Literal["source_locator_receipts", "source_locator_accounting", "source_locator_native"],
        MaintenanceDeferral,
    ] = Field(default_factory=dict)


class AlertStatus(BaseModel):
    """Whether the operator can be told, not whether anything is wrong."""

    state: Literal["off", "ready", "misconfigured", "failing"] = Field(
        description="off: no robot is set. misconfigured: the setting is not its vendor's robot address, "
                    "or two robots are set. failing: the last message was not delivered. ready says "
                    "nothing was needed or it was sent.")
    channel: Literal["feishu", "wecom"] | None = Field(
        default=None, description="Which vendor's robot is set; null when none is usable.")
    last_sent_at: AwareDatetime | None = None
    last_failed_at: AwareDatetime | None = None


class MailStatus(BaseModel):
    """Whether the service can send email, not whether any was needed."""

    state: Literal["off", "ready", "misconfigured", "failing"] = Field(
        description="off: no mail setting. misconfigured: a setting is unusable or both are set, or MAIL_FROM "
                    "or PUBLIC_URL is missing. failing: the last message was not delivered. ready says "
                    "nothing was needed or it was sent.")
    channel: Literal["resend", "outbox"] | None = Field(
        default=None, description="resend: Resend's API. outbox: messages are written to a directory "
                                  "(development). null when nothing is usable.")
    last_sent_at: AwareDatetime | None = None
    last_failed_at: AwareDatetime | None = None


class RunMinutes(BaseModel):
    """The fastest and slowest of the newest completed runs, in whole minutes."""

    low: int = Field(ge=1)
    high: int = Field(ge=1)
    runs: int = Field(ge=3, description="Completed runs the two figures are drawn from.")


class HealthStatus(BaseModel):
    status: Literal["ok"]
    active_runs: int = Field(
        description="Occupied run slots, including launch and stop finalization. Kept separately "
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
    llm_model: str | None = Field(
        default=None,
        description="Model name a run on the deployment's own key would request, from the "
                    "same resolution the worker uses. Reported because the public "
                    "deployment changes models without a code change, so docs point "
                    "here instead of naming one. Null when no provider or model is "
                    "configured. A name is not proof the provider serves it.",
    )
    run_minutes: RunMinutes | None = Field(
        default=None,
        description="How long the newest completed assessments on this deployment took, for the pages that "
                    "say how long a run takes; null with fewer than three of them.")
    contact: str | None = Field(
        default=None,
        description="The operator's contact line (OPERATOR_CONTACT), if set: the same value the privacy page "
                    "shows, here for the run page of a failure only the operator can look into.")
    pipeline_revision: str | None = Field(
        default=None,
        description="Code this process serves: git:<commit> where the platform exposes "
                    "it (Railway, CI), otherwise a hash of the pipeline sources. "
                    "Lets a deploy be confirmed rather than inferred.",
    )

    source_locator: SourceLocatorStatus | None = Field(
        default=None, description="Optional locator configuration; null when its entry is not exposed. "
                                  "A configured budget is not proof of a credential or available allowance.",
    )
    alerts: AlertStatus = Field(
        default_factory=lambda: AlertStatus(state="off"),
        description="Operator alerts to a Feishu or WeCom group robot: whether they can be delivered.",
    )
    mail: MailStatus = Field(
        default_factory=lambda: MailStatus(state="off"),
        description="Outgoing email (verification links): whether it can be sent. With state off, "
                    "accounts are created verified.",
    )
    maintenance: MaintenanceStatus = Field(
        default_factory=lambda: MaintenanceStatus(state="not_started"),
        description="Background timeout/retention checks; not_started is not a passing audit.",
    )


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
    source_locator: SourceLocatorStatus | None = Field(
        default=None, description="Advisory locator configuration, independent of assessment readiness.",
    )
    maintenance: MaintenanceStatus | None = Field(
        default=None, description="HTTP supervisor snapshot shared with health. "
                                  "Absent from the standalone configuration-only readiness check.",
    )


class RetrievalLaneHealth(BaseModel):
    lane: str = Field(description="Audit label such as 'OA-Cited', 'S2' or 'market web search'.")
    observed_runs: int = Field(description="Examined runs whose audit has this lane.")
    empty_runs: int = Field(description="Runs in which the lane returned no result.")
    failed_runs: int = Field(description="Runs in which the lane recorded a refusal or failed request.")


class AuthCredentials(BaseModel):
    """Sign-up and sign-in share one body; api.accounts applies the policy."""

    email: str = Field(max_length=254)
    password: str = Field(max_length=200)
    invite: str | None = Field(default=None, max_length=200,
                               description="Invite code; needed in invite mode and for a reserved (admin) address.")


class AuthSession(BaseModel):
    """Returned once, at sign-up or sign-in. The token is a bearer credential:
    send it as `Authorization: Bearer <token>`; it is never shown again."""

    token: str
    email: str
    admin: bool = False
    verified: bool = Field(default=True, description="The address has been proven. Until it is, paid "
                                                     "operations are refused with email_unverified.")
    trial_runs_left: int = Field(default=0, description="Assessments this account may still start without "
                                                        "keys, on the deployment's own.")
    keys_saved: bool = Field(default=False, description="The account has API keys saved with it: its paid "
                                                        "operations run on them when a request brings none.")


class AuthMe(BaseModel):
    email: str
    admin: bool = False
    verified: bool = True
    notify_done: bool = Field(default=False, description="The account asked for an email when one of its runs ends.")
    trial_runs_left: int = Field(default=0, description="Assessments this account may still start without keys.")
    keys_saved: bool = Field(default=False, description="The account has API keys saved with it.")


class SavedKeys(BaseModel):
    """What an account is told about the keys saved with it. Never a key:
    the provider, the model, and the last four characters of each key, so a
    person can tell which key it is."""

    saved: bool = Field(description="This account has keys saved that the deployment can use.")
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_key_hint: str | None = Field(default=None, description="An ellipsis and the key's last four characters.")
    search: str | None = Field(default=None, description="tavily or serper.")
    search_key_hint: str | None = None
    saved_at: AwareDatetime | None = None


class NotifyPreference(BaseModel):
    """Whether the signed-in account wants an email when one of its runs ends."""

    enabled: bool


class VerifyEmail(BaseModel):
    """The token from a verification link, presented by the page that opened it."""

    token: str = Field(min_length=1, max_length=128)


class EmailVerified(BaseModel):
    email: str
    verified: Literal[True] = True


class PasswordForgot(BaseModel):
    """An address to send a password-reset link to. The answer is the same
    whether or not an account has it."""

    email: str = Field(max_length=254)


class PasswordReset(BaseModel):
    """The token from a reset link, with the password to set."""

    token: str = Field(min_length=1, max_length=128)
    new_password: str = Field(max_length=200)


class PasswordResetDone(BaseModel):
    email: str


class SampleSummary(BaseModel):
    """One committed example report, as the list of them states it."""

    slug: str = Field(description="The name in /samples/{slug} and /api/samples/{slug}.")
    title: str
    topic: str = Field(description="The topic exactly as it was given to the run.")
    committed: str = Field(description="The date the sample was added, YYYY-MM-DD.")
    commit: str = Field(description="The pipeline revision the run was made on.")
    model: str = Field(description="The model the run was made with.")
    language: str = Field(description="The language the report is written in: 'English' or 'Simplified Chinese'.")
    title_zh: str = Field(
        default="",
        description="The sample's name for the Chinese interface; empty where `title` is already Chinese.")
    overall_score: float | None = Field(
        default=None,
        description="The overall score (0-100) from the scorecard the sample's run wrote; null when this "
                    "deployment has no readable scorecard for it.")
    trl_score: float | None = Field(
        default=None,
        description="The technology readiness level (1-9) from the same scorecard; null likewise.")


class SiteInfo(BaseModel):
    """What the pages read before signing in say about this deployment: the
    privacy page, and the sample reader's link to the way in."""

    retention_days: int | None = Field(description="Days an assessment is kept; null when kept until deleted.")
    contact: str | None = Field(description="The operator's contact line (OPERATOR_CONTACT), if set.")
    accounts: bool = Field(description="Email-and-password accounts are enabled.")
    signup_open: bool = Field(
        default=False,
        description="New accounts can be created (open or invite mode); false where accounts are off.")
    account_backup_days: int | None = Field(
        default=None,
        description="Days a deleted account can remain in the service's own backups of the account "
                    "database; null when it takes none.")
    mail: bool = Field(
        default=False,
        description="This deployment hands email to its delivery service: address verification, password "
                    "reset and, for accounts that turn it on, a note when an assessment ends.")


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


class AccountDeletion(BaseModel):
    """The password again: a session alone must not be able to erase an account."""

    password: str = Field(max_length=200)


class AdminAccount(BaseModel):
    """One account as the admin console lists it. Never a hash, never a token."""

    id: int
    email: str
    created_at: int = Field(description="Unix time the account was created.")
    disabled: bool
    verified: bool = Field(default=True, description="The address has been proven, or the account predates email.")
    admin: bool = Field(description="Named in ACCOUNTS_ADMIN_EMAILS.")
    sessions: int = Field(description="Live sign-ins; expired ones are not counted.")
    last_seen_at: int | None = Field(description="Unix time of the newest live session's last request.")
    runs: int = Field(description="Assessments recorded under the account.")
    trial_used: int = Field(default=0, description="Assessments started on the account's trial and not given back.")


class FunnelAccounts(BaseModel):
    """Accounts created in the window, administrators apart; each step is a subset of the one before."""

    created: int
    verified: int = Field(description="Of those, the address has been proven.")
    ran: int = Field(description="Of those, at least one run is kept.")
    completed: int = Field(description="Of those, at least one kept run completed.")


class FunnelFailure(BaseModel):
    code: str = Field(description="The public failure code, as a run's status gives it.")
    runs: int


class FunnelTrial(BaseModel):
    started: int
    completed: int
    given_back: int = Field(description="Trials returned because the provider could not be reached.")


class AdminFunnel(BaseModel):
    """Counts only, from what is kept: no address, and nothing about a run that was deleted."""

    window_days: int
    since: int = Field(description="Unix time the window begins.")
    accounts: FunnelAccounts
    runs: dict[str, int] = Field(description="Runs started in the window by anyone but an administrator: "
                                             "started, then one count for each ending.")
    failures: list[FunnelFailure] = Field(description="Failed runs by public code, most frequent first.")
    trial: FunnelTrial
    admin_runs: int = Field(description="Administrators' runs in the window, counted apart.")
    runs_kept_since: int | None = Field(description="Start of the oldest run still on the volume; no run "
                                                    "count reaches further back.")
    unreadable: int = Field(description="Runs whose owner or state could not be read; in no other number.")


class AdminAccounts(BaseModel):
    accounts: list[AdminAccount]


class AdminConfirm(BaseModel):
    """The admin's own password: a session left open in a browser is not enough."""

    password: str = Field(max_length=200)


class AdminDisable(AdminConfirm):
    disabled: bool


class AdminPasswordReset(BaseModel):
    """Shown once. The server keeps only the hash, like the command."""

    email: str
    temporary_password: str
    sessions_ended: int


class AdminBackup(BaseModel):
    name: str
    taken_at: int | None = Field(description="Unix time from the file's name.")
    size: int
    accounts: int | None = Field(description="Accounts in the file once verified; null when it failed.")
    problem: str | None = Field(default=None, description="Why the file did not verify.")


class AdminBackups(BaseModel):
    scheduled: bool = Field(description="Whether the service takes backups by itself here.")
    every_hours: float | None
    keep: int | None
    backups: list[AdminBackup]


class LinkProbeReading(BaseModel):
    """One request from this host; marks are milliseconds since it started."""

    body_bytes: int
    connect_ms: int | None = Field(description="Socket connected; null when it never did.")
    tls_ms: int | None = Field(description="TLS up.")
    upload_ms: int | None = Field(description="Whole body sent.")
    first_byte_ms: int | None = Field(description="First response byte in.")
    total_ms: int
    status: int | None = Field(description="HTTP status (401 is the expected answer); null on a transport failure.")
    error: str | None = Field(description="The transport error's name when the request did not complete.")


class LinkProbeTarget(BaseModel):
    name: Literal["configured", "intl", "mainland"]
    host: str
    readings: list[LinkProbeReading]


class AdminLinkProbe(BaseModel):
    """What this host measured on the path to the provider, just now."""

    taken_at: str
    timeout_seconds: float
    small_bytes: int
    large_bytes: int = Field(description="The writer's request size: about 22,000 prompt tokens.")
    sizes: list[int] = Field(description="Every body size read, smallest first.")
    targets: list[LinkProbeTarget]


class AccountDeleted(BaseModel):
    runs: int = Field(description="Assessments deleted with the account.")
    uploads: int = Field(description="Uploaded papers deleted with the account.")


class KeyCheckRequest(BaseModel):
    """Body for POST /api/keys/check: one complete key set, as a run sends it."""

    llm_provider: str = Field(description=f"One of {BYOK_PROVIDERS}.")
    llm_api_key: str = Field(min_length=1, max_length=400)
    llm_model: str = Field(description="The model the key will be used with.")
    tavily_api_key: str | None = Field(default=None, max_length=400)
    serper_api_key: str | None = Field(default=None, max_length=400)

    @model_validator(mode="after")
    def _one_complete_set(self) -> "KeyCheckRequest":
        _check_byok(self.llm_provider, self.llm_api_key, self.serper_api_key,
                    self.tavily_api_key, self.llm_model)
        return self

    @property
    def search(self) -> str:
        return "tavily" if self.tavily_api_key else "serper"

    @property
    def search_api_key(self) -> str:
        return self.tavily_api_key or self.serper_api_key or ""


class SavedModelChange(BaseModel):
    """Body for PATCH /api/auth/keys: another model for the keys already saved.

    The model and nothing else. A body that also carries a key or a
    provider is refused whole: a key set is replaced whole, with PUT, so
    that nobody can believe a key was changed by a request that kept the
    old one.
    """

    model_config = ConfigDict(extra="forbid")

    llm_model: str = Field(description="The model the saved keys will be used with.")

    @field_validator("llm_model", mode="before")
    @classmethod
    def _a_plain_model_name(cls, value):
        if not isinstance(value, str) or not BYOK_MODEL_PATTERN.fullmatch(value):
            raise ValueError("llm_model must be a plain model identifier "
                             "(letters, digits and . _ - : only, at most 100 characters).")
        return value


class KeyCheckResult(BaseModel):
    """What the providers said about a key set. Carries no key and no provider text."""

    checked: bool = Field(description="False when this deployment does not check keys.")
    llm: Literal["accepted", "rejected", "unverified"] = Field(
        description="The model provider's answer about the key. `unverified` is no answer: "
                    "a timeout, a server error, or a key not allowed to list models.")
    model: Literal["listed", "not_listed", "unknown"] = Field(
        description="Whether the provider's model list names the model. `not_listed` only "
                    "when the whole list was read.")
    search: Literal["accepted", "rejected", "unverified"] = Field(
        description="The search service's answer about its key.")


class AuthConfig(BaseModel):
    """What the sign-in screen offers on this deployment."""

    enabled: bool = Field(description="Accounts exist here (ACCOUNTS_DB is set).")
    signup_open: bool = Field(description="New accounts can be created (open or invite mode).")
    signup: str = Field(default="closed", description="open, invite or closed.")
    access_codes: bool = Field(description="An operator access code is also accepted.")
    key_check: bool = Field(default=False, description="Saving keys can be checked with POST /api/keys/check.")
    contact: str | None = Field(default=None, description="Who to ask for an invite code: the operator's "
                                                          "contact as the privacy page states it, or None.")
    plan_preview: bool = Field(default=False, description="An account can preview the search with POST /api/plan, "
                                                          "on its own key.")
    daily_quota: bool = Field(default=False, description="An account has a daily allowance of its own, shown by "
                                                         "GET /api/quota once signed in.")
    password_reset: bool = Field(default=False, description="A forgotten password can be reset by a link "
                                                               "sent to the account's address: mail is set up.")
    notices: bool = Field(default=False, description="An account can ask for an email when one of its runs "
                                                        "ends: mail is set up.")
    admin_funded: bool = Field(default=False, description="An administrator's paid operations run on the "
                                                             "deployment's own keys; everyone else brings keys.")
    trial_runs: int = Field(default=0, description="Assessments a verified account may start without keys, on "
                                                   "the deployment's own; 0 when the operator has not turned "
                                                   "this on or the deployment has no keys to pay with.")


class RetrievalHealth(BaseModel):
    """Per-lane counts over recent runs' saved audits; no topics or run ids.

    Scoped like GET /api/runs: a code holder's own runs, every run for the
    admin code or a deployment without codes.
    """

    window: int
    runs_examined: int = Field(description="Newest runs with a saved audit, at most `window`.")
    lanes: list[RetrievalLaneHealth]
    failing: list[str] = Field(
        description="Lanes that failed in at least half of 3 or more observed runs.",
    )
    mostly_empty: list[str] = Field(
        description="Other lanes that returned nothing in at least 80% of 3 or more observed runs.",
    )
