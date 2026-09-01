"""Zero-network wire and accounting seams for the role-slot v6 Qwen judge."""

from __future__ import annotations

import hashlib
import json
from urllib.error import HTTPError

import pytest

from academic_agent.tools.qwen_role_slot_judge import (
    QWEN_ROLE_SLOT_ENDPOINT,
    QWEN_ROLE_SLOT_TIMEOUT_SECONDS,
    QwenRoleSlotJudgeAdapter,
    QwenRoleSlotJudgeError,
    QwenRoleSlotRequest,
    QwenRoleSlotTransportResponse,
    prompt_sha256,
)


def _request() -> QwenRoleSlotRequest:
    system = "Extract exact role quotes and return one strict JSON object only."
    user = "Process every candidate and fixed slot in provider order as JSON."
    return QwenRoleSlotRequest(
        case_id="Y01",
        pass_number=1,
        candidate_order="provider_order",
        trace_id="openalex-v6-y01-pass-1",
        system_prompt=system,
        user_prompt=user,
        batch_input_sha256="1" * 64,
        prompt_sha256=prompt_sha256(system, user),
    )


def _provider_body(*, model: str = "qwen3.5-plus") -> bytes:
    return json.dumps(
        {
            "id": "qwen-role-slot-response-1",
            "model": model,
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": '{"case_id":"Y01"}'},
                }
            ],
            "usage": {
                "prompt_tokens": 120,
                "prompt_tokens_details": {"cached_tokens": 20},
                "completion_tokens": 10,
                "total_tokens": 130,
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
        return QwenRoleSlotTransportResponse(
            body=self.body,
            headers={"X-DashScope-Request-ID": "qwen-role-slot-request-1"},
        )


def test_adapter_sends_exact_non_thinking_body_once(monkeypatch):
    """The test observes the wire body, not an unused configuration field."""

    monkeypatch.setenv("LLM_PRICE_PER_MTOK", "99:99:99")
    transport = RecordingTransport()
    adapter = QwenRoleSlotJudgeAdapter(
        api_key="role-slot-secret",
        transport=transport,
        monotonic_clock=iter((1.0, 1.25)).__next__,
    )

    response = adapter(_request())

    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["endpoint"] == QWEN_ROLE_SLOT_ENDPOINT
    assert call["timeout"] == QWEN_ROLE_SLOT_TIMEOUT_SECONDS
    assert call["headers"]["Authorization"] == "Bearer role-slot-secret"
    assert b"role-slot-secret" not in call["body"]
    body = json.loads(call["body"])
    assert body["enable_thinking"] is False
    assert "extra_body" not in body
    assert body["model"] == "qwen3.5-plus"
    assert body["temperature"] == 0.0
    assert body["stream"] is False
    assert body["max_tokens"] == 8000
    assert body["response_format"] == {"type": "json_object"}
    assert response.case_id == "Y01"
    assert response.candidate_order == "provider_order"
    assert response.provider_request_id == "qwen-role-slot-request-1"
    assert response.latency_ms == pytest.approx(250.0)
    assert response.usage.cached_prompt_tokens == 20
    assert response.usage.cost_usd > 0
    assert "built-in Qwen3.5 Plus peak tier" in response.usage.cost_basis
    assert "env" not in response.usage.cost_basis
    assert response.request_sha256 == hashlib.sha256(call["body"]).hexdigest()


class TimeoutTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs):  # noqa: ANN003, ANN204
        self.calls.append(kwargs)
        raise TimeoutError("simulated v6 timeout")


def test_timeout_is_one_terminal_attempt_with_visible_latency():
    transport = TimeoutTransport()
    adapter = QwenRoleSlotJudgeAdapter(
        api_key="secret",
        transport=transport,
        monotonic_clock=iter((1.0, 121.25)).__next__,
    )

    with pytest.raises(QwenRoleSlotJudgeError) as caught:
        adapter(_request())

    assert caught.value.failure_type == "provider_transport"
    assert caught.value.request_may_have_spent is True
    assert caught.value.observed_latency_ms == pytest.approx(120_250.0)
    assert len(transport.calls) == 1


def test_model_identity_failure_discards_semantic_content_but_keeps_usage():
    transport = RecordingTransport(
        _provider_body(model="qwen3.5-plus-2026-09-01")
    )
    adapter = QwenRoleSlotJudgeAdapter(api_key="secret", transport=transport)

    with pytest.raises(QwenRoleSlotJudgeError) as caught:
        adapter(_request())

    assert caught.value.failure_type == "provider_model_identity_mismatch"
    assert caught.value.request_may_have_spent is True
    assert caught.value.observed_returned_model == "qwen3.5-plus-2026-09-01"
    assert caught.value.observed_usage.prompt_tokens == 120
    assert not hasattr(caught.value, "raw_content")
    assert len(transport.calls) == 1


class RedirectTransport:
    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, **kwargs):  # noqa: ANN003, ANN204
        self.call_count += 1
        raise HTTPError(kwargs["endpoint"], 302, "redirect", {}, None)


def test_redirect_is_rejected_without_retry_or_key_leak():
    transport = RedirectTransport()
    adapter = QwenRoleSlotJudgeAdapter(
        api_key="do-not-persist-v6-key",
        transport=transport,
    )

    with pytest.raises(QwenRoleSlotJudgeError) as caught:
        adapter(_request())

    assert caught.value.failure_type == "provider_redirect"
    assert caught.value.request_may_have_spent is False
    assert "do-not-persist-v6-key" not in str(caught.value)
    assert transport.call_count == 1


def test_missing_or_inconsistent_usage_never_becomes_zero_cost():
    missing = json.loads(_provider_body())
    del missing["usage"]
    adapter = QwenRoleSlotJudgeAdapter(
        api_key="secret",
        transport=RecordingTransport(json.dumps(missing).encode("utf-8")),
    )
    with pytest.raises(QwenRoleSlotJudgeError) as missing_error:
        adapter(_request())
    assert missing_error.value.failure_type == "provider_response_invalid"

    inconsistent = json.loads(_provider_body())
    inconsistent["usage"]["total_tokens"] = 999
    transport = RecordingTransport(json.dumps(inconsistent).encode("utf-8"))
    adapter = QwenRoleSlotJudgeAdapter(api_key="secret", transport=transport)
    with pytest.raises(QwenRoleSlotJudgeError) as total_error:
        adapter(_request())
    assert total_error.value.failure_type == "provider_usage_invalid"
    assert total_error.value.request_may_have_spent is True
    assert len(transport.calls) == 1


def test_request_identity_rejects_wrong_pass_order_and_prompt_hash():
    with pytest.raises(ValueError, match="candidate order"):
        QwenRoleSlotRequest(
            case_id="Y01",
            pass_number=1,
            candidate_order="reverse_provider_order",
            trace_id="openalex-v6-y01-pass-1",
            system_prompt="A sufficiently long role-slot system instruction.",
            user_prompt="A sufficiently long role-slot user instruction in JSON.",
            batch_input_sha256="2" * 64,
            prompt_sha256="3" * 64,
        )

    with pytest.raises(ValueError, match="prompt SHA-256"):
        QwenRoleSlotRequest(
            case_id="Y01",
            pass_number=1,
            candidate_order="provider_order",
            trace_id="openalex-v6-y01-pass-1",
            system_prompt="A sufficiently long role-slot system instruction.",
            user_prompt="A sufficiently long role-slot user instruction in JSON.",
            batch_input_sha256="2" * 64,
            prompt_sha256="3" * 64,
        )
