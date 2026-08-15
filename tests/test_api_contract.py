"""The seam between what a run knows and what a client receives.

Two features shipped, were documented, and never worked in the browser: the
per-agent cost and the citation-check counts. `get_state()` returned both,
`status.json` held both, the worker printed both, and the HTTP response
carried neither — `response_model` drops what the model does not declare, and
one of the two endpoints builds its response field by field, so a key added
to `get_state()` reaches one and silently not the other.

948 tests missed it because every one of them stopped at a boundary: the
worker tests read status.json, the client tests called the formatter with a
literal. Nothing asserted the join.

So these do not test cost, or grounding, or any one field. They test that the
join holds — that a field a run produces reaches the client, whichever
endpoint it comes from — because the next field added will be added the same
way this one was.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

import api.runs as runs
from api.main import app
from api.models import RunProgress, RunStatus

#: Keys get_state() produces that a client deliberately never sees. Listing
#: them here is the point: adding a key means either exposing it or writing
#: down why not, and neither can be done by accident.
_INTERNAL_ONLY: set[str] = set()

_STATUS = {
    "stage": "Done",
    "done": True,
    "error": None,
    "output_language": "English",
    "topic": "solid-state batteries",
    "source_counts": {"academic": 5, "patent": 8, "market": 8},
    "evidence_incomplete": False,
    "failed_domains": [],
    "usage": {"total_tokens": 77819, "total_requests": 6, "cost_usd": 0.0333,
              "cost_complete": True, "agents": []},
    "claim_grounding": {"checked": 2, "ungrounded": 0, "unverifiable": 2,
                        "by_domain": {}},
}


class _Run:
    """A finished run on disk, the way the API expects to find one."""

    def __init__(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.run_id = "20260814T002830Z-5642c7d31d"
        directory = self.root / self.run_id
        directory.mkdir()
        (directory / "status.json").write_text(json.dumps(_STATUS), encoding="utf-8")
        (directory / "commercialization_report.md").write_text("# r", encoding="utf-8")

    def close(self) -> None:
        self._tmp.cleanup()


class StateReachesTheClientTests(unittest.TestCase):

    def setUp(self):
        self.run = _Run()
        self.addCleanup(self.run.close)
        patcher = patch.object(runs, "DEFAULT_OUTPUT_ROOT", self.run.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(app)

    def _state_keys(self) -> set[str]:
        return set(runs.get_state(self.run.run_id)) - _INTERNAL_ONLY

    def test_every_field_a_run_produces_is_declared_by_the_status_model(self):
        missing = self._state_keys() - set(RunStatus.model_fields)
        self.assertFalse(
            missing,
            f"get_state() produces {sorted(missing)}, which RunStatus does not "
            "declare — response_model will drop them before the client sees them",
        )

    def test_every_field_a_run_produces_is_declared_by_the_progress_model(self):
        missing = self._state_keys() - set(RunProgress.model_fields)
        self.assertFalse(
            missing,
            f"get_state() produces {sorted(missing)}, which RunProgress does not "
            "declare",
        )

    def test_the_status_endpoint_returns_them_with_their_values(self):
        """Declaring the field is half of it. The other half is that the
        endpoint actually passes the value through rather than leaving the
        default in place, which looks identical in the schema."""
        body = self.client.get(f"/api/runs/{self.run.run_id}").json()
        for key in self._state_keys():
            with self.subTest(field=key):
                self.assertIn(key, body)
        self.assertEqual(body["usage"]["cost_usd"], 0.0333)
        self.assertEqual(body["claim_grounding"]["unverifiable"], 2)

    def test_the_progress_endpoint_returns_them_with_their_values(self):
        """This endpoint names each field in its constructor, so it is the one
        that silently drops a newly added key. It is why both are asserted."""
        body = self.client.get(f"/api/runs/{self.run.run_id}/progress").json()
        for key in self._state_keys():
            with self.subTest(field=key):
                self.assertIn(key, body)
        self.assertEqual(body["usage"]["cost_usd"], 0.0333)
        self.assertEqual(body["claim_grounding"]["unverifiable"], 2)

    def test_the_two_endpoints_do_not_disagree(self):
        """They are built differently — one splats get_state(), one names every
        field — so they drift apart rather than break together."""
        status = self.client.get(f"/api/runs/{self.run.run_id}").json()
        progress = self.client.get(f"/api/runs/{self.run.run_id}/progress").json()
        for key in self._state_keys():
            with self.subTest(field=key):
                self.assertEqual(status[key], progress[key])


class AbsentDataTests(unittest.TestCase):
    """Runs that predate a feature must not break the endpoint that now
    reports it — there are 65 such runs on disk."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.run_id = "20260710T082000Z-aaaaaaaaaa"
        directory = self.root / self.run_id
        directory.mkdir()
        (directory / "status.json").write_text(
            json.dumps({"stage": "Done", "done": True}), encoding="utf-8")
        patcher = patch.object(runs, "DEFAULT_OUTPUT_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(app)

    def test_a_run_without_usage_reports_null_rather_than_failing(self):
        for path in (f"/api/runs/{self.run_id}", f"/api/runs/{self.run_id}/progress"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.json()["usage"])

    def test_null_is_distinguishable_from_zero(self):
        """A run with no usage recorded is not a run that cost nothing. The
        client renders the first as absent and the second as free."""
        body = self.client.get(f"/api/runs/{self.run_id}").json()
        self.assertIsNone(body["usage"])
        self.assertNotEqual(body["usage"], {})
