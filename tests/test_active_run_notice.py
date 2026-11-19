"""An account is told it has an assessment going before it asks for another.

An account runs one assessment at a time. On 2026-11-18 a second topic went
through its plan preview, one small request on the account's own key, and
only when Start was pressed was it told "your account already has an
assessment in progress". Nothing on the workbench showed a run in progress,
and on a phone the history is off screen.

The run list now says what the caller's own account has going
(`active_runs`, `at_capacity`), by the same count the admission makes, and
the page shows a line with the way to that run and turns off the controls
that would be refused, with the reason beside them. Nothing is queued and
the admission itself is unchanged: these tests hold that too.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from api import runs
from tests.test_account_limits import _Limits

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "web" / "static" / "js"
RUN_JS = (JS / "run.js").read_text(encoding="utf-8")
APP_JS = (JS / "app.js").read_text(encoding="utf-8")
SIDEBAR_JS = (JS / "sidebar.js").read_text(encoding="utf-8")
INDEX = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
EN, ZH = "English", "Simplified Chinese"
ALICE, BOB = "alice@example.com", "bob@example.com"


# ── What the run list says ──────────────────────────────────────────────────


class WhatTheListSaysTests(_Limits):
    def _list(self, email=ALICE):
        reply = self.client.get("/api/runs", headers=self._as(email))
        self.assertEqual(reply.status_code, 200, reply.text)
        return reply.json()

    def test_an_idle_account_has_nothing_going(self):
        listed = self._list()
        self.assertEqual((listed["active_runs"], listed["at_capacity"]), ([], False))

    def test_a_run_in_progress_is_named_with_its_topic_and_the_account_is_at_capacity(self):
        run_id = self._start().json()["run_id"]
        listed = self._list()
        self.assertEqual(listed["active_runs"], [{"run_id": run_id, "topic": "a valid research topic"}])
        self.assertTrue(listed["at_capacity"])
        # It is the admission's own answer: asking changes nothing, and Start is still refused.
        self.assertEqual(self._start().headers["X-Error-Code"], "account_busy")
        self.assertEqual(self._list()["active_runs"], [{"run_id": run_id, "topic": "a valid research topic"}])

    def test_another_accounts_run_is_not_this_accounts(self):
        self._start(BOB)
        listed = self._list(ALICE)
        self.assertEqual((listed["active_runs"], listed["at_capacity"]), ([], False))
        self.assertEqual(len(self._list(BOB)["active_runs"]), 1)

    def test_it_clears_when_the_run_ends_and_when_it_is_cancelled(self):
        self._start()
        self._finish_every_worker()
        self.assertEqual((self._list()["active_runs"], self._list()["at_capacity"]), ([], False))
        run_id = self._start().json()["run_id"]
        self.assertTrue(self._list()["at_capacity"])
        self.client.delete(f"/api/runs/{run_id}?intent=cancel", headers=self._as(ALICE))
        self.assertEqual((self._list()["active_runs"], self._list()["at_capacity"]), ([], False))

    def test_an_upload_being_read_holds_the_slot_without_being_a_run(self):
        with runs.reserve_inline_paid_operation(owner=runs.accounts.owner_tag(1), byok=True):
            listed = self._list()
            self.assertEqual((listed["active_runs"], listed["at_capacity"]), ([], True))
        self.assertFalse(self._list()["at_capacity"])

    def test_capacity_follows_the_setting(self):
        with patch.object(runs, "ACCOUNT_MAX_CONCURRENT", 2):
            first = self._start().json()["run_id"]
            listed = self._list()
            self.assertEqual((len(listed["active_runs"]), listed["at_capacity"]), (1, False))
            second = self._start().json()["run_id"]
            listed = self._list()
            # Newest first: the one the line above the panes points at.
            self.assertEqual([entry["run_id"] for entry in listed["active_runs"]], sorted([first, second], reverse=True))
            self.assertTrue(listed["at_capacity"])
        self._finish_every_worker()
        with patch.object(runs, "ACCOUNT_MAX_CONCURRENT", 0):
            self._start()
            listed = self._list()
            self.assertEqual((len(listed["active_runs"]), listed["at_capacity"]), (1, False))

    def test_an_administrator_is_told_of_their_own_run_not_of_everyones(self):
        with patch.dict("os.environ", {"ACCOUNTS_ADMIN_EMAILS": ALICE}):
            self._start(BOB)
            listed = self._list(ALICE)
            # The list is everyone's; what is going is asked of the caller's own account.
            self.assertEqual(len(listed["runs"]), 1)
            self.assertEqual((listed["active_runs"], listed["at_capacity"]), ([], False))
            own = self._start(ALICE).json()["run_id"]
            listed = self._list(ALICE)
            self.assertEqual(len(listed["runs"]), 2)
            self.assertEqual([entry["run_id"] for entry in listed["active_runs"]], [own])
            self.assertTrue(listed["at_capacity"])

    def test_a_caller_that_is_no_account_has_no_such_limit(self):
        self.assertIsNone(runs.account_activity(None))
        self.assertIsNone(runs.account_activity("code:abc"))
        activity = runs.account_activity(runs.accounts.owner_tag(1))
        self.assertEqual(activity, {"active_runs": [], "at_capacity": False})


# ── What the page says ──────────────────────────────────────────────────────

_HARNESS = """
    globalThis.localStorage = { getItem: () => null, setItem: () => {} };
    globalThis.document = { querySelectorAll: () => [], documentElement: {} };
    const run = await import("./run.mjs");
    const i18n = await import("./i18n.js");
    const out = JSON.parse(process.argv[2]).map(([language, facts]) => {
      i18n.setLanguage(language);
      return run.activeRunNotice(facts);
    });
    console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def notice(tmp_path_factory):
    node = shutil.which("node")
    assert node, "Node must execute the page's own module; skipping loses the seam"
    work = tmp_path_factory.mktemp("active-run-notice")
    (work / "run.mjs").write_text(RUN_JS.replace('import * as api from "./api.js";', "const api = {};"), encoding="utf-8")
    shutil.copy2(JS / "i18n.js", work / "i18n.js")
    (work / "harness.mjs").write_text(textwrap.dedent(_HARNESS), encoding="utf-8")

    def ask(*calls):
        done = subprocess.run([node, "harness.mjs", json.dumps(list(calls))], capture_output=True, text=True,
                              encoding="utf-8", cwd=work, check=False)
        assert done.returncode == 0, done.stderr[-1500:]
        return json.loads(done.stdout)

    return ask


