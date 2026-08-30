"""Zero-network transport and accounting seams for the v5 judge adapter."""

from __future__ import annotations

import hashlib
import json
from urllib.error import HTTPError

import pytest

from academic_agent.tools.deepseek_evidence_judge import (
    DEEPSEEK_CHAT_COMPLETIONS_ENDPOINT,
    DeepSeekEvidenceJudgeAdapter,
    DeepSeekJudgeAdapterError,
    DeepSeekJudgeRequest,
    JudgeTransportResponse,
    prompt_sha256,
)


def _request() -> DeepSeekJudgeRequest:
    system = "Classify supplied evidence and return only strict JSON."
    user = "Evaluate all candidates and preserve their exact order in JSON."
    return DeepSeekJudgeRequest(
        trace_id="openalex-v5-w01-pass-1",
        system_prompt=system,
        user_prompt=user,
        batch_input_sha256="1" * 64,
        prompt_sha256=prompt_sha256(system, user),
    )


def _provider_body(*, model: str = "deepseek-v4-flash") -> bytes:
    return json.dumps(
        {
            "id": "response-123",
            "model": model,
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": '{"case_id":"W01"}'},
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "prompt_cache_hit_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 110,
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")


class RecordingTransport:
    def __init__(self, body: bytes | None = None) -> None:
        self.body = body or _provider_body()
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs):  # noqa: ANN003, ANN204
        self.calls.append(kwargs)
        return JudgeTransportResponse(
            body=self.body,
            headers={"X-Request-ID": "provider-request-456"},
        )


def test_adapter_sends_one_fixed_endpoint_request_without_leaking_key(monkeypatch):
    # Production may override prices; this frozen experiment must not.
    monkeypatch.setenv("LLM_PRICE_PER_MTOK", "99:99:99")
    transport = RecordingTransport()
    adapter = DeepSeekEvidenceJudgeAdapter(
        api_key="secret-deepseek-key",
        transport=transport,
        monotonic_clock=iter((1.0, 1.25)).__next__,
    )

    response = adapter(_request())

    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["endpoint"] == DEEPSEEK_CHAT_COMPLETIONS_ENDPOINT
    assert call["timeout"] == 60.0
    assert call["headers"]["Authorization"] == "Bearer secret-deepseek-key"
    assert b"secret-deepseek-key" not in call["body"]
    payload = json.loads(call["body"])
    assert payload["model"] == "deepseek-v4-flash"
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["temperature"] == 0.0
    assert payload["stream"] is False
    assert payload["response_format"] == {"type": "json_object"}
    assert response.returned_model == "deepseek-v4-flash"
    assert response.provider_request_id == "provider-request-456"
    assert response.latency_ms == pytest.approx(250.0)
    assert response.usage.cached_prompt_tokens == 20
    assert response.usage.cost_usd > 0
    assert "built-in" in response.usage.cost_basis
    assert "peak" in response.usage.cost_basis
    assert "env" not in response.usage.cost_basis
    assert response.request_sha256 == hashlib.sha256(call["body"]).hexdigest()


def test_model_identity_mismatch_is_terminal_and_never_retried():
    transport = RecordingTransport(
        _provider_body(model="deepseek-v4-flash-0731")
    )
    adapter = DeepSeekEvidenceJudgeAdapter(
        api_key="secret",
        transport=transport,
    )

    with pytest.raises(
        DeepSeekJudgeAdapterError,
        match="model identity inconsistent",
    ) as caught:
        adapter(_request())

    assert caught.value.failure_type == "provider_model_identity_mismatch"
    assert caught.value.retryable is False
    assert caught.value.request_may_have_spent is True
    assert caught.value.observed_returned_model == "deepseek-v4-flash-0731"
    assert caught.value.observed_usage.prompt_tokens == 100
    assert caught.value.observed_usage.cost_usd is not None
    # A failed identity check may retain accounting, never the provider's
    # semantic content that could be used to tune a consumed experiment.
    assert not hasattr(caught.value, "raw_content")
    assert len(transport.calls) == 1


class RedirectTransport:
    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, **kwargs):  # noqa: ANN003, ANN204
        self.call_count += 1
        raise HTTPError(
            kwargs["endpoint"],
            302,
            "redirect",
            {},
            None,
        )


def test_redirect_is_a_single_terminal_attempt_with_no_secret_in_error():
    transport = RedirectTransport()
    adapter = DeepSeekEvidenceJudgeAdapter(
        api_key="do-not-persist-this-key",
        transport=transport,
    )

    with pytest.raises(DeepSeekJudgeAdapterError) as caught:
        adapter(_request())

    assert caught.value.failure_type == "provider_redirect"
    assert caught.value.request_may_have_spent is False
    assert "do-not-persist-this-key" not in str(caught.value)
    assert transport.call_count == 1


def test_missing_usage_is_uninspectable_instead_of_zero_cost():
    payload = json.loads(_provider_body())
    del payload["usage"]
    transport = RecordingTransport(json.dumps(payload).encode("utf-8"))
    adapter = DeepSeekEvidenceJudgeAdapter(
        api_key="secret",
        transport=transport,
    )

    with pytest.raises(
        DeepSeekJudgeAdapterError,
        match="schema validation",
    ) as caught:
        adapter(_request())

    assert caught.value.failure_type == "provider_response_invalid"
    assert len(transport.calls) == 1


def test_inconsistent_token_totals_are_uninspectable_and_not_retried():
    payload = json.loads(_provider_body())
    payload["usage"]["total_tokens"] = 999
    transport = RecordingTransport(json.dumps(payload).encode("utf-8"))
    adapter = DeepSeekEvidenceJudgeAdapter(
        api_key="secret",
        transport=transport,
    )

    with pytest.raises(
        DeepSeekJudgeAdapterError,
        match="usage accounting",
    ) as caught:
        adapter(_request())

    assert caught.value.failure_type == "provider_usage_invalid"
    assert caught.value.retryable is False
    assert caught.value.request_may_have_spent is True
    assert len(transport.calls) == 1


def test_request_rejects_a_prompt_hash_that_does_not_bind_both_messages():
    with pytest.raises(ValueError, match="prompt SHA-256"):
        DeepSeekJudgeRequest(
            trace_id="openalex-v5-w01-pass-1",
            system_prompt="A sufficiently long system classification instruction.",
            user_prompt="A sufficiently long user evidence classification request.",
            batch_input_sha256="2" * 64,
            prompt_sha256="3" * 64,
        )
