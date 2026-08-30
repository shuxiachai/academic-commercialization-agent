"""Can this container actually run an assessment, or only serve pages?

/health answers "is the process alive", which is what a load balancer needs
and what it must keep answering under load. It returns 200 for a deployment
with no LLM key, no search key, or an outputs volume it cannot write to — all
three of which serve every page perfectly and fail every single run.

The Dockerfile's healthcheck comment claimed that such a container "is still
reported unhealthy". It was not: the check polled /health and asserted only
that the request succeeded. These pin the endpoint that makes the claim true.

The distinction has teeth now, so the tests that matter most are the ones
about what must *not* turn a container unhealthy: a busy deployment, a full
one, and one that has never had a run.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from fastapi.testclient import TestClient

from api import runs
from api.main import app, readiness
from api.runs import _OPERATOR_BILLED_ENV

_WORKING = {
    "DEEPSEEK_API_KEY": "sk-test",
    "SERPER_API_KEY": "serper-test",
}


def _only(env: dict[str, str]):
    """Patch os.environ so `env` is the only credential configuration present.

    Not clear=True: that also removes HOME, and library code called downstream
    expands ~ and raises. Only the names these checks read are cleared, which
    is also the narrower and more honest thing to be asserting on.
    """
    patched = {name: "" for name in _OPERATOR_BILLED_ENV}
    patched.update(env)
    context = mock.patch.dict(os.environ, patched)

    class _Ctx:
        def __enter__(self):
            context.__enter__()
            for name in _OPERATOR_BILLED_ENV:
                if name not in env:
                    os.environ.pop(name, None)
            return self

        def __exit__(self, *exc):
            return context.__exit__(*exc)

    return _Ctx()


class _ReadinessBase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._root = runs.DEFAULT_OUTPUT_ROOT
        runs.DEFAULT_OUTPUT_ROOT = Path(self._tmp.name)
        self.addCleanup(self._restore)

    def _restore(self):
        runs.DEFAULT_OUTPUT_ROOT = self._root
        self._tmp.cleanup()

    def _readiness(self, env: dict[str, str]):
        with _only(env):
            return readiness()


class WhatMakesItNotReadyTests(_ReadinessBase):

    def test_a_fully_configured_deployment_is_ready(self):
        status = self._readiness(_WORKING)
        self.assertTrue(status.ready, status.checks)
        self.assertEqual(status.llm_provider, "deepseek")
        self.assertEqual(status.search_provider, "serper")

    def test_a_kimi_deployment_is_ready_and_named_as_kimi(self):
        status = self._readiness(
            {
                "LLM_PROVIDER": "kimi",
                "MOONSHOT_API_KEY": "sk-kimi",
                "SERPER_API_KEY": "serper-test",
            }
        )
        self.assertTrue(status.ready, status.checks)
        self.assertEqual(status.llm_provider, "kimi")

    def test_no_llm_key_is_not_ready(self):
        """The case /health already reported, as llm_provider: null, beside
        status "ok" and a 200. Nothing acted on it."""
        status = self._readiness({"SERPER_API_KEY": "serper-test"})
        self.assertFalse(status.ready)
        self.assertNotEqual(status.checks["llm"], "ok")

    def test_no_search_key_is_not_ready(self):
        """Retrieval has no fallback: the pipeline raises before the first
        agent runs. /health never looked at this at all."""
        status = self._readiness({"DEEPSEEK_API_KEY": "sk-test"})
        self.assertFalse(status.ready)
        self.assertNotEqual(status.checks["search"], "ok")

    def test_either_search_provider_satisfies_it(self):
        status = self._readiness({"DEEPSEEK_API_KEY": "sk-test", "TAVILY_API_KEY": "tv"})
        self.assertTrue(status.ready, status.checks)
        self.assertEqual(status.search_provider, "tavily")

    def test_an_unwritable_outputs_directory_is_not_ready(self):
        """The failure the other two cannot catch: every key is right, the
        page loads, and each run dies at its first write. Probed with a real
        file because permission bits and what the filesystem allows are not
        the same question — a read-only mount reports neither."""
        with mock.patch.object(Path, "write_text", side_effect=OSError("read-only file system")):
            status = self._readiness(_WORKING)
        self.assertFalse(status.ready)
        self.assertIn("not writable", status.checks["outputs"])

    def test_every_failing_check_names_itself(self):
        """An operator watching a deploy refuse to go healthy needs to know
        which checks failed, not merely how many."""
        status = self._readiness({})
        failing = [name for name, value in status.checks.items() if value != "ok"]
        self.assertEqual(sorted(failing), ["llm", "search"])
        for name in failing:
            with self.subTest(check=name):
                self.assertGreater(len(status.checks[name]), 10)

    def test_corrupt_enabled_paid_ledger_is_not_ready(self):
        """Admission already fails closed on this file. Readiness must expose
        the same boundary before a visitor spends time preparing a run."""
        ledger = Path(self._tmp.name) / runs._DAILY_LEDGER_FILENAME
        ledger.write_text("{broken", encoding="utf-8")

        with mock.patch.object(runs, "DAILY_CAP", 3):
            status = self._readiness(_WORKING)

        self.assertFalse(status.ready)
        self.assertNotEqual(status.checks["paid_accounting"], "ok")
        self.assertNotIn(str(ledger), status.checks["paid_accounting"])

    def test_enabled_paid_ledger_needs_no_preexisting_file(self):
        """A first deployment has not admitted paid work and has no ledger."""
        with mock.patch.object(runs, "DAILY_CAP", 3):
            status = self._readiness(_WORKING)

        self.assertTrue(status.ready, status.checks)
        self.assertEqual(status.checks["paid_accounting"], "ok")

    def test_corrupt_ledger_is_irrelevant_when_daily_cap_is_disabled(self):
        ledger = Path(self._tmp.name) / runs._DAILY_LEDGER_FILENAME
        ledger.write_text("{broken", encoding="utf-8")

        with mock.patch.object(runs, "DAILY_CAP", 0):
            status = self._readiness(_WORKING)

        self.assertTrue(status.ready, status.checks)
        self.assertNotIn("paid_accounting", status.checks)


class WhatMustNotMakeItUnhealthyTests(_ReadinessBase):
    """The risk this endpoint introduces.

    It is wired to the container healthcheck, so anything it reports as not
    ready gets the container restarted. Ordinary operating conditions must
    never do that.
    """

    def test_a_deployment_at_its_concurrency_cap_is_still_ready(self):
        """Busy is not broken. Reporting a full deployment as unhealthy would
        restart it mid-run, killing the very runs that filled it."""
        with mock.patch.object(runs, "active_count", return_value=runs.MAX_CONCURRENT):
            status = self._readiness(_WORKING)
        self.assertTrue(status.ready, status.checks)

    def test_a_deployment_with_no_runs_yet_is_ready(self):
        """A fresh container has no outputs directory at all. Creating it is
        part of the probe, so first boot must not read as a failure."""
        fresh = Path(self._tmp.name) / "never-created"
        runs.DEFAULT_OUTPUT_ROOT = fresh
        status = self._readiness(_WORKING)
        self.assertTrue(status.ready, status.checks)
        self.assertTrue(fresh.is_dir())

    def test_the_probe_leaves_nothing_behind(self):
        """It runs every 30 seconds forever."""
        self._readiness(_WORKING)
        leftovers = list(Path(self._tmp.name).iterdir())
        self.assertEqual(leftovers, [])


class EndpointTests(_ReadinessBase):

    def test_ready_returns_200(self):
        with _only(_WORKING):
            with TestClient(app) as client:
                response = client.get("/health/ready")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ready"])

    def test_not_ready_returns_503(self):
        """503, not a 200 with ready:false. The container healthcheck reads the
        status code and nothing else — a body nobody parses is how the old
        check ended up asserting something it did not test."""
        with _only({}):
            with TestClient(app) as client:
                response = client.get("/health/ready")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["ready"])

    def test_liveness_stays_200_when_readiness_fails(self):
        """The two must be able to disagree; that is the entire point of
        splitting them. /health is what the load balancer polls."""
        with _only({}):
            with TestClient(app) as client:
                self.assertEqual(client.get("/health").status_code, 200)
                self.assertEqual(client.get("/health/ready").status_code, 503)

    def test_corrupt_paid_ledger_reaches_the_http_boundary(self):
        """The field and 503 must survive response-model serialization."""
        ledger = Path(self._tmp.name) / runs._DAILY_LEDGER_FILENAME
        ledger.write_text("{broken", encoding="utf-8")

        with mock.patch.object(runs, "DAILY_CAP", 3), _only(_WORKING):
            with TestClient(app) as client:
                response = client.get("/health/ready")

        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertFalse(body["ready"])
        self.assertNotEqual(body["checks"]["paid_accounting"], "ok")

    def test_readiness_needs_no_access_code(self):
        """Gated, it would report every deployment with a code as unhealthy
        and restart it forever."""
        from api import access

        with mock.patch.object(access, "ACCESS_CODE", "secret"), \
                _only(_WORKING):
            with TestClient(app) as client:
                self.assertEqual(client.get("/health/ready").status_code, 200)

    def test_readiness_is_exempt_from_the_rate_limit(self):
        """Polled every 30 seconds for the life of the container. A 429 here
        restarts a healthy container."""
        from api import main

        with mock.patch.object(main, "_rate_limit_exceeded", return_value=True), \
                _only(_WORKING):
            with TestClient(app) as client:
                self.assertEqual(client.get("/health/ready").status_code, 200)
                self.assertEqual(client.get("/health").status_code, 200)
                self.assertEqual(client.get("/api/runs").status_code, 429)


class DockerfileTests(unittest.TestCase):
    """The comment and the command have to agree.

    They did not, for as long as the healthcheck existed: the comment said a
    container that could not run an assessment would be reported unhealthy,
    and the command polled an endpoint that returns 200 in exactly that case.
    """

    def test_the_healthcheck_polls_readiness(self):
        dockerfile = (Path(__file__).resolve().parent.parent / "Dockerfile").read_text(
            encoding="utf-8")
        healthcheck = dockerfile[dockerfile.index("HEALTHCHECK"):]
        self.assertIn("/health/ready", healthcheck)


if __name__ == "__main__":
    unittest.main()
