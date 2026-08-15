"""A bring-your-own-key run must spend nothing of the operator's.

The deployment offers two ways in: an access code, billed to whoever runs the
service, or your own keys, billed to you. The second promise is the one these
pin, and it was not being kept.

as_env() used to copy the operator's whole environment and override three
names. Nothing that actually chooses a provider reads those three:

  * default_web_search_client() prefers Tavily whenever TAVILY_API_KEY is set,
    so a visitor's Serper key was never used and every BYOK search came out of
    the operator's Tavily quota;
  * create_llm() takes the api_key from the visitor and the base URL from the
    environment, and llm_config documents a supported setup where
    OPENAI_API_BASE points at DeepSeek — under which a visitor choosing
    "openai" had their own key sent to a host they never chose.

So the tests below assert the consequences (which client resolves, which host
a key would go to), not the presence of a variable name. The last one is the
one that matters in a year: it fails when a new credential is added to the
codebase without deciding which side of the line it falls on.
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from api.runs import (
    _FREE_TO_SHARE_ENV,
    _OPERATOR_BILLED_ENV,
    BYOKCredentials,
)

_OPERATOR_ENV = {
    "PATH": "/usr/bin",
    "LLM_PROVIDER": "deepseek",
    "DEEPSEEK_API_KEY": "operator-deepseek",
    "OPENAI_API_KEY": "operator-openai",
    "OPENAI_API_BASE": "https://api.deepseek.com",
    "OPENAI_MODEL_NAME": "deepseek-chat",
    "ANTHROPIC_API_KEY": "operator-anthropic",
    "SERPER_API_KEY": "operator-serper",
    "TAVILY_API_KEY": "operator-tavily",
    "LENS_API_KEY": "operator-lens",
    "NCBI_API_KEY": "operator-ncbi",
    "SEMANTIC_SCHOLAR_API_KEY": "operator-s2",
}

_GUEST = BYOKCredentials(
    llm_provider="openai",
    llm_api_key="guest-openai-key",
    serper_api_key="guest-serper-key",
)


class NoOperatorCredentialSurvivesTests(unittest.TestCase):

    def test_no_operator_secret_appears_anywhere_in_the_subprocess_env(self):
        """Checked by value, not by variable name. A key copied into some
        other name is the same leak, and naming the variables here would only
        restate the implementation back to itself."""
        env = _GUEST.as_env(_OPERATOR_ENV)
        leaked = sorted(
            f"{name}={value}" for name, value in env.items()
            if isinstance(value, str) and value.startswith("operator-")
            and name not in _FREE_TO_SHARE_ENV
        )
        self.assertEqual(leaked, [])

    def test_every_billed_variable_is_gone(self):
        env = _GUEST.as_env(_OPERATOR_ENV)
        survivors = sorted(
            name for name in _OPERATOR_BILLED_ENV
            if name in env and env[name] == _OPERATOR_ENV.get(name)
        )
        self.assertEqual(survivors, [])

    def test_unrelated_environment_is_left_alone(self):
        """Scrubbing is targeted. A subprocess still needs PATH to start."""
        env = _GUEST.as_env(_OPERATOR_ENV)
        self.assertEqual(env["PATH"], "/usr/bin")

    def test_free_rate_limit_keys_are_kept(self):
        """Deliberate, and the reason is cost: these raise a rate limit and
        charge nothing. Stripping them would slow every BYOK run to honour a
        promise about money they do not spend."""
        env = _GUEST.as_env(_OPERATOR_ENV)
        for name in _FREE_TO_SHARE_ENV:
            with self.subTest(name=name):
                self.assertEqual(env[name], _OPERATOR_ENV[name])


class GuestCredentialsAreTheOnesUsedTests(unittest.TestCase):
    """Removing the operator's keys is only half of it — the visitor's have to
    be what the run then picks up."""

    def test_the_search_client_resolves_to_the_guest_provider(self):
        """The bug expressed as behaviour. With the operator's Tavily key in
        the environment this returned a TavilyClient, billing the operator,
        whatever the visitor supplied."""
        from academic_agent.source_clients import SerperClient, default_web_search_client

        env = _GUEST.as_env(_OPERATOR_ENV)
        with mock.patch.dict(os.environ, env, clear=True):
            client = default_web_search_client()
        self.assertIsInstance(client, SerperClient)
        self.assertEqual(client.api_key, "guest-serper-key")

    def test_the_llm_is_not_pointed_at_someone_elses_host(self):
        """OPENAI_API_BASE survived the old override, so a visitor's OpenAI
        key went to whatever host the operator had configured — DeepSeek, in
        the setup llm_config explicitly supports."""
        from academic_agent import llm_config

        env = _GUEST.as_env(_OPERATOR_ENV)
        captured: dict = {}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(llm_config, "LLM", lambda **kw: captured.update(kw)), \
                mock.patch.object(llm_config, "_wrap_with_retry", lambda x: x):
            llm_config.create_llm()

        self.assertEqual(captured["provider"], "openai")
        self.assertEqual(captured["api_key"], "guest-openai-key")
        self.assertNotIn("base_url", captured)
        self.assertNotIn("deepseek", str(captured).lower())

    def test_the_guest_provider_wins_over_the_operators(self):
        """The operator runs DeepSeek; this visitor asked for OpenAI."""
        from academic_agent.llm_config import _detect_provider

        env = _GUEST.as_env(_OPERATOR_ENV)
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(_detect_provider(), "openai")


class _FakeProc:
    """A subprocess that never exits, recording the env it was launched with."""

    launched: list[dict | None] = []

    def __init__(self, *args, **kwargs):
        type(self).launched.append(kwargs.get("env"))

    def poll(self):
        return None

    def terminate(self):
        pass

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 0


class LaunchedEnvironmentTests(unittest.TestCase):
    """Asserted at the Popen call, not on as_env().

    The last defect of this shape was a value that was computed correctly and
    then never reached the caller. A unit test on as_env() alone would have
    passed through that too, so the assertion belongs where the subprocess is
    actually launched.
    """

    def setUp(self):
        from api import runs

        self._runs = runs
        self._tmp = TemporaryDirectory()
        self._root = runs.DEFAULT_OUTPUT_ROOT
        runs.DEFAULT_OUTPUT_ROOT = Path(self._tmp.name)
        _FakeProc.launched = []
        self.addCleanup(self._restore)

    def _restore(self):
        for handle in list(self._runs._registry.values()):
            if handle.log_file is not None:
                try:
                    handle.log_file.close()
                except OSError:
                    pass
        self._runs._registry.clear()
        self._runs.DEFAULT_OUTPUT_ROOT = self._root
        self._tmp.cleanup()

    def test_a_coded_run_still_inherits_the_operators_environment(self):
        """env=None means inherit. A code holder is meant to spend the
        operator's keys — the scrub must not have leaked into that path."""
        with mock.patch.object(self._runs.subprocess, "Popen", _FakeProc):
            self._runs.start_run("a topic")
        self.assertEqual(_FakeProc.launched, [None])

    def test_a_byok_run_is_launched_with_the_scrubbed_environment(self):
        with mock.patch.dict(os.environ, _OPERATOR_ENV, clear=True), \
                mock.patch.object(self._runs.subprocess, "Popen", _FakeProc):
            self._runs.start_run("a topic", byok=_GUEST)

        env = _FakeProc.launched[0]
        self.assertIsNotNone(env, "a BYOK run must never inherit the environment")
        self.assertNotIn("TAVILY_API_KEY", env)
        self.assertNotIn("OPENAI_API_BASE", env)
        self.assertEqual(env["SERPER_API_KEY"], "guest-serper-key")
        self.assertEqual(env["OPENAI_API_KEY"], "guest-openai-key")


