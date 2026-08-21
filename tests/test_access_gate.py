"""Tests for the public-deployment access gate and paid-operation caps.

Both exist for the same reason: an interviewer-facing demo link is public
enough that anyone who finds it could trigger LLM and Serper calls billed to
the project owner. The gate (api/access.py + the middleware in api/main.py)
keeps an anonymous visitor out entirely; the concurrency and daily caps
(api/runs.py) bound both full runs and inline PDF extraction if a shared code
ever leaks. Neither exists, and neither test matters, once ACCESS_CODE is
unset — which is the default, so local development and every prior test in
this suite see no gate at all.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import threading
from datetime import date, timedelta
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import Request, UploadFile
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api import access, papers, runs
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


class AdminCodeTests(unittest.TestCase):
    """access.is_admin() — the one code exempted from per-code history
    isolation, so its holder can see every code's usage at a glance."""

    def test_admin_code_is_recognized(self):
        with patch.object(access, "ADMIN_CODE", "the-admin-code"):
            self.assertTrue(access.is_admin("the-admin-code"))

    def test_a_different_code_is_not_admin(self):
        with patch.object(access, "ADMIN_CODE", "the-admin-code"):
            self.assertFalse(access.is_admin("some-other-code"))

    def test_no_admin_configured_nothing_is_admin(self):
        with patch.object(access, "ADMIN_CODE", None):
            self.assertFalse(access.is_admin("anything"))

    def test_admin_code_also_authorizes_like_any_other_code(self):
        with patch.object(access, "ACCESS_CODE", None), \
             patch.object(access, "ACCESS_CODES", None), \
             patch.object(access, "ADMIN_CODE", "the-admin-code"):
            self.assertEqual(access.matching_code("the-admin-code"), "the-admin-code")
            self.assertTrue(access.gate_enabled())


class LabelForOwnerTests(unittest.TestCase):
    """access.label_for_owner() — the admin view's way to show which code
    ran something, recovered by testing owner_id() against every code
    currently configured rather than storing the raw code a second place."""

    def test_recovers_the_code_that_produced_the_hash(self):
        with patch.object(access, "ACCESS_CODE", None), \
             patch.object(access, "ACCESS_CODES", "for-alice,for-bob"):
            self.assertEqual(
                access.label_for_owner(access.owner_id("for-alice")), "for-alice"
            )
            self.assertEqual(
                access.label_for_owner(access.owner_id("for-bob")), "for-bob"
            )

    def test_none_owner_is_none(self):
        self.assertIsNone(access.label_for_owner(None))

    def test_a_rotated_out_code_resolves_to_none(self):
        """The run still exists on disk with its old hash; the code that
        made it no longer being configured must not raise or mismatch."""
        stale_hash = access.owner_id("code-nobody-has-anymore")
        with patch.object(access, "ACCESS_CODE", None), \
             patch.object(access, "ACCESS_CODES", "for-alice"):
            self.assertIsNone(access.label_for_owner(stale_hash))


class MisconfigurationWarningTests(unittest.TestCase):
    """access._warn_if_misconfigured() — catches the exact mistake that
    motivated it: pasting `ACCESS_CODES=a,b,c` whole, prefix and all, into a
    field meant to hold just the codes."""

    def _warning_text(self, **patched):
        with patch.object(access, "ACCESS_CODE", patched.get("ACCESS_CODE")), \
             patch.object(access, "ACCESS_CODES", patched.get("ACCESS_CODES")), \
             patch.object(access, "ADMIN_CODE", patched.get("ADMIN_CODE")), \
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
        # Both registries are one capacity boundary and must be isolated alike.
        runs._registry.clear()
        runs._inline_paid_operations.clear()
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
        runs._inline_paid_operations.clear()


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

    def test_launch_failure_refunds_an_unspent_daily_slot(self):
        """A failure before Popen succeeds cannot have reached a paid API.

        The concurrency reservation was already rolled back on this path, but
        the daily charge was not. A transient filesystem or process-launch
        failure could therefore exhaust a code's entire day without starting
        a single worker.
        """
        with patch.object(runs, "DAILY_CAP", 1), \
             patch.object(runs, "MAX_CONCURRENT", 100):
            with patch("api.runs.subprocess.Popen", side_effect=OSError("cannot spawn")):
                with self.assertRaises(OSError):
                    runs.start_run("never launched", owner="alice")

            with patch("api.runs.subprocess.Popen", _FakeProc):
                runs.start_run("first billable attempt", owner="alice")