GOING = [{"run_id": "20261118T083403Z-" + "e" * 32, "topic": "perovskite-silicon tandem cells"}]


def test_a_run_in_progress_is_said_above_the_panes_with_the_way_to_it(notice):
    english, chinese = notice([EN, {"activeRuns": GOING, "atCapacity": True}],
                              [ZH, {"activeRuns": GOING, "atCapacity": True}])
    assert english == {
        "banner": {"runId": GOING[0]["run_id"], "view": "View it",
                   "text": "You have an assessment in progress: perovskite-silicon tandem cells."},
        "blocked": True,
        "reason": "Your account cannot preview or start another assessment while one is in progress. Wait for it to "
                  "finish, or cancel it; what you typed stays here.",
    }
    assert chinese["banner"]["text"] == "你有一份评估正在进行：perovskite-silicon tandem cells。"
    assert chinese["banner"]["view"] == "查看"
    assert chinese["reason"] == "有评估在进行时，你的账号不能预览或开始另一份。等它结束，或先取消它；已输入的内容会保留。"


def test_nothing_is_said_or_turned_off_for_an_idle_account(notice):
    for facts in ({}, {"activeRuns": [], "atCapacity": False}, {"activeRuns": None}, {"activeRuns": "x", "atCapacity": "yes"}):
        assert notice([EN, facts])[0] == {"banner": None, "blocked": False, "reason": ""}, facts


def test_the_line_is_not_shown_on_the_page_of_that_run_but_the_controls_stay_off(notice):
    seen = notice([EN, {"activeRuns": GOING, "atCapacity": True, "openRunId": GOING[0]["run_id"]}])[0]
    assert seen["banner"] is None and seen["blocked"] is True and seen["reason"]
    other = notice([EN, {"activeRuns": GOING, "atCapacity": True, "openRunId": "20260101T000000Z-" + "0" * 32}])[0]
    assert other["banner"]["runId"] == GOING[0]["run_id"]


def test_an_account_allowed_two_is_told_of_the_one_going_and_not_stopped(notice):
    seen = notice([EN, {"activeRuns": GOING, "atCapacity": False}])[0]
    assert seen["banner"]["runId"] == GOING[0]["run_id"]
    assert (seen["blocked"], seen["reason"]) == (False, "")


def test_at_capacity_with_no_run_to_point_at_says_what_else_holds_the_slot(notice):
    english, chinese = notice([EN, {"activeRuns": [], "atCapacity": True}], [ZH, {"activeRuns": [], "atCapacity": True}])
    assert english["banner"] is None and english["blocked"] is True
    assert english["reason"].startswith("Your account has an operation in progress, such as an uploaded paper being read.")
    assert chinese["reason"].startswith("你的账号有一项操作正在进行，比如正在读取上传的论文。")


def test_the_newest_run_is_the_one_pointed_at_and_a_run_without_a_topic_is_still_said(notice):
    older = {"run_id": "20261118T070000Z-" + "a" * 32, "topic": "older"}
    seen = notice([EN, {"activeRuns": [GOING[0], older], "atCapacity": True}])[0]
    assert seen["banner"]["runId"] == GOING[0]["run_id"]
    plain = notice([EN, {"activeRuns": [{"run_id": GOING[0]["run_id"], "topic": "  "}], "atCapacity": True}],
                   [ZH, {"activeRuns": [{"run_id": GOING[0]["run_id"]}], "atCapacity": True}],
                   [EN, {"activeRuns": [{"topic": "no id"}, GOING[0]], "atCapacity": True}])
    assert plain[0]["banner"]["text"] == "You have an assessment in progress."
    assert plain[1]["banner"]["text"] == "你有一份评估正在进行。"
    assert plain[2]["banner"]["runId"] == GOING[0]["run_id"], "An entry with no id is not a run to open"
    # A topic is text: a "$&" in it is not a replacement pattern.
    odd = notice([EN, {"activeRuns": [{"run_id": GOING[0]["run_id"], "topic": "cost $& benefit"}], "atCapacity": True}])[0]
    assert odd["banner"]["text"] == "You have an assessment in progress: cost $& benefit."


