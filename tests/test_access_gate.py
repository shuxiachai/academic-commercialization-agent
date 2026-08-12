"""Tests for the public-deployment access gate and daily run cap.

Both exist for the same reason: an interviewer-facing demo link is public
enough that anyone who finds it could trigger LLM and Serper calls billed to
the project owner. The gate (api/access.py + the middleware in api/main.py)
keeps an anonymous visitor out entirely; the daily cap (api/runs.py) is the
fallback if a shared code ever leaks. Neither exists, and neither test
matters, once ACCESS_CODE is unset — which is the default, so local
development and every prior test in this suite see no gate at all.
"""

from __future__ import annotations

import io
import json
import os
from datetime import date, timedelta
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from api import access, runs
from api.main import app
from api.models import RunRequest


class AccessCheckTests(unittest.TestCase):
    """access.check() in isolation, no HTTP involved."""

    def test_gate_disabled_accepts_anything(self):
        with patch.object(access, "ACCESS_CODE", None):
            self.assertTrue(access.check(None))
            self.assertTrue(access.check("whatever"))

    def test_correct_code_is_accepted(self):
        with patch.object(access, "ACCESS_CODE", "secret123"):
            self.assertTrue(access.check("secret123"))

    def test_wrong_or_missing_code_is_rejected(self):
        with patch.object(access, "ACCESS_CODE", "secret123"):
            self.assertFalse(access.check("wrong"))
            self.assertFalse(access.check(None))
            self.assertFalse(access.check(""))


class MatchingCodeTests(unittest.TestCase):
    """access.matching_code() — which specific code (if any) a header
    matches, the piece submit_run() and list_runs() build their own
    authorization/scoping decisions on top of."""

    def test_no_codes_configured_matches_nothing(self):
        with patch.object(access, "ACCESS_CODE", None), \
             patch.object(access, "ACCESS_CODES", None):
            self.assertIsNone(access.matching_code(None))
            self.assertIsNone(access.matching_code("anything"))
            self.assertFalse(access.gate_enabled())

    def test_single_legacy_code_still_works(self):
        with patch.object(access, "ACCESS_CODE", "secret123"), \
             patch.object(access, "ACCESS_CODES", None):
            self.assertEqual(access.matching_code("secret123"), "secret123")
            self.assertIsNone(access.matching_code("wrong"))
            self.assertIsNone(access.matching_code(None))
            self.assertTrue(access.gate_enabled())

    def test_multiple_codes_each_match_their_own_value(self):
        with patch.object(access, "ACCESS_CODE", None), \
             patch.object(access, "ACCESS_CODES", "for-alice, for-bob"):
            self.assertEqual(access.matching_code("for-alice"), "for-alice")
            self.assertEqual(access.matching_code("for-bob"), "for-bob")
            self.assertIsNone(access.matching_code("for-carol"))

    def test_legacy_and_plural_codes_both_accepted_together(self):
        with patch.object(access, "ACCESS_CODE", "legacy"), \
             patch.object(access, "ACCESS_CODES", "for-alice"):
            self.assertEqual(access.matching_code("legacy"), "legacy")
            self.assertEqual(access.matching_code("for-alice"), "for-alice")


class OwnerIdTests(unittest.TestCase):
    """access.owner_id() — the tag that separates one code's run history
    from another's without keeping the raw code in a run directory."""

    def test_same_code_always_produces_the_same_id(self):
        self.assertEqual(access.owner_id("for-alice"), access.owner_id("for-alice"))

    def test_different_codes_produce_different_ids(self):
        self.assertNotEqual(access.owner_id("for-alice"), access.owner_id("for-bob"))

    def test_id_does_not_contain_the_raw_code(self):
        self.assertNotIn("for-alice", access.owner_id("for-alice"))


class MisconfigurationWarningTests(unittest.TestCase):
    """access._warn_if_misconfigured() — catches the exact mistake that
    motivated it: pasting `ACCESS_CODES=a,b,c` whole, prefix and all, into a
    field meant to hold just the codes."""

    def _warning_text(self, **patched):
        with patch.object(access, "ACCESS_CODE", patched.get("ACCESS_CODE")), \
             patch.object(access, "ACCESS_CODES", patched.get("ACCESS_CODES")), \
             patch("sys.stderr", new_callable=io.StringIO) as stderr:
            access._warn_if_misconfigured()
            return stderr.getvalue()

    def test_flags_a_pasted_assignment_line(self):
        text = self._warning_text(ACCESS_CODE="ACCESS_CODES=abc,def,ghi")
        self.assertIn("ACCESS_CODES=abc,def,ghi", text)

    def test_flags_it_in_the_plural_variable_too(self):
        text = self._warning_text(ACCESS_CODES="ACCESS_CODE=abc")
        self.assertIn("ACCESS_CODE=abc", text)

    def test_a_normal_code_is_silent(self):
        text = self._warning_text(ACCESS_CODES="for-alice,for-bob,ceshi")
        self.assertEqual(text, "")

    def test_no_codes_configured_is_silent(self):
        text = self._warning_text()
        self.assertEqual(text, "")


