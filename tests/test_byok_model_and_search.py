"""BYOK visitors choose their own model and may search with Tavily.

A visitor's run is billed to their own key, so the model is theirs to name;
it used to be fixed at each provider's default, and later fell back to one
when left empty. There is no default now: the model is part of the set. The search key was Serper
only, and Serper refuses requests from some hosts, including this
deployment's, so a Tavily key is accepted as the alternative. Both changes
must keep the existing boundary: complete credentials or operator billing,
never a mix, and no visitor field may redirect a key to another host.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from pydantic import ValidationError

from academic_agent import llm_config
from academic_agent.llm_config import MODEL_ENV_NAMES, resolve_provider_config
from api import papers
from api.models import ResumeRunRequest, RunRequest
from api.runs import BYOKCredentials

_OPERATOR_ENV = {
    "PATH": "/usr/bin",
    "LLM_PROVIDER": "qwen",
    "DASHSCOPE_API_KEY": "operator-dashscope",
    "QWEN_MODEL": "qwen3.8-max",
    "QWEN_API_BASE": "https://operator.invalid/v1",
    "OPENAI_MODEL_NAME": "deepseek-chat",
    "OPENAI_API_BASE": "https://api.deepseek.com",
    "SERPER_API_KEY": "operator-serper",
    "TAVILY_API_KEY": "operator-tavily",
}


def _request(cls=RunRequest, **fields):
    base = {"topic": "fusion power"} if cls is RunRequest else {}
    return cls(**base, **fields)


class RequestShapeTests(unittest.TestCase):

    def test_tavily_or_serper_completes_a_byok_request(self):
        for cls in (RunRequest, ResumeRunRequest):
            for search in ({"tavily_api_key": "t"}, {"serper_api_key": "s"}):
                with self.subTest(cls=cls.__name__, search=search):
                    req = _request(cls, llm_provider="qwen", llm_api_key="k",
                                   llm_model="qwen3.8-27b", **search)
                    self.assertTrue(req.byok)

    def test_partial_or_double_search_credentials_are_rejected(self):
        """Never fall back to operator billing, never leave the choice implicit."""
        for fields in (
            {"llm_provider": "qwen", "llm_api_key": "k", "llm_model": "m"},
            {"llm_provider": "qwen", "llm_api_key": "k", "llm_model": "m",
             "serper_api_key": "s", "tavily_api_key": "t"},
            {"tavily_api_key": "t"},
            {"llm_model": "qwen3.8-max"},
        ):
            for cls in (RunRequest, ResumeRunRequest):
                with self.subTest(cls=cls.__name__, fields=fields), self.assertRaises(ValidationError):
                    _request(cls, **fields)

    def test_model_must_be_a_plain_identifier(self):
        for bad in ("../qwen", "qwen 3", "https://evil.invalid/m", "qwen?x=1", "a/b", "x" * 101):
            with self.subTest(model=bad), self.assertRaises(ValidationError):
                _request(llm_provider="qwen", llm_api_key="k", tavily_api_key="t", llm_model=bad)
        for good in ("qwen3.8-max", "gpt-4.1-mini", "claude-sonnet-5", "deepseek-v4-flash", "qwen3.8-max:latest"):
            with self.subTest(model=good):
                req = _request(llm_provider="qwen", llm_api_key="k", tavily_api_key="t", llm_model=good)
                self.assertEqual(req.llm_model, good)

    def test_a_missing_or_blank_model_is_rejected_not_defaulted(self):
        """No built-in model: the visitor's key is billed only for one they named."""
        for model in ({}, {"llm_model": ""}, {"llm_model": "   "}):
            for cls in (RunRequest, ResumeRunRequest):
                with self.subTest(cls=cls.__name__, model=model), self.assertRaises(ValidationError):
                    _request(cls, llm_provider="qwen", llm_api_key="k", tavily_api_key="t", **model)

    def test_operator_billed_request_is_unchanged(self):
        req = _request()
        self.assertFalse(req.byok)
        self.assertIsNone(req.llm_model)


