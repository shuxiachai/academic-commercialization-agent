"""Regression at credential dispatch and ordinary-log boundaries, never paid calls."""

from __future__ import annotations

import io
import json
import os
from email.message import Message
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.error import HTTPError
from urllib.request import HTTPSHandler, build_opener
from urllib.response import addinfourl

import pytest
from fastapi.testclient import TestClient

from academic_agent import language, llm_config, pdf_extractor
from api import access, main, papers, runs

pytestmark = pytest.mark.allow_llm

CASES = [
    ("openai", "OPENAI_API_KEY", "https://api.openai.com/v1", "gpt-4o"),
    ("qwen", "DASHSCOPE_API_KEY", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3.5-plus"),
    ("deepseek", "DEEPSEEK_API_KEY", "https://api.deepseek.com", "deepseek-chat"),
    ("anthropic", "ANTHROPIC_API_KEY", "https://api.anthropic.com", "claude-sonnet-5"),
]


class Response:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps({
            "choices": [{"message": {"content": "translated"}}],
            "content": [{"type": "text", "text": "translated"}],
        }).encode()


@pytest.mark.parametrize("provider,key_name,base,model", CASES)
@pytest.mark.parametrize("byok", [False, True])
def test_auxiliary_and_factory_share_the_actual_identity(provider, key_name, base, model, byok):
    """The real child environment must reach both transports, not just config."""
    dirty = dict.fromkeys(runs._OPERATOR_BILLED_ENV, "operator-secret")
    if byok:
        env = runs.BYOKCredentials(provider, "visitor-key", "visitor-search").as_env(dirty)
        key = "visitor-key"
    else:
        env = {**dict.fromkeys(runs._OPERATOR_BILLED_ENV, ""), key_name: "operator-key",
               "LLM_PROVIDER": provider}
        key = "operator-key"
    with patch.dict(os.environ, env), patch.object(language, "urlopen", return_value=Response()) as send, \
         patch.object(llm_config, "LLM", return_value=MagicMock()) as factory:
        assert language._llm_call("private-input", system="translate") == "translated"
        llm_config.create_llm()
    request = send.call_args.args[0]
    body = json.loads(request.data)
    headers = dict((k.lower(), v) for k, v in request.header_items())
    assert request.full_url == base + ("/v1/messages" if provider == "anthropic" else "/chat/completions")
    assert body["model"] == factory.call_args.kwargs["model"] == model
    assert factory.call_args.kwargs["api_key"] == key
    assert factory.call_args.kwargs["base_url"] == base
    assert headers["x-api-key" if provider == "anthropic" else "authorization"] == (
        key if provider == "anthropic" else "Bearer " + key
    )
    assert "operator-secret" not in request.full_url + str(headers) + str(body)
    if provider == "qwen":
        assert body["enable_thinking"] is False
        assert factory.call_args.kwargs["additional_params"]["extra_body"] == {"enable_thinking": False}
    send.assert_called_once()


@pytest.mark.parametrize("provider,key_name,base,model", CASES)
def test_inline_byok_pins_endpoint_even_with_sdk_environment(provider, key_name, base, model):
    """PDF runs in the API process: SDK base variables cannot redirect its key."""
    env = dict.fromkeys(runs._OPERATOR_BILLED_ENV, "operator-secret")
    env.update(OPENAI_BASE_URL="https://operator.invalid/v1",
               ANTHROPIC_BASE_URL="https://operator.invalid")
    with patch.dict(os.environ, env), patch.object(llm_config, "LLM", return_value=MagicMock()) as factory:
        llm_config.create_llm(provider=provider, api_key="visitor-key")
    assert factory.call_args.kwargs["base_url"] == base
    assert factory.call_args.kwargs["model"] == model
    assert factory.call_args.kwargs["api_key"] == "visitor-key"


@pytest.mark.parametrize("provider", ["openai", "qwen", "deepseek", "anthropic", "unknown"])
def test_invalid_configuration_makes_no_auxiliary_request(provider):
    """Optional translation can abstain, never try an empty/wrong-provider key."""
    env = {**dict.fromkeys(runs._OPERATOR_BILLED_ENV, ""), "LLM_PROVIDER": provider}
    with patch.dict(os.environ, env), patch.object(language, "urlopen") as send, \
         pytest.warns(UserWarning, match="RuntimeError"):
        assert language._llm_call("private", system="translate") == ""
    send.assert_not_called()


@pytest.mark.parametrize("kwargs", [{"provider": "qwen"}, {"api_key": "x"},
                                    {"provider": "openai", "api_key": ""}])
def test_partial_inline_credentials_never_select_operator_billing(kwargs):
    with patch.object(llm_config, "LLM") as factory, pytest.raises(RuntimeError):
        llm_config.create_llm(**kwargs)
    factory.assert_not_called()


@pytest.mark.parametrize("base", ["https://api.deepseek.com", "https://api.anthropic.com",
                                 "https://dashscope.aliyuncs.com/compatible-mode/v1",
                                 "http://api.openai.com/v1", "https://secret@api.openai.com/v1",
                                 "https://api.openai.com/v1?key=private"])
def test_invalid_or_other_vendor_endpoint_fails_readiness_and_dispatch(base):
    env = {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "visitor-key", "OPENAI_API_BASE": base}
    with patch.dict(os.environ, env), patch.object(language, "urlopen") as send:
        with pytest.raises(RuntimeError):
            llm_config.validate_llm_configuration()
        with pytest.warns(UserWarning, match="RuntimeError"):
            assert language._llm_call("private", system="translate") == ""
    send.assert_not_called()


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirect_is_rejected_before_another_authenticated_request(status):
    """Exercise urllib's real error/redirect chain, with a fake HTTPS transport."""
    attempts = []

    class FakeHTTPS(HTTPSHandler):
        def https_open(self, request):
            attempts.append(request.full_url)
            headers = Message()
            headers["Location"] = "https://other-provider.invalid/"
            response = addinfourl(io.BytesIO(b""), headers, request.full_url, status)
            response.msg = "redirect"
            return response

    def opener(*handlers):
        return build_opener(FakeHTTPS(), *handlers)

    with patch.object(language, "build_opener", side_effect=opener):
        request = language.Request("https://api.openai.com/v1/chat/completions",
                                   headers={"Authorization": "Bearer fake"}, data=b"{}")
        with pytest.raises(HTTPError):
            language.urlopen(request, timeout=1)
    assert attempts == ["https://api.openai.com/v1/chat/completions"]


def test_auxiliary_warning_never_echoes_a_provider_exception():
    with patch.dict(os.environ, {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "fake"}), \
         patch.object(language, "urlopen", side_effect=OSError("secret-key private-paper")), \
         pytest.warns(UserWarning) as warnings:
        assert language._llm_call("private-paper", system="translate") == ""
    assert len(warnings) == 1
    assert "OSError" in str(warnings[0].message)
    assert "private-paper" not in str(warnings[0].message)
    assert "secret-key" not in str(warnings[0].message)


def test_pdf_parser_exception_cannot_echo_model_content():
    llm = MagicMock()
    llm.call.return_value = "private-paper-excerpt secret-key"
    with patch.object(llm_config, "create_llm", return_value=llm), pytest.raises(ValueError) as error:
        pdf_extractor._call_llm_json("private-paper")
    assert "non-JSON" in str(error.value)
    assert "private-paper" not in str(error.value)
    assert "secret-key" not in str(error.value)
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__


@pytest.mark.parametrize("exception,status", [
    (ValueError, 422), (runs.PaidLedgerUnavailable, 503), (main._PaperStorageError, 500),
])
def test_pdf_http_failure_logs_only_category(tmp_path, caplog, monkeypatch, exception, status):
    """Assert the HTTP catch boundary, including upstream validation/SDK echoes."""
    monkeypatch.setattr(papers, "PAPERS_ROOT", tmp_path)
    monkeypatch.setattr(access, "ACCESS_CODE", None)
    monkeypatch.setattr(main, "_process_uploaded_paper",
                        AsyncMock(side_effect=exception("private-paper secret-key")))
    with TestClient(main.app, raise_server_exceptions=False) as client:
        response = client.post("/api/papers", files={"file": ("private.pdf", b"%PDF-1.4 fake")})
    assert response.status_code == status
    records = [r for r in caplog.records if r.name == main._LOGGER.name]
    assert records
    assert exception.__name__ in caplog.text
    assert all(r.exc_info is None for r in records)
    assert "private-paper" not in caplog.text + response.text
    assert "secret-key" not in caplog.text + response.text
    assert "paper-" not in caplog.text


def test_resolved_configuration_repr_never_discloses_key():
    config = llm_config.resolve_provider_config(provider="openai", api_key="private-key")
    assert "private-key" not in repr(config)


@pytest.mark.parametrize("provider,key_name,base,model", CASES)
def test_real_sdk_client_params_cannot_restore_operator_base(provider, key_name, base, model):
    """Use the installed provider class, not a factory double, without sending."""
    with patch.dict(os.environ, {"OPENAI_BASE_URL": "https://operator.invalid/v1",
                                 "ANTHROPIC_BASE_URL": "https://operator.invalid"}):
        llm = llm_config.create_llm(provider=provider, api_key="fake-visitor")
        params = llm._get_client_params()
    assert params["base_url"] == base
    assert params["api_key"] == "fake-visitor"


@pytest.mark.parametrize("provider,base,model", [
    ("deepseek", "https://api.deepseek.com", "deepseek/deepseek-chat"),
    ("qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3.5-plus"),
])
def test_legacy_operator_aliases_resolve_together(provider, base, model):
    """A deliberate legacy alias remains supported without a second router."""
    env = {**dict.fromkeys(runs._OPERATOR_BILLED_ENV, ""),
           "OPENAI_API_KEY": "legacy-key", "OPENAI_API_BASE": base, "OPENAI_MODEL_NAME": model}
    with patch.dict(os.environ, env), patch.object(language, "urlopen", return_value=Response()) as send:
        language._llm_call("topic", system="translate")
        config = llm_config.resolve_provider_config()
    request = send.call_args.args[0]
    assert config.provider == provider
    assert request.full_url == base + "/chat/completions"
    assert json.loads(request.data)["model"] == config.model
    assert request.get_header("Authorization") == "Bearer legacy-key"