class RunRequestByokValidationTests(unittest.TestCase):
    """All three BYOK fields or none — a run must not run half on the
    deployment's dime and half on the requester's."""

    def test_omitting_all_three_is_valid(self):
        req = RunRequest(topic="a valid research topic")
        self.assertFalse(req.byok)

    def test_providing_all_three_is_valid(self):
        req = RunRequest(topic="a valid research topic", llm_provider="deepseek",
                          llm_api_key="k", serper_api_key="s")
        self.assertTrue(req.byok)

    def test_partial_byok_is_rejected(self):
        with self.assertRaises(ValidationError):
            RunRequest(topic="a valid research topic", llm_provider="deepseek")

    def test_unknown_provider_is_rejected(self):
        with self.assertRaises(ValidationError):
            RunRequest(topic="a valid research topic", llm_provider="not-a-real-provider",
                       llm_api_key="k", serper_api_key="s")


class BYOKCredentialsTests(unittest.TestCase):
    """runs.BYOKCredentials.as_env() — the only place a visitor's key touches
    process state, scoped to the env dict handed to one subprocess."""

    def test_env_var_names_match_what_llm_config_reads(self):
        for provider, expected_key in [
            ("deepseek", "DEEPSEEK_API_KEY"),
            ("openai", "OPENAI_API_KEY"),
            ("anthropic", "ANTHROPIC_API_KEY"),
        ]:
            with self.subTest(provider=provider):
                creds = runs.BYOKCredentials(provider, "llm-key", "serper-key")
                env = creds.as_env({})
                self.assertEqual(env["LLM_PROVIDER"], provider)
                self.assertEqual(env[expected_key], "llm-key")
                self.assertEqual(env["SERPER_API_KEY"], "serper-key")

    def test_as_env_does_not_mutate_the_base_dict(self):
        base = {"PATH": "/usr/bin"}
        runs.BYOKCredentials("deepseek", "k", "s").as_env(base)
        self.assertEqual(base, {"PATH": "/usr/bin"})


class _FakeProc:
    def __init__(self, *args, **kwargs):
        pass

    def poll(self):
        return None

    def terminate(self):
        pass

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 0


class _CapturingProc(_FakeProc):
    """Like _FakeProc, but records the `env` kwarg Popen was launched with —
    the only way to check what a BYOK subprocess actually received."""

    last_env: dict | None = None

    def __init__(self, *args, **kwargs):
        type(self).last_env = kwargs.get("env")
        super().__init__(*args, **kwargs)


class _RunLifecycleTestBase(unittest.TestCase):
    """Shared setup for tests that call runs.start_run() without launching a
    real subprocess or touching the real outputs/ directory."""

    def setUp(self):
        runs._registry.clear()
        self._tmp = TemporaryDirectory()
        # Order matters: open process.log handles must close before the
        # directory holding them is removed — Windows refuses to unlink a
        # file still open.
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(self._close_open_logs)
        patcher = patch.object(runs, "DEFAULT_OUTPUT_ROOT", Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _close_open_logs(self):
        for handle in list(runs._registry.values()):
            if handle.log_file is not None:
                try:
                    handle.log_file.close()
                except OSError:
                    pass
        runs._registry.clear()


class BYOKSubprocessEnvTests(_RunLifecycleTestBase):
    """The env dict a BYOK run's subprocess actually receives, and proof it
    cannot see or affect the parent process's own real keys."""

    def test_byok_env_carries_the_visitors_key_not_the_owners(self):
        with patch("api.runs.subprocess.Popen", _CapturingProc), \
             patch.dict(os.environ, {"DEEPSEEK_API_KEY": "owners-real-key"}, clear=False):
            byok = runs.BYOKCredentials("deepseek", "visitors-key", "visitors-serper-key")
            runs.start_run("topic", byok=byok)

            # Must still be checked inside the patch: patch.dict restores
            # whatever os.environ looked like before it, which on a machine
            # with no real DEEPSEEK_API_KEY set means the key is gone again
            # right after this block — that would prove nothing either way.
            self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "owners-real-key")

        env = _CapturingProc.last_env
        self.assertIsNotNone(env)
        self.assertEqual(env["LLM_PROVIDER"], "deepseek")
        self.assertEqual(env["DEEPSEEK_API_KEY"], "visitors-key")
        self.assertEqual(env["SERPER_API_KEY"], "visitors-serper-key")

    def test_non_byok_run_inherits_the_parent_environment_unchanged(self):
        """env=None tells Popen to inherit — today's behaviour, untouched."""
        with patch("api.runs.subprocess.Popen", _CapturingProc):
            runs.start_run("topic")
        self.assertIsNone(_CapturingProc.last_env)


