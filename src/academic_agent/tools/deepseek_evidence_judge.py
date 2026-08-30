"""Strict one-request DeepSeek adapter for the disconnected v5 study.

The semantic model is only a proposal mechanism.  This adapter therefore
owns no retry, repair, fallback, streaming, redirect, or model-selection
logic.  One invocation is one potentially billable HTTP request, and a
response is usable only when model identity, token usage, and local pricing
are all inspectable.  The development runner persists that response before
it permits another call.

Nothing in the production worker imports this module.
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


DEEPSEEK_CHAT_COMPLETIONS_ENDPOINT = (
    "https://api.deepseek.com/chat/completions"
)
REQUESTED_MODEL = "deepseek-chat"
_MAX_RESPONSE_BYTES = 1_000_000
_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class DeepSeekJudgeAdapterError(RuntimeError):
    """A safe, classified failure from one model request."""

    def __init__(
        self,
        message: str,
        *,
        failure_type: str,
        retryable: bool,
        request_may_have_spent: bool,
    ) -> None:
        super().__init__(message)
        self.failure_type = failure_type
        self.retryable = retryable
        self.request_may_have_spent = request_may_have_spent


class DeepSeekJudgeRequest(BaseModel):
    """Credential-free request identity passed across the paid-call seam."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trace_id: str = Field(pattern=r"^openalex-v5-w0[1-8]-pass-[12]$")
    requested_model: Literal["deepseek-chat"] = "deepseek-chat"
    system_prompt: str = Field(min_length=20, max_length=20_000)
    user_prompt: str = Field(min_length=20, max_length=250_000)
    batch_input_sha256: str = Field(pattern=_SHA256_PATTERN)
    prompt_sha256: str = Field(pattern=_SHA256_PATTERN)
    temperature: Literal[0.0] = 0.0
    max_tokens: int = Field(default=8_000, ge=500, le=12_000)

    @model_validator(mode="after")
    def _validate_prompt_identity(self) -> "DeepSeekJudgeRequest":
        payload = {
            "system": self.system_prompt,
            "user": self.user_prompt,
        }
        observed = _sha256_json(payload)
        if observed != self.prompt_sha256:
            raise ValueError("prompt SHA-256 does not match the request text")
        return self

    def body(self) -> bytes:
        """Return the exact OpenAI-shaped body, excluding every credential."""

        return json.dumps(
            {
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


class DeepSeekJudgeUsage(BaseModel):
    """Provider usage and locally reproducible cost for one request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_tokens: int = Field(ge=0)
    cached_prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0.0, allow_inf_nan=False)
    cost_basis: str = Field(min_length=5, max_length=300)

    @model_validator(mode="after")
    def _validate_token_accounting(self) -> "DeepSeekJudgeUsage":
        if self.cached_prompt_tokens > self.prompt_tokens:
            raise ValueError("cached tokens cannot exceed prompt tokens")
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise ValueError("total tokens do not match prompt plus completion")
        return self


class DeepSeekJudgeResponse(BaseModel):
    """Complete inspectable result from exactly one model request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trace_id: str = Field(pattern=r"^openalex-v5-w0[1-8]-pass-[12]$")
    request_sha256: str = Field(pattern=_SHA256_PATTERN)
    batch_input_sha256: str = Field(pattern=_SHA256_PATTERN)
    prompt_sha256: str = Field(pattern=_SHA256_PATTERN)
    requested_model: Literal["deepseek-chat"] = "deepseek-chat"
    returned_model: Literal["deepseek-chat"]
    provider_response_id: str = Field(min_length=3, max_length=300)
    provider_request_id: str | None = Field(default=None, max_length=300)
    finish_reason: str = Field(min_length=1, max_length=100)
    raw_content: str = Field(min_length=1, max_length=200_000)
    raw_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    usage: DeepSeekJudgeUsage
    latency_ms: float = Field(ge=0.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _validate_content_identity(self) -> "DeepSeekJudgeResponse":
        if _sha256_text(self.raw_content) != self.raw_content_sha256:
            raise ValueError("raw model content SHA-256 does not match")
        return self


@dataclass(frozen=True)
class JudgeTransportResponse:
    """Raw body plus response headers from one transport invocation."""

    body: bytes
    headers: Mapping[str, str]


class DeepSeekOneRequestTransport(Protocol):
    """Injected seam whose one invocation equals one outbound request."""

    def __call__(
        self,
        *,
        endpoint: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout: float,
    ) -> JudgeTransportResponse: ...


class _NoRedirectHandler(HTTPRedirectHandler):
    """Reject redirects so one adapter call cannot become two requests."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        del req, fp, code, msg, headers, newurl
        return None


class _UrllibOneRequestTransport:
    """Default transport with no redirect and no retry behavior."""

    def __call__(
        self,
        *,
        endpoint: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout: float,
    ) -> JudgeTransportResponse:
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
            return JudgeTransportResponse(
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


class _ProviderUsage(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    prompt_cache_hit_tokens: int = Field(default=0, ge=0)


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
    """Bind both messages without depending on provider wire formatting."""

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


class DeepSeekEvidenceJudgeAdapter:
    """Perform exactly one fixed-model JSON request with strict accounting."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float = 60.0,
        transport: DeepSeekOneRequestTransport | None = None,
        monotonic_clock=None,  # noqa: ANN001
    ) -> None:
        resolved_key = (api_key or os.getenv("DEEPSEEK_API_KEY") or "").strip()
        if not resolved_key:
            raise ValueError("DEEPSEEK_API_KEY is required for the v5 judge")
        if not 0 < timeout <= 120:
            raise ValueError("timeout must be greater than zero and at most 120 seconds")
        self._api_key = resolved_key
        self._timeout = timeout
        self._transport = transport or _UrllibOneRequestTransport()
        self._clock = monotonic_clock or time.perf_counter

    def __call__(self, request: DeepSeekJudgeRequest) -> DeepSeekJudgeResponse:
        """Send one request; all failures are terminal for the study runner."""

        body = request.body()
        request_sha256 = hashlib.sha256(body).hexdigest()
        started_at = self._clock()
        try:
            transport_response = self._transport(
                endpoint=DEEPSEEK_CHAT_COMPLETIONS_ENDPOINT,
                body=body,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "AcademicAgentEvidenceSetV5/1.0",
                    "X-Client-Request-ID": request.trace_id,
                },
                timeout=self._timeout,
            )
        except HTTPError as exc:
            is_redirect = 300 <= exc.code < 400
            raise DeepSeekJudgeAdapterError(
                f"DeepSeek HTTP {exc.code}",
                failure_type=("provider_redirect" if is_redirect else "provider_http"),
                retryable=exc.code in {408, 429} or 500 <= exc.code < 600,
                request_may_have_spent=not is_redirect,
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise DeepSeekJudgeAdapterError(
                f"DeepSeek transport failed: {type(exc).__name__}",
                failure_type="provider_transport",
                retryable=True,
                request_may_have_spent=True,
            ) from exc
        latency_ms = max((self._clock() - started_at) * 1000.0, 0.0)

        if len(transport_response.body) > _MAX_RESPONSE_BYTES:
            raise DeepSeekJudgeAdapterError(
                "DeepSeek response exceeded the byte limit",
                failure_type="provider_response_too_large",
                retryable=False,
                request_may_have_spent=True,
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
            raise DeepSeekJudgeAdapterError(
                f"DeepSeek response failed schema validation: {detail}",
                failure_type="provider_response_invalid",
                retryable=False,
                request_may_have_spent=True,
            ) from exc

        if envelope.model != request.requested_model:
            raise DeepSeekJudgeAdapterError(
                "DeepSeek returned a model identity inconsistent with the request",
                failure_type="provider_model_identity_mismatch",
                retryable=False,
                request_may_have_spent=True,
            )
        metrics = SimpleNamespace(
            prompt_tokens=envelope.usage.prompt_tokens,
            cached_prompt_tokens=envelope.usage.prompt_cache_hit_tokens,
            cache_creation_tokens=0,
            completion_tokens=envelope.usage.completion_tokens,
        )
        cost = cost_for(envelope.model, metrics)
        price = price_for(envelope.model)
        if cost is None or price is None:
            raise DeepSeekJudgeAdapterError(
                "DeepSeek token cost is not inspectable for the returned model",
                failure_type="provider_cost_uninspectable",
                retryable=False,
                request_may_have_spent=True,
            )
        try:
            usage = DeepSeekJudgeUsage(
                prompt_tokens=envelope.usage.prompt_tokens,
                cached_prompt_tokens=envelope.usage.prompt_cache_hit_tokens,
                completion_tokens=envelope.usage.completion_tokens,
                total_tokens=envelope.usage.total_tokens,
                cost_usd=cost,
                cost_basis=price.basis,
            )
        except ValidationError as exc:
            raise DeepSeekJudgeAdapterError(
                "DeepSeek usage accounting failed schema validation",
                failure_type="provider_usage_invalid",
                retryable=False,
                request_may_have_spent=True,
            ) from exc
        choice = envelope.choices[0]
        return DeepSeekJudgeResponse(
            trace_id=request.trace_id,
            request_sha256=request_sha256,
            batch_input_sha256=request.batch_input_sha256,
            prompt_sha256=request.prompt_sha256,
            requested_model=request.requested_model,
            returned_model=envelope.model,
            provider_response_id=envelope.id,
            provider_request_id=(
                _header_value(transport_response.headers, "x-request-id")
                or _header_value(transport_response.headers, "x-ds-request-id")
            ),
            finish_reason=choice.finish_reason,
            raw_content=choice.message.content,
            raw_content_sha256=_sha256_text(choice.message.content),
            usage=usage,
            latency_ms=latency_ms,
        )
