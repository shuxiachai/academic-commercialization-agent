"""Strict one-request Qwen adapter for the disconnected role-slot v6 study.

The production Qwen path retries selected transport failures and the sealed v5
judge has historical request identities.  Neither boundary is suitable for a
new experiment whose one adapter invocation must equal exactly one potentially
billable request.  This module therefore owns a separate request and response
contract while retaining the already tested direct-HTTP accounting rules.

It performs no retry, redirect, repair, fallback, endpoint override, streaming,
or model substitution.  Nothing in the production worker imports this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from academic_agent.token_usage import cost_for, price_for


QWEN_ROLE_SLOT_ENDPOINT = (
    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
)
QWEN_ROLE_SLOT_MODEL = "qwen3.5-plus"
QWEN_ROLE_SLOT_TIMEOUT_SECONDS = 120.0
QWEN_ROLE_SLOT_MAX_TOKENS = 8_000
_MAX_RESPONSE_BYTES = 1_000_000
_SHA256_PATTERN = r"^[0-9a-f]{64}$"

RoleSlotCandidateOrder = Literal[
    "provider_order",
    "reverse_provider_order",
    "candidate_sha256_order",
]


class QwenRoleSlotJudgeError(RuntimeError):
    """Credential-safe terminal failure from one v6 Qwen request."""

    def __init__(
        self,
        message: str,
        *,
        failure_type: str,
        retryable: bool,
        request_may_have_spent: bool,
        observed_returned_model: str | None = None,
        observed_usage: QwenRoleSlotUsageObservation | None = None,
        observed_latency_ms: float | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_type = failure_type
        self.retryable = retryable
        self.request_may_have_spent = request_may_have_spent
        # A rejected provider envelope may retain safe identity and accounting
        # so an already-spent request cannot disappear into a false zero.  Raw
        # semantic content is deliberately absent from this exception.
        self.observed_returned_model = observed_returned_model
        self.observed_usage = observed_usage
        self.observed_latency_ms = observed_latency_ms


class QwenRoleSlotRequest(BaseModel):
    """Credential-free identity for one candidate-order quote extraction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^Y0[1-8]$")
    pass_number: Literal[1, 2, 3]
    candidate_order: RoleSlotCandidateOrder
    trace_id: str = Field(pattern=r"^openalex-v6-y0[1-8]-pass-[123]$")
    requested_provider: Literal["qwen"] = "qwen"
    requested_model: Literal["qwen3.5-plus"] = QWEN_ROLE_SLOT_MODEL
    chat_completions_endpoint: Literal[
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    ] = QWEN_ROLE_SLOT_ENDPOINT
    system_prompt: str = Field(min_length=20, max_length=20_000)
    user_prompt: str = Field(min_length=20, max_length=250_000)
    batch_input_sha256: str = Field(pattern=_SHA256_PATTERN)
    prompt_sha256: str = Field(pattern=_SHA256_PATTERN)
    temperature: Literal[0.0] = 0.0
    max_tokens: Literal[8000] = QWEN_ROLE_SLOT_MAX_TOKENS
    transport_timeout_seconds: Literal[120.0] = QWEN_ROLE_SLOT_TIMEOUT_SECONDS

    @model_validator(mode="after")
    def _validate_request_identity(self) -> "QwenRoleSlotRequest":
        expected_trace = (
            f"openalex-v6-{self.case_id.casefold()}-pass-{self.pass_number}"
        )
        if self.trace_id != expected_trace:
            raise ValueError("trace ID drifted from the case and pass")
        expected_order = (
            "provider_order",
            "reverse_provider_order",
            "candidate_sha256_order",
        )[self.pass_number - 1]
        if self.candidate_order != expected_order:
            raise ValueError("candidate order drifted from the pass identity")
        observed_prompt = prompt_sha256(self.system_prompt, self.user_prompt)
        if observed_prompt != self.prompt_sha256:
            raise ValueError("prompt SHA-256 does not match the request text")
        return self

    def body(self) -> bytes:
        """Return exact wire bytes while keeping credentials out of artifacts."""

        # ``extra_body`` is an OpenAI SDK argument, not a direct-HTTP field.
        # The provider extension must therefore remain at the top level here.
        return json.dumps(
            {
                "enable_thinking": False,
                "max_tokens": self.max_tokens,
                "messages": [
                    {"content": self.system_prompt, "role": "system"},
                    {"content": self.user_prompt, "role": "user"},
                ],
                "model": self.requested_model,
                "response_format": {"type": "json_object"},
                "stream": False,
                "temperature": self.temperature,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")


class QwenRoleSlotUsageObservation(BaseModel):
    """Safe accounting retained even when semantic output is rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_tokens: int = Field(ge=0)
    cached_prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    cost_usd: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    cost_basis: str | None = Field(default=None, min_length=5, max_length=300)

    @model_validator(mode="after")
    def _validate_accounting(self) -> "QwenRoleSlotUsageObservation":
        if self.cached_prompt_tokens > self.prompt_tokens:
            raise ValueError("cached tokens cannot exceed prompt tokens")
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise ValueError("total tokens do not match prompt plus completion")
        if (self.cost_usd is None) != (self.cost_basis is None):
            raise ValueError("cost and cost basis must be known or unknown together")
        return self


class QwenRoleSlotUsage(QwenRoleSlotUsageObservation):
    """Successful request accounting with a reproducible local price."""

    cost_usd: float = Field(ge=0.0, allow_inf_nan=False)
    cost_basis: str = Field(min_length=5, max_length=300)


class QwenRoleSlotResponse(BaseModel):
    """Complete inspectable result from exactly one Qwen request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^Y0[1-8]$")
    pass_number: Literal[1, 2, 3]
    candidate_order: RoleSlotCandidateOrder
    trace_id: str = Field(pattern=r"^openalex-v6-y0[1-8]-pass-[123]$")
    request_sha256: str = Field(pattern=_SHA256_PATTERN)
    batch_input_sha256: str = Field(pattern=_SHA256_PATTERN)
    prompt_sha256: str = Field(pattern=_SHA256_PATTERN)
    requested_model: Literal["qwen3.5-plus"] = QWEN_ROLE_SLOT_MODEL
    returned_model: Literal["qwen3.5-plus"]
    provider_response_id: str = Field(min_length=3, max_length=300)
    provider_request_id: str | None = Field(default=None, max_length=300)
    finish_reason: str = Field(min_length=1, max_length=100)
    raw_content: str = Field(min_length=1, max_length=200_000)
    raw_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    usage: QwenRoleSlotUsage
    latency_ms: float = Field(ge=0.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _validate_response_identity(self) -> "QwenRoleSlotResponse":
        expected_trace = (
            f"openalex-v6-{self.case_id.casefold()}-pass-{self.pass_number}"
        )
        if self.trace_id != expected_trace:
            raise ValueError("response trace ID drifted from case and pass")
        expected_order = (
            "provider_order",
            "reverse_provider_order",
            "candidate_sha256_order",
        )[self.pass_number - 1]
        if self.candidate_order != expected_order:
            raise ValueError("response candidate order drifted from pass")
        if _sha256_text(self.raw_content) != self.raw_content_sha256:
            raise ValueError("raw model content SHA-256 does not match")
        return self


@dataclass(frozen=True)
class QwenRoleSlotTransportResponse:
    """Raw body and headers from one transport invocation."""

    body: bytes
    headers: Mapping[str, str]


class QwenRoleSlotOneRequestTransport(Protocol):
    """Injected seam whose one invocation equals one outbound request."""

    def __call__(
        self,
        *,
        endpoint: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout: float,
    ) -> QwenRoleSlotTransportResponse: ...


class _NoRedirectHandler(HTTPRedirectHandler):
    """Reject redirects so one adapter call cannot spend twice."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        del req, fp, code, msg, headers, newurl
        return None


class _UrllibOneRequestTransport:
    """Default direct transport with no redirect or retry behavior."""

    def __call__(
        self,
        *,
        endpoint: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout: float,
    ) -> QwenRoleSlotTransportResponse:
        request = Request(
            endpoint,
            data=body,
            headers=dict(headers),
            method="POST",
        )
        opener = build_opener(_NoRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            response_headers = {
                str(key): str(value) for key, value in response.headers.items()
            }
            return QwenRoleSlotTransportResponse(
                body=response.read(_MAX_RESPONSE_BYTES + 1),
                headers=response_headers,
            )


class _ProviderMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    content: str = Field(min_length=1, max_length=200_000)


class _ProviderChoice(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    finish_reason: str = Field(min_length=1, max_length=100)
    message: _ProviderMessage


class _PromptTokenDetails(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    cached_tokens: int = Field(default=0, ge=0)


class _ProviderUsage(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    prompt_tokens_details: _PromptTokenDetails | None = None


class _ProviderEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str = Field(min_length=3, max_length=300)
    model: str = Field(min_length=3, max_length=200)
    choices: tuple[_ProviderChoice, ...] = Field(min_length=1, max_length=1)
    usage: _ProviderUsage


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_json(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return _sha256_text(canonical)


def prompt_sha256(system_prompt: str, user_prompt: str) -> str:
    """Bind both messages independently from provider wire formatting."""

    return _sha256_json({"system": system_prompt, "user": user_prompt})


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    expected = name.casefold()
    return next(
        (value for key, value in headers.items() if key.casefold() == expected),
        None,
    )


def _safe_validation_detail(exc: ValidationError) -> str:
    details = []
    for error in exc.errors(include_input=False)[:4]:
        location = ".".join(str(part) for part in error["loc"]) or "response"
        details.append(f"{location}:{error['type']}")
    return "; ".join(details)[:500] or "provider response schema invalid"


def _usage_observation(
    envelope: _ProviderEnvelope,
) -> QwenRoleSlotUsageObservation:
    """Validate counters before admitting any semantic response text."""

    details = envelope.usage.prompt_tokens_details
    cached_tokens = details.cached_tokens if details is not None else 0
    metrics = SimpleNamespace(
        prompt_tokens=envelope.usage.prompt_tokens,
        cached_prompt_tokens=cached_tokens,
        cache_creation_tokens=0,
        completion_tokens=envelope.usage.completion_tokens,
    )
    # Deployment price overrides are useful operationally but cannot move a
    # committed experiment's cost stop.  The runner also locks token_usage.py.
    price = price_for(envelope.model, allow_env_override=False)
    cost = (
        cost_for(envelope.model, metrics, allow_env_override=False)
        if price is not None
        else None
    )
    return QwenRoleSlotUsageObservation(
        prompt_tokens=envelope.usage.prompt_tokens,
        cached_prompt_tokens=cached_tokens,
        completion_tokens=envelope.usage.completion_tokens,
        total_tokens=envelope.usage.total_tokens,
        cost_usd=cost,
        cost_basis=price.basis if price is not None else None,
    )


class QwenRoleSlotJudgeAdapter:
    """Perform one fixed-endpoint, fixed-model v6 JSON request."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float = QWEN_ROLE_SLOT_TIMEOUT_SECONDS,
        transport: QwenRoleSlotOneRequestTransport | None = None,
        monotonic_clock=None,  # noqa: ANN001
    ) -> None:
        resolved_key = (api_key or os.getenv("DASHSCOPE_API_KEY") or "").strip()
        if not resolved_key:
            raise ValueError("DASHSCOPE_API_KEY is required for the v6 Qwen judge")
        if timeout != QWEN_ROLE_SLOT_TIMEOUT_SECONDS:
            raise ValueError("v6 Qwen timeout must remain exactly 120 seconds")
        self._api_key = resolved_key
        self._timeout = timeout
        self._transport = transport or _UrllibOneRequestTransport()
        self._clock = monotonic_clock or time.perf_counter

    def __call__(
        self,
        request: QwenRoleSlotRequest,
    ) -> QwenRoleSlotResponse:
        """Send one request; every transport or accounting failure is terminal."""

        if request.transport_timeout_seconds != self._timeout:
            raise QwenRoleSlotJudgeError(
                "Qwen request timeout identity does not match the adapter",
                failure_type="request_timeout_identity_mismatch",
                retryable=False,
                request_may_have_spent=False,
            )
        body = request.body()
        request_sha256 = hashlib.sha256(body).hexdigest()
        started_at = self._clock()
        try:
            transport_response = self._transport(
                endpoint=request.chat_completions_endpoint,
                body=body,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "AcademicAgentRoleSlotV6-Qwen/1.0",
                    "X-Client-Request-ID": request.trace_id,
                },
                timeout=self._timeout,
            )
        except HTTPError as exc:
            is_redirect = 300 <= exc.code < 400
            raise QwenRoleSlotJudgeError(
                f"Qwen HTTP {exc.code}",
                failure_type=("provider_redirect" if is_redirect else "provider_http"),
                retryable=exc.code in {408, 429} or 500 <= exc.code < 600,
                request_may_have_spent=not is_redirect,
                observed_latency_ms=max(
                    (self._clock() - started_at) * 1000.0,
                    0.0,
                ),
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise QwenRoleSlotJudgeError(
                f"Qwen transport failed: {type(exc).__name__}",
                failure_type="provider_transport",
                retryable=True,
                request_may_have_spent=True,
                observed_latency_ms=max(
                    (self._clock() - started_at) * 1000.0,
                    0.0,
                ),
            ) from exc
        latency_ms = max((self._clock() - started_at) * 1000.0, 0.0)

        if len(transport_response.body) > _MAX_RESPONSE_BYTES:
            raise QwenRoleSlotJudgeError(
                "Qwen response exceeded the byte limit",
                failure_type="provider_response_too_large",
                retryable=False,
                request_may_have_spent=True,
                observed_latency_ms=latency_ms,
            )
        try:
            decoded = json.loads(transport_response.body.decode("utf-8"))
            envelope = _ProviderEnvelope.model_validate(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
            detail = (
                _safe_validation_detail(exc)
                if isinstance(exc, ValidationError)
                else type(exc).__name__
            )
            raise QwenRoleSlotJudgeError(
                f"Qwen response failed schema validation: {detail}",
                failure_type="provider_response_invalid",
                retryable=False,
                request_may_have_spent=True,
                observed_latency_ms=latency_ms,
            ) from exc

        try:
            observed_usage = _usage_observation(envelope)
        except ValidationError as exc:
            raise QwenRoleSlotJudgeError(
                "Qwen usage accounting failed schema validation",
                failure_type="provider_usage_invalid",
                retryable=False,
                request_may_have_spent=True,
                observed_returned_model=envelope.model,
                observed_latency_ms=latency_ms,
            ) from exc

        if envelope.model != request.requested_model:
            raise QwenRoleSlotJudgeError(
                "Qwen returned a model identity inconsistent with the request",
                failure_type="provider_model_identity_mismatch",
                retryable=False,
                request_may_have_spent=True,
                observed_returned_model=envelope.model,
                observed_usage=observed_usage,
                observed_latency_ms=latency_ms,
            )
        if observed_usage.cost_usd is None or observed_usage.cost_basis is None:
            raise QwenRoleSlotJudgeError(
                "Qwen token cost is not inspectable for the returned model",
                failure_type="provider_cost_uninspectable",
                retryable=False,
                request_may_have_spent=True,
                observed_returned_model=envelope.model,
                observed_usage=observed_usage,
                observed_latency_ms=latency_ms,
            )
        try:
            usage = QwenRoleSlotUsage.model_validate(
                observed_usage.model_dump(mode="python")
            )
        except ValidationError as exc:
            raise QwenRoleSlotJudgeError(
                "Qwen usage accounting failed schema validation",
                failure_type="provider_usage_invalid",
                retryable=False,
                request_may_have_spent=True,
                observed_returned_model=envelope.model,
                observed_latency_ms=latency_ms,
            ) from exc

        choice = envelope.choices[0]
        return QwenRoleSlotResponse(
            case_id=request.case_id,
            pass_number=request.pass_number,
            candidate_order=request.candidate_order,
            trace_id=request.trace_id,
            request_sha256=request_sha256,
            batch_input_sha256=request.batch_input_sha256,
            prompt_sha256=request.prompt_sha256,
            requested_model=request.requested_model,
            returned_model=envelope.model,
            provider_response_id=envelope.id,
            provider_request_id=(
                _header_value(transport_response.headers, "x-request-id")
                or _header_value(
                    transport_response.headers,
                    "x-dashscope-request-id",
                )
            ),
            finish_reason=choice.finish_reason,
            raw_content=choice.message.content,
            raw_content_sha256=_sha256_text(choice.message.content),
            usage=usage,
            latency_ms=latency_ms,
        )