# ── How the page is wired ───────────────────────────────────────────────────


def _body(source: str, opening: str) -> str:
    start = source.index(opening)
    return source[start:source.index("\n}\n", start)]


def test_the_line_sits_above_the_panes_and_the_reason_beside_the_run_button():
    line = INDEX.index('id="active-run"')
    assert INDEX.index('<main class="main" id="main">') < line < INDEX.index('id="pane-compose"'), \
        "Inside the main column and above every pane, so a phone shows it"
    assert 'id="active-run" role="status" hidden' in INDEX
    assert INDEX.index('id="run-btn"') < INDEX.index('id="busy-note"') < INDEX.index('id="plan-panel"')
    assert 'id="busy-note" role="status" hidden' in INDEX


def test_the_list_hands_the_page_what_the_account_has_going():
    assert "activity: { activeRuns: first?.active_runs ?? [], atCapacity: first?.at_capacity === true }" in SIDEBAR_JS
    refresh = SIDEBAR_JS[SIDEBAR_JS.index("export async function refresh("):]
    assert refresh.index("if (!isCurrent()) return null;") < refresh.index("onActivity(activity);") < refresh.index("render(container"), \
        "Only for the identity the list was asked for, and before the rows are drawn"
    assert "onActivity: noteAccountActivity," in APP_JS


def test_the_run_button_the_plans_start_and_the_upload_are_off_with_the_reason():
    sync = _body(APP_JS, "function syncComposer() {")
    assert "const busy = activeRunView().blocked;" in sync
    assert re.search(r"runBtn\.disabled = [^;]*\|\| busy;", sync, re.S)
    assert "busy ? activeRunView().reason : t(\"run_hint\")" in sync
    assert '(busy && control.id === "plan-start")' in sync, "Start is off; Change topic is not"
    assert re.search(r"attachBtn\.disabled = [^;]*\|\| busy;", sync)
    # Enter in the field goes through the same button, so a preview is not asked for either.
    assert 'if (!runBtn.disabled) $("#compose-form").requestSubmit();' in APP_JS
    paint = _body(APP_JS, "function paintActiveRun() {")
    assert "line.hidden = !view.banner || viewerMode;" in paint
    assert "open.onclick = view.banner ? () => openRun(view.banner.runId) : null;" in paint
    assert "note.textContent = view.reason;" in paint and "note.hidden = !view.reason;" in paint


def test_the_page_asks_again_while_a_run_is_going_and_only_then():
    note = _body(APP_JS, "function noteAccountActivity(activity) {")
    assert "paintActiveRun();" in note and "syncComposer();" in note
    assert "const going = accountActivity.activeRuns.length > 0 || accountActivity.atCapacity;" in note
    # Not while that run's own page is open: its progress poll sees the end and asks the list then.
    assert "const followed = accountActivity.activeRuns.some((entry) => entry?.run_id === activeRunId);" in note
    assert "if (going && !followed && !document.hidden) activityTimer = setTimeout(refreshSidebar, ACTIVITY_INTERVAL);" in note
    assert "const ACTIVITY_INTERVAL = 15_000;" in APP_JS
    assert "const activeRunView = () => runView.activeRunNotice({ ...accountActivity, openRunId: activeRunId });" in APP_JS
    # The line follows the pane: gone on the run's own page, back on the composer.
    assert "activeRunId = runId;\n  // The line about a run in progress is not shown on that run's own page.\n  paintActiveRun();" in APP_JS
    assert "activeRunId = null;\n  paintActiveRun();" in APP_JS


def test_nothing_is_queued_and_the_admission_is_as_it_was():
    """Option A of the two put to the maintainer: say why and turn the controls off; no queue."""
    assert "queue" not in _body(APP_JS, "function noteAccountActivity(activity) {").lower()
    admit = (ROOT / "api" / "runs.py").read_text(encoding="utf-8")
    assert "going = _account_active_locked(owner)\n        if going >= ACCOUNT_MAX_CONCURRENT:\n            raise AccountBusy(" in admit
    activity = admit[admit.index("def account_activity("):admit.index("def capacity_counts(")]
    assert "_admit_paid_operation_locked(" not in activity.split('"""')[2], "Reading admits nothing"


def test_every_string_is_in_both_languages():
    header = RUN_JS[RUN_JS.index("const HEADER_STRINGS = {"):RUN_JS.index("// English keeps the API's own state words")]
    english, chinese = header.split('"Simplified Chinese": {')
    for key in ("busy_banner", "busy_banner_plain", "busy_view", "busy_reason", "busy_reason_other"):
        assert english.count(f"    {key}: ") == 1 and chinese.count(f"    {key}: ") == 1, key