class GateMiddlewareTests(unittest.TestCase):
    """The HTTP-level enforcement in api/main.py."""

    def setUp(self):
        self.client = TestClient(app)

    def test_health_is_never_gated(self):
        """Platform health checks poll this with no header."""
        with patch.object(access, "ACCESS_CODE", "secret123"):
            r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)

    def test_api_route_rejected_without_the_header(self):
        with patch.object(access, "ACCESS_CODE", "secret123"):
            r = self.client.get("/api/runs")
        self.assertEqual(r.status_code, 401)

    def test_api_route_rejected_with_the_wrong_code(self):
        with patch.object(access, "ACCESS_CODE", "secret123"):
            r = self.client.get("/api/runs", headers={"X-Access-Code": "nope"})
        self.assertEqual(r.status_code, 401)

    def test_api_route_allowed_with_the_right_code(self):
        with patch.object(access, "ACCESS_CODE", "secret123"):
            r = self.client.get("/api/runs", headers={"X-Access-Code": "secret123"})
        self.assertEqual(r.status_code, 200)

    def test_gate_disabled_needs_no_header(self):
        """The default for local development and self-hosting without it."""
        with patch.object(access, "ACCESS_CODE", None):
            r = self.client.get("/api/runs")
        self.assertEqual(r.status_code, 200)

    def test_access_check_endpoint_reflects_the_gate(self):
        with patch.object(access, "ACCESS_CODE", "secret123"):
            ok = self.client.get("/api/access/check", headers={"X-Access-Code": "secret123"})
            bad = self.client.get("/api/access/check")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(bad.status_code, 401)


class DailyCapTests(_RunLifecycleTestBase):
    """The fallback for a leaked code: a hard ceiling independent of
    concurrency, applied per owner rather than as one pool every code
    shares — ten people with ten separate codes should not be able to
    exhaust each other's budget."""

    def setUp(self):
        super().setUp()
        # These are module globals mutated by start_run; reset them so this
        # test file cannot leak state into whichever test runs after it.
        self.addCleanup(setattr, runs, "_daily_counts", dict(runs._daily_counts))
        self.addCleanup(setattr, runs, "_daily_date", runs._daily_date)
        runs._daily_counts = {}
        runs._daily_date = None

    def test_cap_disabled_by_default(self):
        self.assertEqual(runs.DAILY_CAP, 0)
        # A high concurrency cap isolates what this test checks: that
        # DAILY_CAP=0 never raises. The concurrency cap itself has its own
        # coverage in test_api_concurrency.py.
        with patch.object(runs, "MAX_CONCURRENT", 100), \
             patch("api.runs.subprocess.Popen", _FakeProc):
            for _ in range(5):
                runs.start_run("topic")   # must not raise DailyCapReached

    def test_cap_rejects_the_run_after_the_limit(self):
        with patch.object(runs, "DAILY_CAP", 2), \
             patch("api.runs.subprocess.Popen", _FakeProc):
            runs.start_run("t1")
            runs.start_run("t2")
            with self.assertRaises(runs.DailyCapReached):
                runs.start_run("t3")

    def test_each_owner_has_an_independent_budget(self):
        """The reason this is per-owner at all: one code exhausting its
        budget must not touch another code's, or handing out separate
        codes to separate people would not have bought them anything."""
        with patch.object(runs, "DAILY_CAP", 1), \
             patch.object(runs, "MAX_CONCURRENT", 100), \
             patch("api.runs.subprocess.Popen", _FakeProc):
            runs.start_run("alice's only run", owner="alice-hash")
            with self.assertRaises(runs.DailyCapReached):
                runs.start_run("alice's second run", owner="alice-hash")

            runs.start_run("bob's only run", owner="bob-hash")  # must not raise

    def test_cap_resets_on_a_new_utc_day(self):
        with patch.object(runs, "DAILY_CAP", 1):
            runs._daily_date = date.today() - timedelta(days=1)
            runs._daily_counts[None] = 1     # yesterday's budget, fully spent

            with patch("api.runs.subprocess.Popen", _FakeProc):
                runs.start_run("today's first run")   # must not raise

    def test_byok_runs_do_not_spend_the_daily_cap(self):
        """BYOK is billed to the requester — the cap exists only to bound
        the operator's own bill, so it has nothing to protect there."""
        with patch.object(runs, "DAILY_CAP", 1), \
             patch.object(runs, "MAX_CONCURRENT", 100), \
             patch("api.runs.subprocess.Popen", _FakeProc):
            byok = runs.BYOKCredentials("deepseek", "k", "s")
            for _ in range(5):
                runs.start_run("topic", byok=byok)     # must not raise

            runs.start_run("owner's run")              # spends the day's only slot
            with self.assertRaises(runs.DailyCapReached):
                runs.start_run("owner's second run")