class EveryCredentialIsClassifiedTests(unittest.TestCase):
    """The guard that outlives this change.

    A denylist is only correct on the day it is written. The next paid API
    gets read with os.getenv like all the others, and nothing about adding it
    would prompt anyone to come back here — which is exactly how TAVILY_API_KEY
    came to be missing from the override in the first place.

    So this fails on an unclassified credential rather than on a leak. Adding a
    key means putting it on one side of the line on purpose.
    """

    _ROOT = Path(__file__).resolve().parent.parent
    _CREDENTIAL = re.compile(r'os\.getenv\(\s*"([A-Z0-9_]*(?:API_KEY|API_BASE))"')

    def test_no_credential_is_read_without_being_classified(self):
        found: dict[str, str] = {}
        for directory in ("src", "api"):
            for path in (self._ROOT / directory).rglob("*.py"):
                for name in self._CREDENTIAL.findall(path.read_text(encoding="utf-8")):
                    found.setdefault(name, str(path.relative_to(self._ROOT)))

        self.assertTrue(found, "the scan found nothing; the pattern is wrong")
        unclassified = sorted(
            f"{name} (read in {where})" for name, where in found.items()
            if name not in _OPERATOR_BILLED_ENV and name not in _FREE_TO_SHARE_ENV
        )
        self.assertEqual(
            unclassified, [],
            "A credential is read from the environment but is on neither list "
            "in api/runs.py. Decide: does it cost the operator money (add it "
            "to _OPERATOR_BILLED_ENV so BYOK runs cannot spend it), or is it a "
            "free rate-limit key (_FREE_TO_SHARE_ENV)?")

    def test_the_two_lists_do_not_overlap(self):
        self.assertEqual(_OPERATOR_BILLED_ENV & _FREE_TO_SHARE_ENV, frozenset())


if __name__ == "__main__":
    unittest.main()
