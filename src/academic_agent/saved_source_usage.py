"""Strict, private-content-free accounting for one isolated locator operation.

These are code-owned observations, not model prose, provider invoices or a
permission to spend. Receipt state and saved-text delivery remain independent.
"""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from academic_agent.report_evidence_snapshot import FrozenModel
from academic_agent.saved_source_loader import valid_run_id

Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Count = Annotated[int, Field(ge=0, le=1_000_000_000)]
Money = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]{0,8})\.[0-9]{9}$", max_length=19)]
Dispatch = Literal["not_dispatched", "may_have_dispatched", "response_received", "unknown"]
NativeJournal = Literal["not_started", "complete", "unresolved", "unavailable"]
PricePolicy = Literal["locator_qwen_frozen_rates_v1"]
FaultCode = Literal[
    "not_recorded", "accounting_unavailable", "binding_mismatch", "native_journal_unavailable",
    "native_journal_unresolved", "usage_missing_or_invalid", "model_mismatch", "price_unavailable",
]
MAX_ACCOUNTING_BYTES = 4096


class AccountingError(Exception):
    """Never include rejected values, paths or raw native errors in diagnostics."""

    def __init__(self):
        super().__init__("Saved-source accounting is unavailable.")


class OperationContext(FrozenModel):
    receipt_key_sha256: Hash
    owner_id: Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]
    intent_fingerprint: Hash
    run_id: str
    expires_at: int = Field(ge=1, le=9_007_199_254_740_991)
    selector_identity_sha256: Hash
    snapshot_hash: Hash
    catalog_hash: Hash

    @field_validator("run_id")
    @classmethod
    def check_run(cls, value):
        if not valid_run_id(value):
            raise ValueError("invalid_run_id")
        return value


class ReportedUsage(FrozenModel):
    prompt_tokens: Count
    completion_tokens: Count
    total_tokens: Count

    @model_validator(mode="after")
    def check_total(self):
        if self.prompt_tokens + self.completion_tokens != self.total_tokens:
            raise ValueError("contradictory_usage")
        return self


class NativeFactsV1(FrozenModel):
    """Only an exact operation's acknowledged durable native events enter here."""

    wire_sha256: Hash | None
    dispatch_state: Dispatch
    native_journal_state: NativeJournal
    model_matches_authorized: bool | None
    reported_usage: ReportedUsage | None
    reservation_usd: Money | None
    price_policy_id: PricePolicy | None
    fault_codes: list[FaultCode] = Field(max_length=8)

    @model_validator(mode="after")
    def check_events(self):
        if self.fault_codes != sorted(set(self.fault_codes)):
            raise ValueError("invalid_fault_codes")
        if self.reported_usage is not None and self.dispatch_state != "response_received":
            raise ValueError("unreceived_usage")
        if self.native_journal_state == "complete" and (self.wire_sha256 is None
                                                        or self.reservation_usd is None):
            raise ValueError("unbound_native_finish")
        return self


class ExecutionFactsV1(FrozenModel):
    """Physical operation finalization, distinct from successful receipt writes."""

    receipt_state: Literal["completed", "failed", "unresolved"]
    admission_state: Literal["not_admitted", "unknown", "admitted"]
    accounted_selector_entries: int = Field(ge=0, le=1)
    result_digest: Hash | None


def decimal_usd(value: Decimal) -> str:
    """Bounded canonical decimal text; NaN/Infinity never become JSON numbers."""
    if not value.is_finite() or value < 0:
        raise ValueError("invalid_usd")
    if value > Decimal("999999999.999999999") or value != value.quantize(Decimal("0.000000001")):
        raise ValueError("invalid_usd")
    text = format(value, ".9f")
    if len(text) > 19:
        raise ValueError("invalid_usd")
    return text


def estimated_usd(usage):
    return decimal_usd(Decimal(usage.prompt_tokens * 573 + usage.completion_tokens * 3440) / 1_000_000_000)


class UsageValues(FrozenModel):
    status: Literal["reported_complete", "reported_partial", "unknown", "not_dispatched", "unavailable"]
    prompt_tokens: Count | None
    completion_tokens: Count | None
    total_tokens: Count | None

    @model_validator(mode="after")
    def check_reported(self):
        values = (self.prompt_tokens, self.completion_tokens, self.total_tokens)
        if self.status in {"reported_complete", "reported_partial"}:
            if any(value is None for value in values) or values[0] + values[1] != values[2]:
                raise ValueError("invalid_reported_usage")
        elif any(value is not None for value in values):
            raise ValueError("unreported_tokens")
        return self


class CostValues(FrozenModel):
    currency: Literal["USD"]
    status: Literal["estimated", "partial_estimate", "unknown", "not_applicable", "unavailable"]
    estimated_usd: Money | None
    reservation_usd: Money | None
    price_policy_id: PricePolicy | None
    invoice_status: Literal["not_observed"]