class BYOKSubmissionTests(_RunLifecycleTestBase):
    """POST /api/runs authorizing itself — code OR complete BYOK — plus the
    capability-URL model for everything scoped to a specific run id.

    Not covered by the blanket path-prefix middleware in api/main.py: that
    decision needs the parsed request body, so submit_run() makes it itself.
    """

    def setUp(self):
        super().setUp()
        popen_patcher = patch("api.runs.subprocess.Popen", _FakeProc)
        popen_patcher.start()
        self.addCleanup(popen_patcher.stop)
        self.client = TestClient(app)

    def _byok_body(self, **overrides):
        body = {
            "topic": "a valid research topic",
            "llm_provider": "deepseek",
            "llm_api_key": "visitors-llm-key",
            "serper_api_key": "visitors-serper-key",
        }
        body.update(overrides)
        return body

    def test_full_byok_is_accepted_with_no_code(self):
        with patch.object(access, "ACCESS_CODE", "secret123"):
            r = self.client.post("/api/runs", json=self._byok_body())
        self.assertEqual(r.status_code, 202)

    def test_no_code_and_no_byok_is_rejected(self):
        with patch.object(access, "ACCESS_CODE", "secret123"):
            r = self.client.post("/api/runs", json={"topic": "a valid research topic"})
        self.assertEqual(r.status_code, 401)

    def test_valid_code_still_works_with_no_byok(self):
        with patch.object(access, "ACCESS_CODE", "secret123"):
            r = self.client.post(
                "/api/runs",
                json={"topic": "a valid research topic"},
                headers={"X-Access-Code": "secret123"},
            )
        self.assertEqual(r.status_code, 202)

    def test_partial_byok_fields_are_a_validation_error_not_a_401(self):
        with patch.object(access, "ACCESS_CODE", "secret123"):
            r = self.client.post(
                "/api/runs",
                json={"topic": "a valid research topic", "llm_provider": "deepseek"},
            )
        self.assertEqual(r.status_code, 422)

    def test_run_list_stays_gated_even_for_a_byok_visitor(self):
        """The one endpoint BYOK deliberately does not open: it would show
        every visitor's run history, not just the caller's own."""
        with patch.object(access, "ACCESS_CODE", "secret123"):
            self.client.post("/api/runs", json=self._byok_body())
            r = self.client.get("/api/runs")
        self.assertEqual(r.status_code, 401)

    def test_a_specific_run_is_readable_without_a_code(self):
        """Capability-URL model: knowing the id is the credential, the same
        trust model already used for sharing a finished report's link."""
        with patch.object(access, "ACCESS_CODE", "secret123"):
            created = self.client.post("/api/runs", json=self._byok_body())
            run_id = created.json()["run_id"]
            r = self.client.get(f"/api/runs/{run_id}")
        self.assertEqual(r.status_code, 200)

    def test_cancelling_a_run_needs_no_code_either(self):
        with patch.object(access, "ACCESS_CODE", "secret123"):
            created = self.client.post("/api/runs", json=self._byok_body())
            run_id = created.json()["run_id"]
            r = self.client.delete(f"/api/runs/{run_id}")
        self.assertEqual(r.status_code, 200)


