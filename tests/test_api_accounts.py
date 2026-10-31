"""Accounts over HTTP: sign-up, sign-in, and what a signed-in account may do.

The rules under test are the product's: an account scopes history to itself,
pays for runs with its own keys and never with the deployment's, and sits
beside the access code without displacing it. A deployment with ACCOUNTS_DB
unset must see none of this.
"""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import access, accounts, runs
from api.main import app

PASSWORD = "a sufficiently long password"
BYOK = {"llm_provider": "deepseek", "llm_api_key": "k", "llm_model": "deepseek-chat", "tavily_api_key": "t"}


class _AccountsHttp(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._env = patch.dict("os.environ", {"ACCOUNTS_DB": str(Path(self._tmp.name) / "accounts.sqlite3")})
        self._env.start()
        for name in ("ACCOUNTS_SIGNUP", "ACCOUNTS_ADMIN_EMAILS"):
            os.environ.pop(name, None)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self._env.stop()
        self._tmp.cleanup()

    def _signup(self, email="alice@example.com", password=PASSWORD, invite=None):
        body = {"email": email, "password": password, **({"invite": invite} if invite else {})}
        response = self.client.post("/api/auth/register", json=body)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    @staticmethod
    def _bearer(token):
        return {"Authorization": f"Bearer {token}"}


class DisabledTests(unittest.TestCase):
    """With ACCOUNTS_DB unset the endpoints say so and nothing else changes."""

    def setUp(self):
        self._env = patch.dict("os.environ", {})
        self._env.start()
        os.environ.pop("ACCOUNTS_DB", None)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self._env.stop()

    def test_config_says_disabled_and_the_rest_is_absent(self):
        config = self.client.get("/api/auth/config").json()
        self.assertEqual(config, {"enabled": False, "signup_open": False, "signup": "closed", "access_codes": False})
        self.assertEqual(self.client.post("/api/auth/register", json={"email": "a@b.co", "password": PASSWORD}).status_code, 404)
        self.assertEqual(self.client.post("/api/auth/login", json={"email": "a@b.co", "password": PASSWORD}).status_code, 404)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 404)
        # An ungated deployment still lists history without any header.
        with patch.object(runs, "list_runs", return_value=([], 0)) as listed:
            self.assertEqual(self.client.get("/api/runs").status_code, 200)
        self.assertIsNone(listed.call_args.kwargs["owner"])

    def test_a_code_gated_refusal_has_no_accounts_field(self):
        with patch.object(access, "ACCESS_CODE", "code-1"):
            response = self.client.get("/api/runs")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Missing or invalid access code."})

    def test_a_stray_bearer_token_is_ignored_when_accounts_are_off(self):
        with patch.object(runs, "list_runs", return_value=([], 0)):
            self.assertEqual(self.client.get("/api/runs", headers={"Authorization": "Bearer nonsense"}).status_code, 200)