class PaperPaidBoundaryTests(_RunLifecycleTestBase):
    """PDF extraction and full runs draw from one paid-operation boundary.

    Upload parsing itself is local work. The boundary begins immediately
    before extraction reaches the LLM, and it must protect both the operator's
    budget and the finite upstream/host concurrency shared with worker runs.
    """

    def setUp(self):
        super().setUp()
        self.addCleanup(setattr, runs, "_daily_counts", dict(runs._daily_counts))
        self.addCleanup(setattr, runs, "_daily_date", runs._daily_date)
        runs._daily_counts = {}
        runs._daily_date = None

        paper_root = Path(self._tmp.name) / "_papers"
        paper_patcher = patch.object(papers, "PAPERS_ROOT", paper_root)
        paper_patcher.start()
        self.addCleanup(paper_patcher.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    @staticmethod
    def _contribution():
        from academic_agent.pdf_extractor import PaperContribution

        return PaperContribution(
            title="A bounded extraction",
            core_contribution="x" * 25,
            application_domain="energy storage",
            delta_from_prior="y" * 15,
            commercialization_topic="z" * 15,
            search_keywords=["a", "b", "c"],
        )

    def _upload(self, *, code: str | None = None, byok: bool = False):
        headers = {"X-Access-Code": code} if code else {}
        data = (
            {"llm_provider": "deepseek", "llm_api_key": "visitor-key"}
            if byok else {}
        )
        return self.client.post(
            "/api/papers",
            headers=headers,
            data=data,
            files={"file": ("paper.pdf", b"%PDF-1.4 body", "application/pdf")},
        )

    def test_operator_pdf_extraction_spends_the_same_daily_budget_as_a_run(self):
        """The upload endpoint used to make an unmetered server-key LLM call."""
        with patch.object(access, "ACCESS_CODE", "alice-code"), \
             patch.object(runs, "DAILY_CAP", 1), \
             patch.object(runs, "MAX_CONCURRENT", 10), \
             patch("api.main.extract_paper_contribution", return_value=self._contribution()), \
             patch("api.runs.subprocess.Popen", _FakeProc):
            extracted = self._upload(code="alice-code")
            submitted = self.client.post(
                "/api/runs",
                headers={"X-Access-Code": "alice-code"},
                json={"topic": "a valid research topic"},
            )

        self.assertEqual(extracted.status_code, 200)
        self.assertEqual(submitted.status_code, 429)
        self.assertIn("daily", submitted.json()["detail"].lower())

    def test_active_run_blocks_pdf_before_the_extractor_is_called(self):
        """The two paid paths must share concurrency, not only a quota name."""
        with patch.object(access, "ACCESS_CODE", "alice-code"), \
             patch.object(runs, "DAILY_CAP", 0), \
             patch.object(runs, "MAX_CONCURRENT", 1), \
             patch("api.runs.subprocess.Popen", _FakeProc):
            submitted = self.client.post(
                "/api/runs",
                headers={"X-Access-Code": "alice-code"},
                json={"topic": "a valid research topic"},
            )
            with patch(
                "api.main.extract_paper_contribution",
                return_value=self._contribution(),
            ) as extractor:
                extracted = self._upload(code="alice-code")

        self.assertEqual(submitted.status_code, 202)
        self.assertEqual(extracted.status_code, 429)
        extractor.assert_not_called()
        self.assertFalse(papers.PAPERS_ROOT.exists() and any(papers.PAPERS_ROOT.iterdir()))

    def test_inline_reservation_blocks_a_run_and_reaches_the_health_payload(self):
        """The shared slot must work in both directions and reach the client.

        The inverse seam is already covered above (a run blocks extraction).
        This proves an inline call blocks run admission and that the health
        response does not silently report a free slot merely because inline
        calls do not have run ids.
        """
        with patch.object(access, "ACCESS_CODE", "alice-code"), \
             patch.object(runs, "DAILY_CAP", 0), \
             patch.object(runs, "MAX_CONCURRENT", 1), \
             patch("api.runs.subprocess.Popen") as popen:
            with runs.reserve_inline_paid_operation(owner="alice", byok=False):
                capacity = self.client.get("/health").json()
                submitted = self.client.post(
                    "/api/runs",
                    headers={"X-Access-Code": "alice-code"},
                    json={"topic": "a valid research topic"},
                )

        self.assertEqual(capacity["active_runs"], 0)
        self.assertEqual(capacity["active_paid_operations"], 1)
        self.assertEqual(submitted.status_code, 429)
        popen.assert_not_called()

    def test_failed_extraction_releases_its_shared_concurrency_slot(self):
        """A provider failure may spend budget but must never leak capacity.

        DAILY_CAP is disabled here on purpose: once extraction begins the API
        cannot prove that a failed provider request was unbilled, so the daily
        admission remains spent. This test isolates the independently safe
        guarantee that the in-process concurrency reservation is released.
        """
        with patch.object(access, "ACCESS_CODE", "alice-code"), \
             patch.object(runs, "DAILY_CAP", 0), \
             patch.object(runs, "MAX_CONCURRENT", 1), \
             patch(
                 "api.main.extract_paper_contribution",
                 side_effect=RuntimeError("provider failed after admission"),
             ), \
             patch("api.runs.subprocess.Popen", _FakeProc):
            failed = self._upload(code="alice-code")
            submitted = self.client.post(
                "/api/runs",
                headers={"X-Access-Code": "alice-code"},
                json={"topic": "a valid research topic"},
            )

        self.assertEqual(failed.status_code, 422)
        self.assertEqual(submitted.status_code, 202)
        self.assertEqual(runs._inline_paid_operations, {})

    def test_cancelled_waiter_keeps_the_slot_until_its_thread_finishes(self):
        """Cancelling asyncio.to_thread does not stop the provider call.

        The reservation must therefore live inside that thread. Releasing it
        with the cancelled request task would admit another paid operation
        while the abandoned extraction was still running upstream.
        """
        from api import main

        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()

        def blocking_extractor(*_args, **_kwargs):
            started.set()
            try:
                if not release.wait(timeout=2):
                    raise TimeoutError("test did not release extractor")
                return self._contribution()
            finally:
                finished.set()

        async def exercise_cancellation():
            request = Request({
                "type": "http",
                "method": "POST",
                "path": "/api/papers",
                "headers": [],
                "query_string": b"",
                "client": ("test", 123),
                "server": ("test", 80),
                "scheme": "http",
                "http_version": "1.1",
            })
            upload = UploadFile(
                file=io.BytesIO(b"%PDF-1.4 body"),
                filename="paper.pdf",
            )
            task = asyncio.create_task(
                main.upload_paper(
                    request,
                    file=upload,
                    llm_provider="deepseek",
                    llm_api_key="visitor-key",
                )
            )
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 1))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertEqual(runs.active_paid_operation_count(), 1)
            finally:
                release.set()
                await upload.close()

            self.assertTrue(await asyncio.to_thread(finished.wait, 1))
            for _ in range(100):
                if runs.active_paid_operation_count() == 0:
                    break
                await asyncio.sleep(0.001)
            self.assertEqual(runs.active_paid_operation_count(), 0)

        with patch.object(runs, "DAILY_CAP", 0), \
             patch.object(runs, "MAX_CONCURRENT", 1), \
             patch.object(runs, "BYOK_MAX_CONCURRENT", 1), \
             patch("api.main.extract_paper_contribution", side_effect=blocking_extractor):
            asyncio.run(exercise_cancellation())

    def test_byok_pdf_is_daily_cap_exempt_but_not_resource_cap_exempt(self):
        """Who pays changes the wallet limit, never the host/upstream limit."""
        with patch.object(access, "ACCESS_CODE", "alice-code"), \
             patch.object(runs, "DAILY_CAP", 1), \
             patch.object(runs, "MAX_CONCURRENT", 2), \
             patch.object(runs, "BYOK_MAX_CONCURRENT", 1), \
             patch("api.runs.subprocess.Popen", _FakeProc), \
             patch("api.main.extract_paper_contribution", return_value=self._contribution()):
            byok = runs.BYOKCredentials("deepseek", "visitor-key", "search-key")
            runs.start_run("visitor run", byok=byok)
            extracted = self._upload(byok=True)

        self.assertEqual(extracted.status_code, 429)

        # The refused BYOK extraction did not consume the operator's daily
        # budget. End the synthetic visitor run so only that rule is tested.
        runs._registry.clear()
        with patch.object(runs, "DAILY_CAP", 1), \
             patch.object(runs, "MAX_CONCURRENT", 2), \
             patch("api.runs.subprocess.Popen", _FakeProc):
            runs.start_run("operator run", owner="alice")


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

    def test_cancelling_a_byok_run_needs_no_code_either(self):
        """A BYOK run carries no owner tag and its submitter holds no code,
        so the id stays its only credential."""
        with patch.object(access, "ACCESS_CODE", "secret123"):
            created = self.client.post("/api/runs", json=self._byok_body())
            run_id = created.json()["run_id"]
            r = self.client.delete(f"/api/runs/{run_id}")
        self.assertEqual(r.status_code, 200)


