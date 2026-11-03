"""Reader feedback: stored with the run, one record per responder, a closed vocabulary.

Writing an answer is a mutation of the run directory, so it is authorized the
way cancellation and resume are: a code-owned run answers to its code or the
admin, an ownerless run to whoever holds its URL. Reading one's own answer
needs the same, so a shared link never shows another reader's answer.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from academic_agent.run_output import create_run_id
from api import access, runs
from api.main import app
from scripts import ops_report

YES = {"changed_view": "yes"}
NO_REPORT = {"changed_view": "no", "part": "report"}


class _FeedbackTestCase(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for target, name, value in (
            (runs, "DEFAULT_OUTPUT_ROOT", self.tmp),
            (access, "ACCESS_CODE", None), (access, "ACCESS_CODES", None), (access, "ADMIN_CODE", None),
        ):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        runs._registry.clear()
        self.client = TestClient(app)

    def _run(self, *, owner: str | None = None, delivered: bool = True) -> str:
        run_id = create_run_id()
        directory = self.tmp / run_id
        directory.mkdir()
        status = {"done": True, "topic": "solid-state batteries"} if delivered else {"done": False, "error": "boom"}
        (directory / "status.json").write_text(json.dumps(status), encoding="utf-8")
        if owner is not None:
            (directory / ".owner").write_text(owner, encoding="utf-8")
        return run_id

    def _post(self, run_id: str, body: dict, code: str | None = None):
        headers = {"X-Access-Code": code} if code else {}
        return self.client.post(f"/api/runs/{run_id}/feedback", json=body, headers=headers)

    def _get(self, run_id: str, code: str | None = None):
        headers = {"X-Access-Code": code} if code else {}
        return self.client.get(f"/api/runs/{run_id}/feedback", headers=headers)


class FeedbackStorageTests(_FeedbackTestCase):

    def test_one_click_is_stored_with_the_run_and_read_back(self):
        run_id = self._run()
        posted = self._post(run_id, YES)
        self.assertEqual(posted.status_code, 200, posted.text)
        body = posted.json()
        self.assertEqual((body["recorded"], body["changed_view"], body["part"]), (True, "yes", None))
        self.assertTrue(body["recorded_at"].endswith("+00:00"))
        self.assertEqual(self._get(run_id).json(), body)
        on_disk = json.loads((self.tmp / run_id / "feedback.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk["schema_version"], 1)
        self.assertEqual(list(on_disk["responses"]), ["holder"])
        self.assertEqual(on_disk["responses"]["holder"]["changed_view"], "yes")

    def test_an_unanswered_report_reads_as_not_recorded(self):
        run_id = self._run()
        self.assertEqual(self._get(run_id).json(),
                         {"recorded": False, "changed_view": None, "part": None, "recorded_at": None})
        self.assertFalse((self.tmp / run_id / "feedback.json").exists())

    def test_a_second_answer_replaces_the_first_rather_than_adding_a_vote(self):
        run_id = self._run()
        self._post(run_id, YES)
        second = self._post(run_id, NO_REPORT)
        self.assertEqual(second.status_code, 200)
        self.assertEqual((second.json()["changed_view"], second.json()["part"]), ("no", "report"))
        on_disk = json.loads((self.tmp / run_id / "feedback.json").read_text(encoding="utf-8"))
        self.assertEqual(len(on_disk["responses"]), 1)
        self.assertEqual(self._get(run_id).json()["changed_view"], "no")

    def test_only_a_delivered_report_takes_an_answer(self):
        """A failed run has no report to answer about; its page shows no question."""
        run_id = self._run(delivered=False)
        refused = self._post(run_id, YES)
        self.assertEqual(refused.status_code, 409)
        self.assertIn("delivered reports only", refused.json()["detail"])
        self.assertFalse((self.tmp / run_id / "feedback.json").exists())

    def test_the_vocabulary_is_closed(self):
        run_id = self._run()
        for body in ({"changed_view": "maybe"}, {"changed_view": "yes", "part": "everything"},
                     {"changed_view": "yes", "comment": "free text"}, {}):
            with self.subTest(body=body):
                self.assertEqual(self._post(run_id, body).status_code, 422)
        self.assertFalse((self.tmp / run_id / "feedback.json").exists())

    def test_an_unknown_run_is_404_for_both_verbs(self):
        self.assertEqual(self._get("20260101T000000Z-0000000000000000").status_code, 404)
        self.assertEqual(self._post("20260101T000000Z-0000000000000000", YES).status_code, 404)

    def test_a_damaged_file_is_reported_and_never_overwritten(self):
        """It may hold other responders' answers; a new click must not erase them."""
        run_id = self._run()
        damaged = self.tmp / run_id / "feedback.json"
        damaged.write_text("{not json", encoding="utf-8")
        self.assertEqual(self._get(run_id).status_code, 503)
        self.assertEqual(self._post(run_id, YES).status_code, 503)
        self.assertEqual(damaged.read_text(encoding="utf-8"), "{not json")

    def test_feedback_is_not_served_as_a_run_artifact(self):
        run_id = self._run()
        self._post(run_id, YES)
        self.assertNotIn("feedback", runs.artifact_names())
        self.assertEqual(self.client.get(f"/api/runs/{run_id}/feedback.json").status_code, 404)