class OwnerScopingTests(_RunLifecycleTestBase):
    """runs.start_run(owner=...) tags a run; list_runs(owner=...) filters by
    it — the mechanism behind giving each access code its own history."""

    @staticmethod
    def _write_topic(run_dir, topic):
        """list_runs() reads the topic from status.json, which only the real
        pipeline_worker subprocess writes — _FakeProc never does, so these
        tests write it themselves rather than seeing the "—" placeholder."""
        (run_dir / "status.json").write_text(
            json.dumps({"topic": topic}), encoding="utf-8"
        )

    def test_run_created_with_an_owner_writes_the_owner_file(self):
        with patch("api.runs.subprocess.Popen", _FakeProc):
            _run_id, run_dir = runs.start_run("topic", owner="alice-hash")
        self.assertEqual(
            (run_dir / runs._OWNER_FILE).read_text(encoding="utf-8"), "alice-hash"
        )

    def test_run_created_with_no_owner_writes_no_file(self):
        """The BYOK case, and the no-code-configured case — neither should
        leave a marker that could make the run attributable to anyone."""
        with patch("api.runs.subprocess.Popen", _FakeProc):
            _run_id, run_dir = runs.start_run("topic")
        self.assertFalse((run_dir / runs._OWNER_FILE).exists())

    def test_list_filters_to_the_given_owner(self):
        with patch("api.runs.subprocess.Popen", _FakeProc):
            _id, dir_a = runs.start_run("alice's topic", owner="alice-hash")
            self._write_topic(dir_a, "alice's topic")
            _id, dir_b = runs.start_run("bob's topic", owner="bob-hash")
            self._write_topic(dir_b, "bob's topic")

        alice_summaries, alice_total = runs.list_runs(owner="alice-hash")
        self.assertEqual([s["topic"] for s in alice_summaries], ["alice's topic"])
        self.assertEqual(alice_total, 1)

        bob_summaries, _bob_total = runs.list_runs(owner="bob-hash")
        self.assertEqual([s["topic"] for s in bob_summaries], ["bob's topic"])

    def test_no_owner_filter_shows_everything(self):
        """The no-code-configured / local-dev case: nothing to scope by."""
        with patch("api.runs.subprocess.Popen", _FakeProc):
            runs.start_run("alice's topic", owner="alice-hash")
            runs.start_run("byok topic")  # no owner at all

        _summaries, total = runs.list_runs(owner=None)
        self.assertEqual(total, 2)

    def test_a_byok_run_is_invisible_to_any_code(self):
        with patch("api.runs.subprocess.Popen", _FakeProc):
            _id, dir_a = runs.start_run("alice's topic", owner="alice-hash")
            self._write_topic(dir_a, "alice's topic")
            runs.start_run("byok topic")  # owner=None, as submit_run() passes for BYOK

        alice_summaries, _ = runs.list_runs(owner="alice-hash")
        self.assertEqual([s["topic"] for s in alice_summaries], ["alice's topic"])


class MultiCodeIsolationTests(_RunLifecycleTestBase):
    """End to end over HTTP: two different codes, each sees only its own
    submitted runs through GET /api/runs — not the fact that the gate
    accepts both codes, but that it keeps their histories apart."""

    def setUp(self):
        super().setUp()
        popen_patcher = patch("api.runs.subprocess.Popen", _FakeProc)
        popen_patcher.start()
        self.addCleanup(popen_patcher.stop)
        self.client = TestClient(app)

    def _write_topic(self, run_id, topic):
        """list_runs() reads the topic from status.json, which only the real
        pipeline_worker subprocess writes — _FakeProc never does."""
        (Path(self._tmp.name) / run_id / "status.json").write_text(
            json.dumps({"topic": topic}), encoding="utf-8"
        )

    def test_each_code_sees_only_its_own_runs(self):
        with patch.object(access, "ACCESS_CODES", "for-alice,for-bob"):
            alice_run = self.client.post(
                "/api/runs", json={"topic": "alice's topic"},
                headers={"X-Access-Code": "for-alice"},
            ).json()
            self._write_topic(alice_run["run_id"], "alice's topic")
            bob_run = self.client.post(
                "/api/runs", json={"topic": "bob's topic"},
                headers={"X-Access-Code": "for-bob"},
            ).json()
            self._write_topic(bob_run["run_id"], "bob's topic")

            alice_view = self.client.get(
                "/api/runs", headers={"X-Access-Code": "for-alice"}
            ).json()
            bob_view = self.client.get(
                "/api/runs", headers={"X-Access-Code": "for-bob"}
            ).json()

        self.assertEqual([r["topic"] for r in alice_view["runs"]], ["alice's topic"])
        self.assertEqual([r["topic"] for r in bob_view["runs"]], ["bob's topic"])

    def test_byok_run_appears_in_no_ones_list(self):
        with patch.object(access, "ACCESS_CODES", "for-alice"):
            self.client.post("/api/runs", json={
                "topic": "byok topic",
                "llm_provider": "deepseek",
                "llm_api_key": "k",
                "serper_api_key": "s",
            })
            alice_view = self.client.get(
                "/api/runs", headers={"X-Access-Code": "for-alice"}
            ).json()

        self.assertEqual(alice_view["runs"], [])


if __name__ == "__main__":
    unittest.main()