class DestructiveAuthorizationTests(_RunLifecycleTestBase):
    """Reading a run by id is deliberately open — that is the report-sharing
    model. Destroying one is not: DELETE now permanently removes a finished
    run's report and every artifact with it, so a forwarded link must not
    carry the power to do that.
    """

    def setUp(self):
        super().setUp()
        popen_patcher = patch("api.runs.subprocess.Popen", _FakeProc)
        popen_patcher.start()
        self.addCleanup(popen_patcher.stop)
        self.client = TestClient(app)

    def _make_run(self, code: str) -> str:
        with patch.object(access, "ACCESS_CODE", code):
            created = self.client.post(
                "/api/runs",
                json={"topic": "a valid research topic"},
                headers={"X-Access-Code": code},
            )
        return created.json()["run_id"]

    def test_a_leaked_run_id_alone_cannot_delete(self):
        """The regression this class exists for: before object-level
        authorization, knowing the id was enough to destroy the run."""
        run_id = self._make_run("alice-code")
        with patch.object(access, "ACCESS_CODE", "alice-code"):
            r = self.client.delete(f"/api/runs/{run_id}")
        self.assertEqual(r.status_code, 404)
        self.assertTrue(runs.run_dir_for(run_id).is_dir(), "run was destroyed")

    def test_another_code_cannot_delete_someone_elses_run(self):
        run_id = self._make_run("alice-code")
        with patch.object(access, "ACCESS_CODES", "alice-code,bob-code"), \
             patch.object(access, "ACCESS_CODE", None):
            r = self.client.delete(
                f"/api/runs/{run_id}", headers={"X-Access-Code": "bob-code"}
            )
        self.assertEqual(r.status_code, 404)
        self.assertTrue(runs.run_dir_for(run_id).is_dir(), "run was destroyed")

    def test_unauthorized_delete_is_indistinguishable_from_a_missing_run(self):
        """404 rather than 403 — a distinct 'forbidden' would confirm which
        ids exist, which is the one thing a 40-bit id cannot afford to leak."""
        run_id = self._make_run("alice-code")
        absent = "20260101T000000Z-ffffffffff"
        with patch.object(access, "ACCESS_CODE", "alice-code"):
            denied = self.client.delete(f"/api/runs/{run_id}")
            missing = self.client.delete(f"/api/runs/{absent}")
        self.assertEqual(denied.status_code, missing.status_code)
        # Same template, each naming only the id the caller already supplied —
        # so the reply carries nothing that distinguishes "exists but is not
        # yours" from "does not exist".
        self.assertEqual(denied.json()["detail"], f"No run with id {run_id}")
        self.assertEqual(missing.json()["detail"], f"No run with id {absent}")

    def test_the_owning_code_can_still_delete(self):
        run_id = self._make_run("alice-code")
        with patch.object(access, "ACCESS_CODE", "alice-code"):
            r = self.client.delete(
                f"/api/runs/{run_id}", headers={"X-Access-Code": "alice-code"}
            )
        self.assertEqual(r.status_code, 200)

    def test_admin_can_delete_any_code_s_run(self):
        run_id = self._make_run("alice-code")
        with patch.object(access, "ACCESS_CODE", "alice-code"), \
             patch.object(access, "ADMIN_CODE", "admin-code"):
            r = self.client.delete(
                f"/api/runs/{run_id}", headers={"X-Access-Code": "admin-code"}
            )
        self.assertEqual(r.status_code, 200)

    def test_reading_a_run_by_id_stays_open(self):
        """The sharing model must survive the fix — locking reads down too
        would break every already-shared report link."""
        run_id = self._make_run("alice-code")
        with patch.object(access, "ACCESS_CODE", "alice-code"):
            r = self.client.get(f"/api/runs/{run_id}")
        self.assertEqual(r.status_code, 200)

    def test_no_gate_configured_leaves_delete_open(self):
        """Local development has no code to authorize against; the check must
        not turn into a lockout there."""
        created = self.client.post(
            "/api/runs", json={"topic": "a valid research topic"}
        )
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

    def test_admin_code_sees_every_codes_runs_combined(self):
        with patch.object(access, "ACCESS_CODES", "for-alice,for-bob"), \
             patch.object(access, "ADMIN_CODE", "for-the-operator"):
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

            admin_view = self.client.get(
                "/api/runs", headers={"X-Access-Code": "for-the-operator"}
            ).json()
            # The admin code must not have muddied its holder's own filtered
            # view for anyone else — alice still sees only her own.
            alice_view = self.client.get(
                "/api/runs", headers={"X-Access-Code": "for-alice"}
            ).json()

        self.assertEqual(
            sorted(r["topic"] for r in admin_view["runs"]),
            ["alice's topic", "bob's topic"],
        )
        self.assertEqual([r["topic"] for r in alice_view["runs"]], ["alice's topic"])

    def test_admin_view_labels_each_run_with_its_code(self):
        """The whole point of the admin view: an unlabelled merge answers
        "what ran", not "who ran it"."""
        with patch.object(access, "ACCESS_CODES", "for-alice,for-bob"), \
             patch.object(access, "ADMIN_CODE", "for-the-operator"):
            alice_run = self.client.post(
                "/api/runs", json={"topic": "alice's topic"},
                headers={"X-Access-Code": "for-alice"},
            ).json()
            self._write_topic(alice_run["run_id"], "alice's topic")

            admin_view = self.client.get(
                "/api/runs", headers={"X-Access-Code": "for-the-operator"}
            ).json()
            alice_view = self.client.get(
                "/api/runs", headers={"X-Access-Code": "for-alice"}
            ).json()

        self.assertEqual(admin_view["runs"][0]["owner_label"], "for-alice")
        # A non-admin's own list needs no label — every entry is already
        # known to be their own.
        self.assertIsNone(alice_view["runs"][0]["owner_label"])

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