class SignUpAndSignInTests(_AccountsHttp):
    def test_config_is_readable_without_credentials(self):
        self.assertEqual(self.client.get("/api/auth/config").json(),
                         {"enabled": True, "signup_open": True, "signup": "open", "access_codes": False})
        with patch.object(access, "ACCESS_CODE", "code-1"):
            self.assertTrue(self.client.get("/api/auth/config").json()["access_codes"])

    def test_the_boot_access_check_names_the_account_and_the_gate_options(self):
        session = self._signup()
        anonymous = self.client.get("/api/access/check")
        self.assertEqual(anonymous.status_code, 401)
        check = self.client.get("/api/access/check", headers=self._bearer(session["token"])).json()
        self.assertEqual(check["account"], {"email": "alice@example.com", "admin": False})
        self.assertEqual(check["accounts"], {"enabled": True, "signup_open": True, "signup": "open", "access_codes": False})
        with patch.object(access, "ACCESS_CODE", "code-1"):
            by_code = self.client.get("/api/access/check", headers={"X-Access-Code": "code-1"}).json()
        self.assertIsNone(by_code["account"])
        self.assertTrue(by_code["accounts"]["access_codes"])

    def test_register_signs_in_and_me_names_the_account(self):
        session = self._signup()
        self.assertEqual(session["email"], "alice@example.com")
        self.assertFalse(session["admin"])
        me = self.client.get("/api/auth/me", headers=self._bearer(session["token"]))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json(), {"email": "alice@example.com", "admin": False})

    def test_login_refusals_carry_stable_codes(self):
        self._signup()
        wrong = self.client.post("/api/auth/login", json={"email": "alice@example.com", "password": "not the password"})
        self.assertEqual((wrong.status_code, wrong.headers["X-Error-Code"]), (401, "invalid_credentials"))
        taken = self.client.post("/api/auth/register", json={"email": "alice@example.com", "password": PASSWORD})
        self.assertEqual((taken.status_code, taken.headers["X-Error-Code"]), (409, "email_taken"))
        weak = self.client.post("/api/auth/register", json={"email": "bob@example.com", "password": "short"})
        self.assertEqual((weak.status_code, weak.headers["X-Error-Code"]), (422, "weak_password"))
        with patch.dict("os.environ", {"ACCOUNTS_SIGNUP": "closed"}):
            closed = self.client.post("/api/auth/register", json={"email": "bob@example.com", "password": PASSWORD})
            self.assertEqual((closed.status_code, closed.headers["X-Error-Code"]), (403, "signup_closed"))
            self.assertFalse(self.client.get("/api/auth/config").json()["signup_open"])

    def test_a_reserved_admin_address_cannot_be_claimed_without_the_invite_code(self):
        with patch.dict("os.environ", {"ACCOUNTS_ADMIN_EMAILS": "ops@example.com"}):
            # No invite code configured at all: the address is simply closed.
            refused = self.client.post("/api/auth/register", json={"email": "Ops@Example.com", "password": PASSWORD})
            self.assertEqual((refused.status_code, refused.headers["X-Error-Code"]), (403, "invite_required"))
            with patch.dict("os.environ", {"ACCOUNTS_INVITE_CODE": "let-me-in"}):
                wrong = self.client.post("/api/auth/register",
                                         json={"email": "ops@example.com", "password": PASSWORD, "invite": "guess"})
                self.assertEqual((wrong.status_code, wrong.headers["X-Error-Code"]), (403, "invite_required"))
                ops = self._signup("ops@example.com", invite="let-me-in")
                self.assertTrue(ops["admin"])
            # Anyone else still registers freely in open mode.
            self._signup("bob@example.com")

    def test_invite_mode_asks_everyone_for_the_code(self):
        with patch.dict("os.environ", {"ACCOUNTS_SIGNUP": "invite", "ACCOUNTS_INVITE_CODE": "let-me-in"}):
            config = self.client.get("/api/auth/config").json()
            self.assertEqual((config["signup"], config["signup_open"]), ("invite", True))
            refused = self.client.post("/api/auth/register", json={"email": "bob@example.com", "password": PASSWORD})
            self.assertEqual((refused.status_code, refused.headers["X-Error-Code"]), (403, "invite_required"))
            self._signup("bob@example.com", invite="let-me-in")

    def test_lockout_answers_429_with_retry_after(self):
        self._signup()
        for _ in range(accounts.LOCKOUT_FAILURES):
            self.client.post("/api/auth/login", json={"email": "alice@example.com", "password": "not the password"})
        locked = self.client.post("/api/auth/login", json={"email": "alice@example.com", "password": PASSWORD})
        self.assertEqual((locked.status_code, locked.headers["X-Error-Code"]), (429, "locked"))
        self.assertEqual(locked.headers["Retry-After"], str(accounts.LOCKOUT_SECONDS))

    def test_logout_ends_the_session(self):
        token = self._signup()["token"]
        self.assertEqual(self.client.post("/api/auth/logout", headers=self._bearer(token)).status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me", headers=self._bearer(token)).status_code, 401)
        # Idempotent, and never a way to learn whether a token existed.
        self.assertEqual(self.client.post("/api/auth/logout", headers=self._bearer(token)).status_code, 401)

    def test_the_session_token_is_never_echoed_or_cached(self):
        response = self.client.post("/api/auth/login", json={"email": "x@example.com", "password": PASSWORD})
        self.assertEqual(response.status_code, 401)
        session = self._signup("y@example.com")
        self.assertNotIn(session["token"], self.client.get("/api/auth/me", headers=self._bearer(session["token"])).text)
        login = self.client.post("/api/auth/login", json={"email": "y@example.com", "password": PASSWORD})
        self.assertEqual(login.headers["Cache-Control"], "no-store")


class GateTests(_AccountsHttp):
    """Enabling accounts gates the API the way an access code does."""

    def test_anonymous_requests_are_turned_away_with_a_sign_in_message(self):
        response = self.client.get("/api/runs")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Sign in to use this deployment.")
        # The refusal carries what the gate should offer, so the page's boot
        # stays one request; without accounts the body is the bare detail.
        self.assertEqual(response.json()["accounts"],
                         {"enabled": True, "signup_open": True, "signup": "open", "access_codes": False})
        with patch.object(access, "ACCESS_CODE", "code-1"):
            self.assertEqual(self.client.get("/api/runs").json()["detail"], "Sign in, or provide a valid access code.")

    def test_a_session_passes_the_gate_and_scopes_history_to_the_account(self):
        session = self._signup()
        with patch.object(runs, "list_runs", return_value=([], 0)) as listed:
            self.assertEqual(self.client.get("/api/runs", headers=self._bearer(session["token"])).status_code, 200)
        owner = listed.call_args.kwargs["owner"]
        self.assertTrue(owner.startswith("user:"), owner)
        other = self._signup("bob@example.com")
        with patch.object(runs, "list_runs", return_value=([], 0)) as listed:
            self.client.get("/api/runs", headers=self._bearer(other["token"]))
        self.assertNotEqual(listed.call_args.kwargs["owner"], owner)

    def test_an_expired_or_garbage_token_is_anonymous(self):
        for header in ({"Authorization": "Bearer nonsense"}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer "}):
            self.assertEqual(self.client.get("/api/runs", headers=header).status_code, 401, header)

    def test_access_codes_keep_working_beside_accounts_and_win_precedence(self):
        session = self._signup()
        with patch.object(access, "ACCESS_CODE", "code-1"), patch.object(runs, "list_runs", return_value=([], 0)) as listed:
            self.assertEqual(self.client.get("/api/runs", headers={"X-Access-Code": "code-1"}).status_code, 200)
            self.assertEqual(listed.call_args.kwargs["owner"], access.owner_id("code-1"))
            self.client.get("/api/runs", headers={"X-Access-Code": "code-1", **self._bearer(session["token"])})
            self.assertEqual(listed.call_args.kwargs["owner"], access.owner_id("code-1"))

    def test_an_admin_email_sees_everyone_and_owners_are_labelled_by_email(self):
        alice = self._signup()
        with patch.dict("os.environ", {"ACCOUNTS_ADMIN_EMAILS": "ops@example.com", "ACCOUNTS_INVITE_CODE": "let-me-in"}):
            ops = self._signup("ops@example.com", invite="let-me-in")
            self.assertTrue(ops["admin"])
            summary = {"run_id": "20260101T000000Z-0123456789", "topic": "t", "state": "completed",
                       "started_at": "2026-01-01T00:00:00Z", "duration": "1m 00s",
                       "_owner": f"user:{accounts.session_user(alice['token']).id}"}
            with patch.object(runs, "list_runs", return_value=([dict(summary)], 1)) as listed:
                response = self.client.get("/api/runs", headers=self._bearer(ops["token"]))
            self.assertIsNone(listed.call_args.kwargs["owner"])
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["runs"][0]["owner_label"], "alice@example.com")


class PaidOperationTests(_AccountsHttp):
    """An account's runs are tagged to it and paid for with its own keys."""

    def setUp(self):
        super().setUp()
        self.session = self._signup()

    def test_a_run_without_keys_is_refused_as_byok_required(self):
        response = self.client.post("/api/runs", json={"topic": "a valid research topic"},
                                    headers=self._bearer(self.session["token"]))
        self.assertEqual((response.status_code, response.headers["X-Error-Code"]), (401, "byok_required"))

    def test_a_run_with_keys_is_tagged_to_the_account(self):
        with patch.object(runs, "start_run", return_value=("20260101T000000Z-0123456789", Path("."))) as started:
            response = self.client.post("/api/runs", json={"topic": "a valid research topic", **BYOK},
                                        headers=self._bearer(self.session["token"]))
        self.assertEqual(response.status_code, 202, response.text)
        kwargs = started.call_args.kwargs
        self.assertEqual(kwargs["owner"], accounts.session_user(self.session["token"]).owner)
        self.assertEqual(kwargs["byok"].llm_api_key, "k")

    def test_an_anonymous_byok_run_must_sign_in_once_accounts_exist(self):
        with patch.object(runs, "start_run") as started:
            response = self.client.post("/api/runs", json={"topic": "a valid research topic", **BYOK})
        self.assertEqual((response.status_code, response.headers["X-Error-Code"]), (401, "sign_in_required"))
        started.assert_not_called()

    def test_a_code_holder_is_still_billed_to_the_deployment(self):
        with patch.object(access, "ACCESS_CODE", "code-1"), \
                patch.object(runs, "start_run", return_value=("20260101T000000Z-0123456789", Path("."))) as started:
            response = self.client.post("/api/runs", json={"topic": "a valid research topic"},
                                        headers={"X-Access-Code": "code-1"})
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(started.call_args.kwargs["owner"], access.owner_id("code-1"))
        self.assertIsNone(started.call_args.kwargs["byok"])

    def test_accounts_have_no_operator_quota_or_plan_preview(self):
        headers = self._bearer(self.session["token"])
        self.assertIsNone(self.client.get("/api/quota", headers=headers).json())
        with patch("api.plan_preview.enabled", return_value=True):
            preview = self.client.post("/api/plan", json={"topic": "a valid research topic"}, headers=headers)
        self.assertEqual((preview.status_code, preview.headers["X-Error-Code"]), (404, "byok_required"))

    def test_only_the_owning_account_or_an_admin_may_mutate_a_run(self):
        mine = accounts.session_user(self.session["token"]).owner
        other = self._signup("bob@example.com")
        with patch.object(runs, "owner_of", return_value=mine), patch.object(runs, "delete_run") as deleted:
            self.assertEqual(self.client.delete("/api/runs/20260101T000000Z-0123456789",
                                                headers=self._bearer(other["token"])).status_code, 404)
            deleted.assert_not_called()
            self.assertIn(self.client.delete("/api/runs/20260101T000000Z-0123456789",
                                             headers=self._bearer(self.session["token"])).status_code, (200, 204))
            deleted.assert_called_once()


if __name__ == "__main__":
    unittest.main()