class SubprocessEnvironmentTests(unittest.TestCase):

    def test_only_the_selected_providers_model_variable_is_set(self):
        for provider, variable in MODEL_ENV_NAMES.items():
            with self.subTest(provider=provider):
                env = BYOKCredentials(provider, "guest-key", tavily_api_key="guest-tavily",
                                      llm_model="guest-model").as_env(_OPERATOR_ENV)
                self.assertEqual(env[variable], "guest-model")
                others = set(MODEL_ENV_NAMES.values()) - {variable}
                self.assertTrue(all(env.get(name, "") == "" for name in others))
                # The operator's model and base never survive.
                self.assertNotIn("qwen3.8-max", env.values())
                self.assertNotIn("https://operator.invalid/v1", env.values())

    def test_a_worker_without_a_model_fails_closed(self):
        """Defence in depth behind the API check: no operator model, no default."""
        env = BYOKCredentials("qwen", "guest-key", tavily_api_key="t").as_env(_OPERATOR_ENV)
        self.assertEqual(env["QWEN_MODEL"], "")
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "No model configured for qwen"):
                resolve_provider_config()

    def test_worker_resolves_the_visitors_model_at_the_official_endpoint(self):
        env = BYOKCredentials("qwen", "guest-key", tavily_api_key="t",
                              llm_model="qwen3.7-plus").as_env(_OPERATOR_ENV)
        with mock.patch.dict(os.environ, env, clear=True):
            config = resolve_provider_config()
        self.assertEqual((config.provider, config.model, config.api_key),
                         ("qwen", "qwen3.7-plus", "guest-key"))
        self.assertEqual(config.base_url, "https://dashscope.aliyuncs.com/compatible-mode/v1")

    def test_tavily_key_is_the_visitors_and_selects_tavily(self):
        from academic_agent.source_clients import TavilyClient, default_web_search_client

        env = BYOKCredentials("qwen", "guest-key", tavily_api_key="guest-tavily").as_env(_OPERATOR_ENV)
        self.assertEqual(env["SERPER_API_KEY"], "")
        with mock.patch.dict(os.environ, env, clear=True):
            client = default_web_search_client()
        self.assertIsInstance(client, TavilyClient)
        self.assertEqual(client.api_key, "guest-tavily")

    def test_serper_path_still_never_uses_the_operators_tavily(self):
        from academic_agent.source_clients import SerperClient, default_web_search_client

        env = BYOKCredentials("qwen", "guest-key", "guest-serper").as_env(_OPERATOR_ENV)
        self.assertEqual(env["TAVILY_API_KEY"], "")
        with mock.patch.dict(os.environ, env, clear=True):
            client = default_web_search_client()
        self.assertIsInstance(client, SerperClient)
        self.assertEqual(client.api_key, "guest-serper")

    def test_credentials_need_exactly_one_search_key_and_a_plain_model(self):
        with self.assertRaises(ValueError):
            BYOKCredentials("qwen", "k")
        with self.assertRaises(ValueError):
            BYOKCredentials("qwen", "k", "s", tavily_api_key="t")
        with self.assertRaises(ValueError):
            BYOKCredentials("qwen", "k", tavily_api_key="t", llm_model="../evil")


class ExplicitResolutionTests(unittest.TestCase):
    """The in-process paper extractor passes credentials explicitly."""

    def test_explicit_model_is_used_and_the_operator_environment_ignored(self):
        with mock.patch.dict(os.environ, _OPERATOR_ENV, clear=True):
            config = resolve_provider_config(provider="qwen", api_key="guest", model="qwen3.7-plus")
        self.assertEqual(config.model, "qwen3.7-plus")
        self.assertEqual(config.base_url, "https://dashscope.aliyuncs.com/compatible-mode/v1")

    def test_a_model_requires_explicit_credentials_and_a_plain_name(self):
        with self.assertRaises(RuntimeError):
            resolve_provider_config(model="qwen3.8-max")
        with self.assertRaises(RuntimeError):
            resolve_provider_config(provider="qwen", api_key="guest", model="http://evil.invalid")

    def test_explicit_credentials_without_a_model_are_rejected(self):
        with mock.patch.dict(os.environ, _OPERATOR_ENV, clear=True):
            with self.assertRaisesRegex(RuntimeError, "model must be named"):
                resolve_provider_config(provider="qwen", api_key="guest")

    def test_create_llm_passes_the_model_through(self):
        captured: dict = {}
        with mock.patch.dict(os.environ, _OPERATOR_ENV, clear=True), \
                mock.patch.object(llm_config, "LLM", lambda **kw: captured.update(kw)), \
                mock.patch.object(llm_config, "_wrap_with_retry", lambda x: x):
            llm_config.create_llm(provider="qwen", api_key="guest", model="qwen3.7-plus")
        self.assertEqual(captured["model"], "qwen3.7-plus")
        self.assertEqual(captured["api_key"], "guest")


class PaperUploadModelTests(unittest.TestCase):

    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(papers, "PAPERS_ROOT", Path(tmp.name) / "_papers")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _post(self, **form):
        from fastapi.testclient import TestClient

        from api.main import app

        seen: dict = {}

        def capture(_path, **kwargs):
            seen.update(kwargs)
            raise ValueError("stop after capture")

        with mock.patch("api.main.extract_paper_contribution", side_effect=capture):
            with TestClient(app) as client:
                response = client.post(
                    "/api/papers", data=form,
                    files={"file": ("p.pdf", b"%PDF-1.4 body", "application/pdf")})
        return response, seen

    def test_the_visitors_model_reaches_the_extractor(self):
        _response, seen = self._post(llm_provider="qwen", llm_api_key="guest", llm_model="qwen3.7-plus")
        self.assertEqual(seen.get("llm_model"), "qwen3.7-plus")
        self.assertEqual(seen.get("llm_api_key"), "guest")

    def test_a_bad_model_or_a_model_without_a_provider_is_rejected(self):
        for form in ({"llm_provider": "qwen", "llm_api_key": "guest", "llm_model": "../x"},
                     {"llm_model": "qwen3.8-max"}):
            with self.subTest(form=form):
                response, seen = self._post(**form)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(seen, {})

    def test_a_missing_or_empty_model_field_is_rejected(self):
        for form in ({"llm_provider": "qwen", "llm_api_key": "guest", "llm_model": ""},
                     {"llm_provider": "qwen", "llm_api_key": "guest"}):
            with self.subTest(form=form):
                response, seen = self._post(**form)
                self.assertEqual(response.status_code, 422)
                self.assertIn("llm_model is required", response.text)
                self.assertEqual(seen, {})