class FeedbackAuthorizationTests(_FeedbackTestCase):

    def setUp(self):
        super().setUp()
        for name, value in (("ACCESS_CODE", "code-a"), ("ACCESS_CODES", "code-b"), ("ADMIN_CODE", "admin-z")):
            patcher = patch.object(access, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.owner_a = access.owner_id("code-a")

    def test_a_code_owned_run_answers_only_to_its_code_or_the_admin(self):
        run_id = self._run(owner=self.owner_a)
        # The shared link alone, and another valid code, learn nothing and write nothing.
        for code in (None, "code-b", "not-a-code"):
            with self.subTest(code=code):
                self.assertEqual(self._get(run_id, code).status_code, 404)
                self.assertEqual(self._post(run_id, YES, code).status_code, 404)
        self.assertFalse((self.tmp / run_id / "feedback.json").exists())
        self.assertEqual(self._post(run_id, YES, "code-a").status_code, 200)
        self.assertEqual(self._get(run_id, "code-a").json()["changed_view"], "yes")

    def test_the_admin_answers_under_their_own_name_not_the_owners(self):
        run_id = self._run(owner=self.owner_a)
        self._post(run_id, YES, "code-a")
        self.assertEqual(self._post(run_id, NO_REPORT, "admin-z").status_code, 200)
        self.assertEqual(self._get(run_id, "code-a").json()["changed_view"], "yes")
        self.assertEqual(self._get(run_id, "admin-z").json()["changed_view"], "no")
        on_disk = json.loads((self.tmp / run_id / "feedback.json").read_text(encoding="utf-8"))
        self.assertEqual(set(on_disk["responses"]), {self.owner_a, access.owner_id("admin-z")})

    def test_an_ownerless_run_has_one_responder_whoever_holds_its_url(self):
        """A visitor's own-key run has no code to prove anything with; the id is
        its only credential, as it is for cancellation and deletion. A code
        presented alongside changes nothing: the answer is the URL holder's."""
        run_id = self._run(owner=None)
        self.assertEqual(self._post(run_id, YES).status_code, 200)
        self.assertEqual(self._get(run_id, "code-b").json()["changed_view"], "yes")
        self.assertEqual(self._post(run_id, NO_REPORT, "code-b").status_code, 200)
        self.assertEqual(self._get(run_id).json()["changed_view"], "no")
        on_disk = json.loads((self.tmp / run_id / "feedback.json").read_text(encoding="utf-8"))
        self.assertEqual(list(on_disk["responses"]), ["holder"])


class OpsReportFeedbackTests(_FeedbackTestCase):

    def test_the_ops_report_counts_answers_over_delivered_reports(self):
        answered_yes = self._run()
        answered_no = self._run()
        self._run()                     # delivered, unanswered
        self._run(delivered=False)      # failed, cannot be answered
        damaged = self._run()
        self._post(answered_yes, YES)
        self._post(answered_no, NO_REPORT)
        (self.tmp / damaged / "feedback.json").write_text("{not json", encoding="utf-8")

        collected = {run["run_id"]: run["feedback"] for run in ops_report.collect(self.tmp)}
        self.assertEqual(collected[answered_yes][0]["changed_view"], "yes")
        self.assertEqual(collected[answered_no][0]["part"], "report")
        self.assertIsNone(collected[damaged])
        self.assertEqual(sum(1 for value in collected.values() if value == []), 2)

        out = io.StringIO()
        with redirect_stdout(out):
            ops_report._print_feedback(ops_report.collect(self.tmp))
        text = out.getvalue()
        self.assertIn("Reader feedback (2 of 4 delivered report(s) answered; 1 feedback file(s) unreadable)", text)
        self.assertIn("changed the reader's view: yes=1, no=1, unsure=0", text)
        self.assertIn("part that mattered most:   report=1", text)

    def test_no_answers_is_said_rather_than_counted_as_no(self):
        self._run()
        out = io.StringIO()
        with redirect_stdout(out):
            ops_report._print_feedback(ops_report.collect(self.tmp))
        self.assertIn("none recorded; an unanswered report says nothing either way", out.getvalue())
