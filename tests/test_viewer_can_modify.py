"""A run's reads say whether the caller may change the run.

A run's page is readable by whoever holds its link, by design: "Copy link"
is for handing a report to someone else. Until 2026-11-15 the page then
offered that someone a red Delete, and Cancel while the run was going. The
server refused them (404), so nothing was lost, but a button that can only
fail is worse than none, and nothing told the reader the report was not
theirs.

The reads now carry `viewer_can_modify`, computed by the one rule that
guards the mutations themselves (`_run_mutation_verdict`), so the page can
hide what the server would refuse. Hiding is a courtesy to the reader, not
the boundary: the mutations are guarded exactly as before, and the tests
below hold the field and the guard to each other, case by case, at the
HTTP boundary.

  true   the server would accept this caller's Cancel, Delete or Resume
  false  it would not
  null   the run has no owner on record (a keys-only run): its id is the
         only credential, the server cannot say whose it is, and anyone
         holding the id is accepted. The page decides from what it knows.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from api import access, accounts, models, runs
from api.main import app
from tests.test_api_accounts import _AccountsHttp

RUN_ID = "20261115T010203Z-0123456789abcdef0123456789abcdef"
OWNERLESS_ID = "20261115T010204Z-fedcba9876543210fedcba9876543210"


def _write_run(root: Path, run_id: str, owner: str | None) -> None:
    directory = root / run_id
    directory.mkdir(parents=True)
    (directory / "status.json").write_text(json.dumps({"done": True, "stage": "Done", "topic": "t"}), encoding="utf-8")
    (directory / "commercialization_report.md").write_text("# Report", encoding="utf-8")
    if owner is not None:
        (directory / ".owner").write_text(owner, encoding="utf-8")


class _Runs(_AccountsHttp):
    def setUp(self):
        super().setUp()
        self.outputs = Path(self._tmp.name) / "outputs"
        self.outputs.mkdir()
        patcher = patch.object(runs, "DEFAULT_OUTPUT_ROOT", self.outputs)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _said(self, run_id, headers=None):
        """What both reads say; they must say the same."""
        status = self.client.get(f"/api/runs/{run_id}", headers=headers or {})
        progress = self.client.get(f"/api/runs/{run_id}/progress", headers=headers or {})
        self.assertEqual((status.status_code, progress.status_code), (200, 200), (status.text, progress.text))
        self.assertIn("viewer_can_modify", status.json())
        self.assertEqual(status.json()["viewer_can_modify"], progress.json()["viewer_can_modify"])
        return status.json()["viewer_can_modify"]

    def _delete_accepted(self, run_id, headers=None):
        """Whether the server lets this caller delete, with the deletion itself stubbed out."""
        with patch.object(runs, "delete_run") as deleted:
            response = self.client.delete(f"/api/runs/{run_id}", headers=headers or {})
        self.assertIn(response.status_code, (200, 204, 404), response.text)
        self.assertEqual(deleted.called, response.status_code != 404)
        return deleted.called


class AccountTests(_Runs):
    def setUp(self):
        super().setUp()
        os.environ["ACCOUNTS_ADMIN_EMAILS"] = "boss@example.com"
        os.environ["ACCOUNTS_INVITE_CODE"] = "let-me-in"    # a reserved address registers with it
        self.alice = self._bearer(self._signup("alice@example.com")["token"])
        self.bob = self._bearer(self._signup("bob@example.com")["token"])
        self.admin = self._bearer(self._signup("boss@example.com", invite="let-me-in")["token"])
        self.assertTrue(self.client.get("/api/auth/me", headers=self.admin).json()["admin"])
        owner = accounts.session_user(self.alice["Authorization"].split()[1]).owner
        _write_run(self.outputs, RUN_ID, owner)
        _write_run(self.outputs, OWNERLESS_ID, None)

    def test_the_owner_and_an_administrator_may_and_nobody_else(self):
        cases = (("the owner", self.alice, True), ("another account", self.bob, False), ("an administrator", self.admin, True),
                 ("nobody signed in", None, False), ("a session that is not one", self._bearer("garbage"), False))
        for name, headers, expected in cases:
            with self.subTest(caller=name):
                self.assertIs(self._said(RUN_ID, headers), expected)
                # The field is the guard's own answer: what it says is what a Delete gets.
                self.assertIs(self._delete_accepted(RUN_ID, headers), expected)

    def test_a_run_with_no_owner_on_record_is_null_for_everyone_and_its_id_stays_the_credential(self):
        for name, headers in (("an account", self.bob), ("nobody signed in", None)):
            with self.subTest(caller=name):
                self.assertIsNone(self._said(OWNERLESS_ID, headers))
                self.assertTrue(self._delete_accepted(OWNERLESS_ID, headers), "unchanged: the id is the credential")
        self.assertIs(self._said(OWNERLESS_ID, self.admin), True, "an administrator is an administrator of every run")

    def test_an_owner_record_that_cannot_be_read_offers_nothing_and_the_read_still_answers(self):
        """The guard answers 503 there: authorization could not be established.
        The read is not a mutation and must not fail for it; it says false."""
        with patch.object(runs, "owner_of", side_effect=runs.OwnerMarkerUnreadable("unreadable")):
            self.assertIs(self._said(RUN_ID, self.alice), False)
            self.assertEqual(self.client.delete(f"/api/runs/{RUN_ID}", headers=self.alice).status_code, 503)
            self.assertIs(self._said(RUN_ID, self.admin), True, "an administrator needs no owner record")

    def test_an_unknown_run_is_still_a_404(self):
        self.assertEqual(self.client.get("/api/runs/20261115T010205Z-00000000000000000000000000000000",
                                         headers=self.alice).status_code, 404)


class CodeTests(_Runs):
    """A deployment that signs visitors in by access code, with no accounts."""

    def setUp(self):
        super().setUp()
        os.environ.pop("ACCOUNTS_DB", None)
        for name, value in (("ACCESS_CODE", None), ("ACCESS_CODES", "code-1,code-2"), ("ADMIN_CODE", "admin-code")):
            patcher = patch.object(access, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        _write_run(self.outputs, RUN_ID, access.owner_id("code-1"))

    def test_the_code_that_made_the_run_and_the_admin_code_may(self):
        cases = (("its own code", {"X-Access-Code": "code-1"}, True), ("another code", {"X-Access-Code": "code-2"}, False),
                 ("the admin code", {"X-Access-Code": "admin-code"}, True), ("no code", None, False),
                 ("a code that is not one", {"X-Access-Code": "nope"}, False))
        for name, headers, expected in cases:
            with self.subTest(caller=name):
                self.assertIs(self._said(RUN_ID, headers), expected)
                self.assertIs(self._delete_accepted(RUN_ID, headers), expected)


class OpenTests(_Runs):
    """No accounts and no codes: nothing to authorize against, as the guard has always said."""

    def setUp(self):
        super().setUp()
        os.environ.pop("ACCOUNTS_DB", None)
        for name in ("ACCESS_CODE", "ACCESS_CODES", "ADMIN_CODE"):
            patcher = patch.object(access, name, None)
            patcher.start()
            self.addCleanup(patcher.stop)
        _write_run(self.outputs, RUN_ID, "user:someone-else")

    def test_everyone_may(self):
        self.assertIs(self._said(RUN_ID), True)
        self.assertTrue(self._delete_accepted(RUN_ID))


def test_both_response_models_declare_the_field_and_say_what_null_means():
    for model in (models.RunStatus, models.RunProgress):
        field = model.model_fields["viewer_can_modify"]
        assert field.default is None, model.__name__
        assert "no owner on record" in field.description, model.__name__
    schema = app.openapi()["components"]["schemas"]
    for name in ("RunStatus", "RunProgress"):
        declared = schema[name]["properties"]["viewer_can_modify"]
        assert {"type": "boolean"} in declared["anyOf"] and {"type": "null"} in declared["anyOf"], name


def test_the_mutation_guard_and_the_reads_share_one_rule():
    """One function decides; the guard raises on it and the reads report it.
    A second copy of the rule in the reads would be free to drift."""
    source = (Path(__file__).resolve().parents[1] / "api" / "main.py").read_text(encoding="utf-8")
    assert source.count("def _run_mutation_verdict(") == 1
    guard = source[source.index("def _authorize_run_mutation("):]
    guard = guard[:guard.index("\n\n\n")]
    assert "_run_mutation_verdict(run_id, http_request)" in guard
    assert "owner_of" not in guard, "the guard no longer reads the owner itself"
    reads = source[source.index("def _viewer_can_modify("):]
    reads = reads[:reads.index("\n\n\n")]
    assert "_run_mutation_verdict(run_id, http_request)" in reads
    assert source.count("viewer_can_modify=_viewer_can_modify(run_id, http_request)") == 2
