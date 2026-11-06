"""A malformed request is refused without being quoted back.

The framework's reply to a malformed body includes what was sent. For a rule
about the whole body that is the whole body, so a run request with a
misspelt model name came back carrying the model key and the search key.
This file sends secrets through every route that takes a body, breaks each
request in the ways a real client breaks them, and looks for the secrets in
the reply.

It walks the routes the application actually has, so a route added later is
covered without anyone remembering this file.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from api import access, accounts, key_check, runs
from api.main import app

SECRETS = {
    "llm_api_key": "sk-SECRET-MODEL-KEY-0001",
    "tavily_api_key": "tvly-SECRET-SEARCH-KEY-0002",
    "serper_api_key": "serper-SECRET-SEARCH-KEY-0003",
    "password": "a-SECRET-password-0004",
    "current_password": "a-SECRET-password-0005",
    "new_password": "a-SECRET-password-0006",
    "invite": "an-invite-SECRET-0007",
}
_API_JS = Path(__file__).resolve().parents[1] / "web" / "static" / "js" / "api.js"


def _body_routes() -> list[tuple[str, str]]:
    found = []
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/"):
            for method in sorted(route.methods - {"GET", "HEAD", "OPTIONS", "DELETE"}):
                found.append((method, route.path.replace("{run_id}", "20261105T000000Z-" + "a" * 32)))
    return sorted(set(found))


class NoEchoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._env = patch.dict("os.environ", {"ACCOUNTS_DB": str(Path(self._tmp.name) / "accounts.sqlite3")})
        self._env.start()
        for name in ("ACCOUNTS_SIGNUP", "ACCOUNTS_ADMIN_EMAILS", "KEY_CHECK"):
            os.environ.pop(name, None)
        # Nothing here may start work or reach a provider, whatever a body turns out to be.
        self._guards = [
            patch.object(access, "ACCESS_CODE", None),
            patch.object(accounts, "LOCKOUT_FAILURES", 10 ** 6),
            patch.object(accounts, "LOCKOUT_EMAIL_FAILURES", 10 ** 6),
            patch.object(runs, "_start_run_from_spec", side_effect=AssertionError("a malformed request started a run")),
            patch.object(key_check, "check", AsyncMock(side_effect=AssertionError("a malformed request reached a provider"))),
        ]
        for guard in self._guards:
            guard.start()
        self.client = TestClient(app)
        account = self.client.post("/api/auth/register",
                                   json={"email": "alice@example.com", "password": "an ordinary long password"})
        self.assertEqual(account.status_code, 201, account.text)
        self.headers = {"Authorization": f"Bearer {account.json()['token']}"}

    def tearDown(self):
        self.client.close()
        for guard in reversed(self._guards):
            guard.stop()
        self._env.stop()
        self._tmp.cleanup()

    def _assert_no_secret(self, response, label):
        for name, secret in SECRETS.items():
            self.assertNotIn(secret, response.text, f"{label} quoted {name}")

    def test_the_request_that_started_this_is_refused_without_its_keys(self):
        body = {"topic": "solid-state batteries", "llm_provider": "deepseek", "llm_api_key": SECRETS["llm_api_key"],
                "llm_model": "a model name with spaces", "tavily_api_key": SECRETS["tavily_api_key"]}
        for path in ("/api/runs", "/api/runs/20261105T000000Z-" + "a" * 32 + "/resume"):
            with self.subTest(path=path):
                response = self.client.post(path, json=body, headers=self.headers)
                self.assertEqual(response.status_code, 422, response.text)
                self._assert_no_secret(response, path)
                # Still says what is wrong, in the three fields the API description documents.
                problems = response.json()["detail"]
                self.assertTrue(problems)
                for problem in problems:
                    self.assertEqual(set(problem), {"type", "loc", "msg"})
                self.assertIn("llm_model must be a plain model identifier", problems[0]["msg"])

    def test_no_route_quotes_a_malformed_body(self):
        whole = {"topic": "solid-state batteries", "llm_provider": "deepseek", "llm_model": "deepseek-chat",
                 "email": "bob@example.com", "rating": "useful", "comment": "fine", **SECRETS}
        # The ways a body goes wrong: a rule about the whole body, a field of
        # the wrong type, each secret itself of the wrong shape, and no object at all.
        broken = [
            {**whole, "llm_model": "a model name with spaces"},
            {**whole, "llm_provider": "nobody"},
            {**whole, "topic": 7, "email": 7},
            {key: [value] for key, value in whole.items()},
            {key: {"nested": value} for key, value in whole.items()},
            [whole],
        ]
        routes = _body_routes()
        self.assertGreaterEqual(len(routes), 9, routes)
        refused = 0
        for method, path in routes:
            for index, body in enumerate(broken):
                with self.subTest(route=f"{method} {path}", body=index):
                    # One of the routes signs the session out; each request gets a live one.
                    session = self.client.post("/api/auth/login", json={
                        "email": "alice@example.com", "password": "an ordinary long password"}).json()["token"]
                    response = self.client.request(method, path, json=body,
                                                   headers={"Authorization": f"Bearer {session}"})
                    self._assert_no_secret(response, f"{method} {path}")
                    if response.status_code == 422:
                        refused += 1
                        for problem in response.json()["detail"]:
                            if isinstance(problem, dict):
                                self.assertLessEqual(set(problem), {"type", "loc", "msg"})
        # The walk is only worth something if it actually reached the validators.
        self.assertGreaterEqual(refused, 20, refused)

    def test_a_body_that_is_not_json_is_refused_the_same_way(self):
        raw = ('{"llm_api_key": "' + SECRETS["llm_api_key"] + '", "password": "' + SECRETS["password"] + '"').encode()
        for path in ("/api/runs", "/api/auth/login", "/api/auth/delete-account", "/api/keys/check"):
            with self.subTest(path=path):
                response = self.client.post(path, content=raw,
                                            headers={**self.headers, "Content-Type": "application/json"})
                self.assertEqual(response.status_code, 422, response.text)
                self._assert_no_secret(response, path)

    def test_form_fields_of_an_upload_are_not_quoted_either(self):
        response = self.client.post("/api/papers", headers=self.headers,
                                    data={"llm_provider": "deepseek", "llm_api_key": SECRETS["llm_api_key"],
                                          "llm_model": "a model name with spaces",
                                          "tavily_api_key": SECRETS["tavily_api_key"]})
        self.assertIn(response.status_code, (400, 422), response.text)
        self._assert_no_secret(response, "/api/papers")

    def test_what_a_validator_says_is_still_delivered(self):
        # The reply is for a person fixing a request: the rule must survive.
        response = self.client.post("/api/runs", json={"topic": "ab"}, headers=self.headers)
        self.assertEqual(response.status_code, 422)
        problem = response.json()["detail"][0]
        self.assertEqual(problem["loc"], ["body", "topic"])
        self.assertEqual(problem["type"], "string_too_short")
        self.assertIn("at least 3 characters", problem["msg"])


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PageMessageTests(unittest.TestCase):
    """The page turned these refusals into the text "[object Object]"."""

    def _text(self, detail) -> str | None:
        source = _API_JS.read_text(encoding="utf-8")
        start = source.index("function validationText(detail) {")
        function = source[start:source.index("\n}\n", start) + 3]
        script = function + "\nprocess.stdout.write(JSON.stringify(validationText(JSON.parse(process.argv[1]))));"
        result = subprocess.run([shutil.which("node"), "-e", script, json.dumps(detail)],
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr[:500])
        return json.loads(result.stdout)

    def test_a_list_of_problems_becomes_sentences(self):
        self.assertEqual(
            self._text([{"type": "value_error", "loc": ["body"],
                         "msg": "Value error, llm_model must be a plain model identifier."}]),
            "llm_model must be a plain model identifier.")
        self.assertEqual(
            self._text([{"type": "string_too_short", "loc": ["body", "topic"],
                         "msg": "String should have at least 3 characters"},
                        {"type": "missing", "loc": ["body", "password"], "msg": "Field required"}]),
            "topic: String should have at least 3 characters password: Field required")

    def test_repeats_collapse_and_anything_else_is_left_to_the_caller(self):
        same = {"type": "value_error", "loc": ["body"], "msg": "Value error, One rule."}
        self.assertEqual(self._text([same, same]), "One rule.")
        for detail in ("A plain sentence.", None, {"msg": "not a list"}, [], [{"loc": ["body"]}], [None, 7]):
            with self.subTest(detail=detail):
                self.assertIsNone(self._text(detail))

    def test_the_request_helper_uses_it(self):
        source = _API_JS.read_text(encoding="utf-8")
        self.assertIn('detail = validationText(body.detail) ?? body.detail ?? "";', source)


if __name__ == "__main__":
    unittest.main()