class UsageProjectionV1(FrozenModel):
    schema_version: Literal[1]
    method_id: Literal["saved_source_native_usage_v1"]
    scope: Literal["single_saved_source_selection"]
    receipt_key_sha256: Hash
    run_id: str
    expires_at: int = Field(ge=1, le=9_007_199_254_740_991)
    publication_state: Literal["pending", "sealed", "unavailable"]
    dispatch_state: Dispatch
    native_journal_state: NativeJournal
    model_matches_authorized: bool | None
    usage: UsageValues
    cost: CostValues
    fault_codes: list[FaultCode] = Field(max_length=8)

    @field_validator("schema_version", mode="before")
    @classmethod
    def check_version_type(cls, value):
        if type(value) is not int:
            raise ValueError("invalid_schema_version")
        return value

    @model_validator(mode="after")
    def check_projection(self):
        if not valid_run_id(self.run_id) or self.fault_codes != sorted(set(self.fault_codes)):
            raise ValueError("invalid_identity_or_faults")
        state, usage, cost = self.publication_state, self.usage, self.cost
        if usage.status == "reported_complete" and (
                state != "sealed" or self.dispatch_state != "response_received"
                or self.native_journal_state != "complete"):
            raise ValueError("incomplete_reported_accounting")
        if usage.status == "reported_partial" and (self.dispatch_state != "response_received"
                                                  or self.native_journal_state == "complete"):
            raise ValueError("invalid_partial_accounting")
        if usage.status == "not_dispatched" and (state != "sealed" or self.dispatch_state != "not_dispatched"):
            raise ValueError("unproven_no_dispatch")
        if (usage.status == "unavailable" or state == "unavailable" or cost.status == "unavailable") and not self.fault_codes:
            raise ValueError("missing_unavailable_reason")
        if cost.status in {"estimated", "partial_estimate"}:
            expected = "reported_complete" if cost.status == "estimated" else "reported_partial"
            if (usage.status != expected or self.model_matches_authorized is not True
                    or cost.price_policy_id != "locator_qwen_frozen_rates_v1"
                    or cost.estimated_usd != estimated_usd(usage)):
                raise ValueError("invalid_estimate")
        elif cost.estimated_usd is not None:
            raise ValueError("unreported_estimate")
        if cost.status == "not_applicable" and usage.status != "not_dispatched":
            raise ValueError("unproven_no_cost")
        if self.model_matches_authorized is False and (
                cost.status != "unavailable" or "model_mismatch" not in self.fault_codes):
            raise ValueError("model_price_mismatch")
        return self


def unavailable_usage(key_hash, run_id, expires_at, fault="accounting_unavailable"):
    return UsageProjectionV1(
        schema_version=1, method_id="saved_source_native_usage_v1", scope="single_saved_source_selection",
        receipt_key_sha256=key_hash, run_id=run_id, expires_at=expires_at,
        publication_state="unavailable", dispatch_state="unknown", native_journal_state="unavailable",
        model_matches_authorized=None, fault_codes=[fault],
        usage=UsageValues(status="unavailable", prompt_tokens=None, completion_tokens=None, total_tokens=None),
        cost=CostValues(currency="USD", status="unavailable", estimated_usd=None,
                        reservation_usd=None, price_policy_id=None, invoice_status="not_observed"),
    ).model_dump(mode="json")


def project_usage(entry):
    """Project only allowlisted facts; never serialize the private context."""
    claim, facts = entry.claim, entry.native
    sealed = entry.phase == "sealed"
    dispatch = facts.dispatch_state if facts else ("may_have_dispatched" if entry.wire_sha256 else "unknown")
    journal = facts.native_journal_state if facts else ("unresolved" if entry.wire_sha256 else "not_started")
    model = facts.model_matches_authorized if facts else None
    faults = set(facts.fault_codes if facts else [])
    reported = facts.reported_usage if facts else None
    # Only the controller's actual accounted-entry count proves zero callback
    # activity. Locator callback_entries also includes rejected admission.
    if sealed and entry.execution.accounted_selector_entries == 0:
        dispatch, journal = "not_dispatched", "not_started"
    if reported is not None:
        if not sealed and journal == "complete":
            # Captured facts await controller finalization; observation cannot
            # publish a complete operation before the owning thread seals it.
            return unavailable_usage(claim.key_hash, claim.run_id, claim.expires)
        status = "reported_complete" if sealed and journal == "complete" else "reported_partial"
    elif sealed and dispatch == "not_dispatched":
        status = "not_dispatched"
    else:
        status = "unknown"
        if journal == "unresolved":
            faults.add("native_journal_unresolved")
        if dispatch == "response_received":
            faults.add("usage_missing_or_invalid")
    policy = facts.price_policy_id if facts else ("locator_qwen_frozen_rates_v1" if entry.reservation_usd else None)
    reservation = facts.reservation_usd if facts else entry.reservation_usd
    estimate = None
    if model is False:
        cost_status = "unavailable"
        faults.add("model_mismatch")
    elif reported is not None and model is True and policy is not None:
        cost_status = "estimated" if status == "reported_complete" else "partial_estimate"
        estimate = estimated_usd(reported)
    elif reported is not None:
        cost_status = "unavailable"
        faults.add("price_unavailable")
    else:
        cost_status = "not_applicable" if status == "not_dispatched" else "unknown"
    tokens = reported.model_dump() if reported else dict(prompt_tokens=None, completion_tokens=None, total_tokens=None)
    return UsageProjectionV1(
        schema_version=1, method_id="saved_source_native_usage_v1", scope="single_saved_source_selection",
        receipt_key_sha256=claim.key_hash, run_id=claim.run_id, expires_at=claim.expires,
        publication_state="sealed" if sealed else "pending", dispatch_state=dispatch,
        native_journal_state=journal, model_matches_authorized=model, fault_codes=sorted(faults),
        usage=UsageValues(status=status, **tokens),
        cost=CostValues(currency="USD", status=cost_status, estimated_usd=estimate,
                        reservation_usd=reservation, price_policy_id=policy, invoice_status="not_observed"),
    ).model_dump(mode="json")
