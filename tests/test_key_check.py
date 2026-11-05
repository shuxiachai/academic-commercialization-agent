"""Checking an account's keys when it saves them.

No test here reaches a provider: every request is answered by a local
transport, which also records where it was sent and with what, because where
a key travels is the thing most worth pinning.

The rules under test: a provider's "no" is `rejected`; anything that is not
an answer about the key is `unverified` and never blocks; the requests go
only to the provider's own host and are not redirected; the endpoint is for
signed-in accounts and is bounded per account; no key comes back.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from api import access, key_check
from api import main as api_main
from api.main import app

PASSWORD = "a sufficiently long password"
LLM_KEY = "sk-llm-SECRET-0123456789"
SEARCH_KEY = "tvly-SEARCH-SECRET-9876"
KEYS = {"llm_provider": "deepseek", "llm_api_key": LLM_KEY, "llm_model": "deepseek-chat",
        "tavily_api_key": SEARCH_KEY}


def _models(*names, has_more=False):
    return httpx.Response(200, json={"data": [{"id": name} for name in names], "has_more": has_more})


class _Providers:
    """Answer provider requests locally and remember each one."""

    def __init__(self, llm=None, search=None):
        self.llm = llm if llm is not None else _models("deepseek-chat")
        self.search = search if search is not None else httpx.Response(200, json={"plan": "free"})
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.search if request.url.host in {"api.tavily.com", "google.serper.dev"} else self.llm
        if isinstance(answer, Exception):
            raise answer
        # A fresh object per request: one Response cannot be delivered twice.
        return httpx.Response(answer.status_code, headers=answer.headers, content=answer.content)

    @property
    def hosts(self) -> set[str]:
        return {request.url.host for request in self.requests}


def _check(providers: _Providers, **overrides) -> key_check.KeyCheck:
    args = {"provider": "deepseek", "llm_api_key": LLM_KEY, "model": "deepseek-chat",
            "search": "tavily", "search_api_key": SEARCH_KEY, **overrides}
    return asyncio.run(key_check.check(**args, transport=httpx.MockTransport(providers)))


class VerdictTests(unittest.TestCase):
    def setUp(self):
        self._env = patch.dict("os.environ", {})
        self._env.start()
        os.environ.pop("KEY_CHECK", None)

    def tearDown(self):
        self._env.stop()

    def test_accepted_keys_and_a_listed_model(self):
        providers = _Providers()
        self.assertEqual(_check(providers), key_check.KeyCheck("accepted", "listed", "accepted"))
        self.assertEqual(len(providers.requests), 2)
        self.assertTrue(all(request.method == "GET" for request in providers.requests))

    def test_a_provider_that_says_no_is_a_rejection(self):
        providers = _Providers(llm=httpx.Response(401, json={"error": {"message": f"Incorrect API key provided: {LLM_KEY}"}}),
                               search=httpx.Response(403, json={"message": "Unauthorized. Sign up for a free account."}))
        self.assertEqual(_check(providers, search="serper"), key_check.KeyCheck("rejected", "unknown", "rejected"))

    def test_a_real_key_that_may_not_list_models_is_not_called_wrong(self):
        # OpenAI issues keys with scopes; Anthropic answers 403 permission_error.
        for response in (
            httpx.Response(401, json={"error": {"message": "You have insufficient permissions for this operation. "
                                                           "Missing scopes: api.model.read."}}),
            httpx.Response(403, json={"type": "error", "error": {"type": "permission_error", "message": "Not allowed."}}),
        ):
            with self.subTest(status=response.status_code):
                self.assertEqual(_check(_Providers(llm=response)).llm, "unverified")

    def test_no_answer_is_never_a_rejection(self):
        for failure in (httpx.Response(500), httpx.Response(429), httpx.Response(404),
                        httpx.ConnectTimeout("fixture"), httpx.ConnectError("fixture"), OSError("fixture")):
            with self.subTest(failure=repr(failure)):
                result = _check(_Providers(llm=failure, search=failure))
                self.assertEqual(result, key_check.KeyCheck("unverified", "unknown", "unverified"))

    def test_one_service_failing_does_not_hide_the_other_answer(self):
        result = _check(_Providers(llm=httpx.Response(401, text="Authentication Fails"), search=httpx.ReadTimeout("fixture")))
        self.assertEqual(result, key_check.KeyCheck("rejected", "unknown", "unverified"))

    def test_a_model_the_complete_list_does_not_name_is_reported(self):
        self.assertEqual(_check(_Providers(llm=_models("deepseek-reasoner"))).model, "not_listed")

    def test_an_incomplete_or_unreadable_list_says_nothing_about_the_model(self):
        for response in (_models("deepseek-reasoner", has_more=True), httpx.Response(200, text="not json"),
                         httpx.Response(200, json={"data": []}), httpx.Response(200, json=["deepseek-chat"])):
            with self.subTest(body=response.text[:30]):
                result = _check(_Providers(llm=response))
                self.assertEqual((result.llm, result.model), ("accepted", "unknown"))

    def test_an_oversized_list_is_not_read_to_the_end(self):
        with patch.object(key_check, "_MAX_BODY_BYTES", 64):
            result = _check(_Providers(llm=_models(*[f"model-{i}" for i in range(50)], "deepseek-chat")))
        self.assertEqual((result.llm, result.model), ("accepted", "unknown"))

    def test_each_key_goes_only_to_its_own_service(self):
        cases = {
            "deepseek": ("api.deepseek.com", "/models"),
            "qwen": ("dashscope.aliyuncs.com", "/compatible-mode/v1/models"),
            "openai": ("api.openai.com", "/v1/models"),
            "anthropic": ("api.anthropic.com", "/v1/models"),
        }
        for provider, (host, path) in cases.items():
            for search, search_host in (("tavily", "api.tavily.com"), ("serper", "google.serper.dev")):
                with self.subTest(provider=provider, search=search):
                    providers = _Providers(llm=_models("m"))
                    _check(providers, provider=provider, model="m", search=search)
                    self.assertEqual(providers.hosts, {host, search_host})
                    llm, found = sorted(providers.requests, key=lambda r: r.url.host != host)
                    self.assertEqual((llm.url.scheme, llm.url.path), ("https", path))
                    # Each key is in exactly one request, and never in a URL.
                    self.assertNotIn(SEARCH_KEY, str(dict(llm.headers)))
                    self.assertNotIn(LLM_KEY, str(dict(found.headers)))
                    self.assertFalse(any(key in str(r.url) for r in providers.requests for key in (LLM_KEY, SEARCH_KEY)))
                    if provider == "anthropic":
                        self.assertEqual(llm.headers["x-api-key"], LLM_KEY)
                        self.assertIn("anthropic-version", llm.headers)
                        self.assertNotIn("authorization", llm.headers)
                    else:
                        self.assertEqual(llm.headers["authorization"], f"Bearer {LLM_KEY}")
                    expected = {"x-api-key": SEARCH_KEY} if search == "serper" else {"authorization": f"Bearer {SEARCH_KEY}"}
                    for name, value in expected.items():
                        self.assertEqual(found.headers[name], value)

    def test_an_operator_endpoint_never_receives_a_visitors_key(self):
        # The deployment may route its own Qwen traffic through a gateway.
        # A key the account typed must still go to the provider itself.
        with patch.dict("os.environ", {"QWEN_API_BASE": "https://gateway.example.com/v1",
                                       "OPENAI_API_BASE": "https://gateway.example.com/v1"}):
            providers = _Providers(llm=_models("qwen3.8-flash"))
            _check(providers, provider="qwen", model="qwen3.8-flash")
        self.assertEqual(providers.hosts, {"dashscope.aliyuncs.com", "api.tavily.com"})

    def test_a_redirect_is_not_followed(self):
        redirect = httpx.Response(302, headers={"Location": "https://elsewhere.example.com/collect"})
        providers = _Providers(llm=redirect, search=redirect)
        self.assertEqual(_check(providers), key_check.KeyCheck("unverified", "unknown", "unverified"))
        self.assertEqual(providers.hosts, {"api.deepseek.com", "api.tavily.com"})

    def test_a_key_that_cannot_be_a_key_is_refused_without_a_request(self):
        for broken in ("sk-with a space", "sk-line\nbreak", "sk-密钥", "x" * 401):
            with self.subTest(key=broken[:12]):
                providers = _Providers()
                result = _check(providers, llm_api_key=broken, search_api_key=broken)
                self.assertEqual((result.llm, result.search), ("rejected", "rejected"))
                self.assertEqual(providers.requests, [])

    def test_turned_off_it_asks_nobody(self):
        for value in ("off", "0", "false", "OFF "):
            with self.subTest(value=value), patch.dict("os.environ", {"KEY_CHECK": value}):
                providers = _Providers()
                self.assertFalse(key_check.enabled())
                self.assertEqual(_check(providers), key_check.KeyCheck("unverified", "unknown", "unverified"))
                self.assertEqual(providers.requests, [])
        self.assertTrue(key_check.enabled())


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._env = patch.dict("os.environ", {"ACCOUNTS_DB": str(Path(self._tmp.name) / "accounts.sqlite3")})
        self._env.start()
        for name in ("ACCOUNTS_SIGNUP", "ACCOUNTS_ADMIN_EMAILS", "KEY_CHECK"):
            os.environ.pop(name, None)
        api_main._key_check_times.clear()
        self.client = TestClient(app)
        self.accepted = AsyncMock(return_value=key_check.KeyCheck("accepted", "listed", "accepted"))
        self._check = patch.object(key_check, "check", self.accepted)
        self._check.start()

    def tearDown(self):
        self._check.stop()
        self.client.close()
        self._env.stop()
        self._tmp.cleanup()
        api_main._key_check_times.clear()

    def _account(self, email="alice@example.com"):
        response = self.client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
        self.assertEqual(response.status_code, 201, response.text)
        return {"Authorization": f"Bearer {response.json()['token']}"}

    def test_a_signed_in_account_gets_the_providers_answer_and_no_key(self):
        self.accepted.return_value = key_check.KeyCheck("rejected", "unknown", "accepted")
        response = self.client.post("/api/keys/check", json=KEYS, headers=self._account())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"checked": True, "llm": "rejected", "model": "unknown", "search": "accepted"})
        self.assertNotIn(LLM_KEY, response.text)
        self.assertNotIn(SEARCH_KEY, response.text)
        self.assertEqual(self.accepted.await_args.kwargs, {
            "provider": "deepseek", "llm_api_key": LLM_KEY, "model": "deepseek-chat",
            "search": "tavily", "search_api_key": SEARCH_KEY})

    def test_it_is_not_offered_to_anyone_but_an_account(self):
        # Anonymous: the gate refuses before the handler. A code holder passes
        # the gate and is told this is for accounts. Neither reaches a provider.
        self.assertEqual(self.client.post("/api/keys/check", json=KEYS).status_code, 401)
        with patch.object(access, "ACCESS_CODE", "code-1"):
            self.assertEqual(self.client.post("/api/keys/check", json=KEYS).status_code, 401)
            coded = self.client.post("/api/keys/check", json=KEYS, headers={"X-Access-Code": "code-1"})
        self.assertEqual(coded.status_code, 404)
        self.accepted.assert_not_awaited()

    def test_without_accounts_the_endpoint_answers_nobody(self):
        os.environ.pop("ACCOUNTS_DB", None)
        self.assertEqual(self.client.post("/api/keys/check", json=KEYS).status_code, 404)
        self.accepted.assert_not_awaited()

    def test_an_incomplete_or_malformed_key_set_is_refused_before_any_request(self):
        headers = self._account()
        for body in (
            {k: v for k, v in KEYS.items() if k != "tavily_api_key"},
            {**KEYS, "serper_api_key": "both"},
            {**KEYS, "llm_provider": "elsewhere"},
            {**KEYS, "llm_model": "https://evil.example.com/v1"},
            {**KEYS, "llm_api_key": "x" * 401},
            {},
        ):
            with self.subTest(body=sorted(body)):
                response = self.client.post("/api/keys/check", json=body, headers=headers)
                self.assertEqual(response.status_code, 422, response.text)
                # The framework's own refusal would quote the body, keys and all.
                self.assertNotIn("SECRET", response.text)
        for raw in (b"not json", b"[]", b'"keys"'):
            with self.subTest(raw=raw):
                response = self.client.post("/api/keys/check", content=raw, headers=headers)
                self.assertEqual(response.status_code, 422, response.text)
        oversized = self.client.post("/api/keys/check", content=b'{"pad": "' + b"x" * 9000 + b'"}', headers=headers)
        self.assertEqual(oversized.status_code, 413)
        self.accepted.assert_not_awaited()

    def test_checks_are_bounded_per_account(self):
        alice, bob = self._account(), self._account("bob@example.com")
        for _ in range(api_main._KEY_CHECK_LIMIT):
            self.assertEqual(self.client.post("/api/keys/check", json=KEYS, headers=alice).status_code, 200)
        refused = self.client.post("/api/keys/check", json=KEYS, headers=alice)
        self.assertEqual(refused.status_code, 429)
        self.assertEqual(refused.headers["X-Error-Code"], "rate_limited")
        self.assertEqual(self.accepted.await_count, api_main._KEY_CHECK_LIMIT)
        # One account's limit is not another's.
        self.assertEqual(self.client.post("/api/keys/check", json=KEYS, headers=bob).status_code, 200)
        # The window slides: checks older than it stop counting.
        with api_main._key_check_lock:
            for times in api_main._key_check_times.values():
                aged = [seen - api_main._KEY_CHECK_WINDOW - 1 for seen in times]
                times.clear()
                times.extend(aged)
        self.assertEqual(self.client.post("/api/keys/check", json=KEYS, headers=alice).status_code, 200)

    def test_turned_off_it_says_so_and_asks_nobody(self):
        headers = self._account()
        with patch.dict("os.environ", {"KEY_CHECK": "off"}):
            response = self.client.post("/api/keys/check", json=KEYS, headers=headers)
            config = self.client.get("/api/auth/config").json()
            access_check = self.client.get("/api/access/check", headers=headers).json()
        self.assertEqual(response.json(), {"checked": False, "llm": "unverified", "model": "unknown", "search": "unverified"})
        self.accepted.assert_not_awaited()
        self.assertIs(config["key_check"], False)
        self.assertIs(access_check["accounts"]["key_check"], False)

    def test_the_page_is_told_the_check_exists(self):
        headers = self._account()
        self.assertIs(self.client.get("/api/auth/config").json()["key_check"], True)
        self.assertIs(self.client.get("/api/access/check", headers=headers).json()["accounts"]["key_check"], True)
        refusal = self.client.get("/api/runs")
        self.assertEqual(refusal.status_code, 401)
        self.assertIs(refusal.json()["accounts"]["key_check"], True)

    def test_the_real_check_runs_behind_the_endpoint_without_leaking(self):
        # End to end through the handler, with only the transport replaced.
        self._check.stop()
        providers = _Providers(llm=httpx.Response(401, json={"error": {"message": f"Incorrect API key provided: {LLM_KEY}"}}))
        real = key_check.check

        async def with_transport(**kwargs):
            return await real(**kwargs, transport=httpx.MockTransport(providers))

        headers = self._account()
        records: list[logging.LogRecord] = []
        handler = logging.Handler()
        handler.emit = records.append
        root = logging.getLogger()
        level = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        try:
            with patch.object(key_check, "check", with_transport):
                response = self.client.post("/api/keys/check", json=KEYS, headers=headers)
        finally:
            root.setLevel(level)
            root.removeHandler(handler)
            self._check.start()
        # Whatever the server and its HTTP client logged, at any level, names no key.
        self.assertFalse([record.getMessage() for record in records if "SECRET" in record.getMessage()])
        self.assertEqual(response.json(), {"checked": True, "llm": "rejected", "model": "unknown", "search": "accepted"})
        self.assertNotIn("SECRET", response.text)
        self.assertEqual(providers.hosts, {"api.deepseek.com", "api.tavily.com"})
        self.assertEqual(json.loads(response.text)["llm"], "rejected")


if __name__ == "__main__":
    unittest.main()
