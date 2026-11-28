"""Before its data has answered, the page says it is loading; never that nothing is there.

Reported on production on 2026-11-27: a shared link opened on the home page
(the "What should we assess?" box and "No runs yet" in the rail) for about a
second before the report, and a signed-in visit with seven runs showed "No
runs yet", no account and no "you have an assessment in progress" line for
about a second before all three appeared.

Measured on main (8e232ac) on 2026-11-28 in Chromium against the real app on
loopback (accounts on, no access codes, fixture runs only) under DevTools'
"Slow 4G" preset (562.5 ms latency, 1.44 Mbit/s down): the document arrived
at 1.0 s and was painted from 2.2 s; the modules finished loading at 6.0 s.

- Shared link, anonymous: from 2.2 s to 6.6 s the composer, its topic box and
  "No runs yet" were on screen. That was the markup itself, painted while the
  scripts loaded, and then the access check (6.0 to 6.6 s). From 6.6 to 7.2 s
  the run pane read "…" over an "Unknown state" pill. The requests were
  serial: access check 6.0 to 6.6 s, then progress 6.6 to 7.2 s, then the
  decision, scores, report and sources reads together from 7.2 s.
- Signed-in home, seven runs and one in progress: "No runs yet" and no account
  from 2.2 to 6.6 s, then an empty rail with no in-progress line to 7.2 s. The
  access check ran 6.0 to 6.6 s and the history was asked for only after it,
  6.6 to 7.2 s.

What the page does now:

- The markup opens on a loading view (#pane-loading), loading rows in the rail
  and a placeholder where the account will be; the composer starts hidden.
  Nothing on the first paint says anything about this visitor.
- A run's place says it is being read until its first answer (app.js openRun):
  no header with a placeholder title and an unknown state.
- The reads that do not depend on the access check's answer are sent beside it
  (app.js startBootReads): a run's progress on /run/<id>, since a run's reads
  are a capability the server answers without asking who the reader is; and
  the history's first page when an identity is stored, since the list is
  asked with that identity anyway and the check decides only whether its reply
  is used (sidebar.js prefetch).
- A read that fails says so in place of the loading view: the rail with a
  "Try again" button, the run with a line that it is being retried. The boot's
  access check is bounded (BOOT_READ_TIMEOUT_MS), and a check that never
  answers ends in the existing notice with its reload button.

Measured again with the change, the same way: from 2.2 s until the check
answered (6.7 s) both pages showed the loading view, the rail's loading rows
and the account placeholder. The shared link's progress ran beside the check
(6.1 to 6.7 s) and its report was up at 6.7 s instead of 7.2 s; the signed-in
history ran beside it too (6.1 to 6.7 s) and the seven runs and the in-progress
line were up at 6.7 s instead of 7.2 s. No frame showed the composer before
the boot had decided, "No runs yet", or a run state of "Unknown".

The behaviour is exercised in tests/js/landing_contract.mjs (the boot) and
tests/js/sidebar_history_contract.mjs (the rail) with the shipped modules, and
in Chromium by e2e/composer_smoke.py (_loading_journey), which holds each read
and fails on any painted frame that shows the composer or "No runs yet" before
the page knows. The checks here keep in place what those rely on.
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_WEB = _ROOT / "web"
_INDEX = (_WEB / "index.html").read_text(encoding="utf-8")
_APP = (_WEB / "static/js/app.js").read_text(encoding="utf-8")
_API = (_WEB / "static/js/api.js").read_text(encoding="utf-8")
_RUN = (_WEB / "static/js/run.js").read_text(encoding="utf-8")
_SIDEBAR = (_WEB / "static/js/sidebar.js").read_text(encoding="utf-8")
_STRINGS = (_WEB / "static/js/i18n.js").read_text(encoding="utf-8")
_STYLES = (_WEB / "static/css/workbench.css").read_text(encoding="utf-8")

_KEYS = ("page_loading", "runs_loading", "runs_read_failed", "runs_retry", "run_loading", "run_loading_failed")


def _opening(element_id: str) -> str:
    at = _INDEX.index(f'id="{element_id}"')
    return _INDEX[_INDEX.rindex("<", 0, at):_INDEX.index(">", at) + 1]


def _between(start: str, end: str) -> str:
    at = _INDEX.index(start)
    return _INDEX[at:_INDEX.index(end, at)]


def test_the_page_opens_on_a_loading_view_not_the_composer():
    loading = _opening("pane-loading")
    assert loading.startswith('<section class="pane pane--loading"'), loading
    assert " hidden" not in loading, "Shown from the first paint, before any script has run"
    assert 'role="status"' in loading and 'aria-busy="true"' in loading
    body = _between('id="pane-loading"', "</section>")
    assert 'class="loading-view"' in body
    assert re.search(r'<span class="visually-hidden" data-i18n="page_loading">[^<]+</span>', body), (
        "Said to a screen reader, in the interface's words once i18n.js runs")
    compose = _opening("pane-compose")
    assert re.search(r"\shidden>$", compose), "The composer is shown by the page once it knows whose page this is"
    main = _INDEX.index('<main class="main" id="main">')
    assert main < _INDEX.index('id="pane-loading"') < _INDEX.index('id="pane-compose"')


def test_the_rail_starts_loading_and_never_says_no_runs_before_the_server():
    rail = _between('<nav class="runlist" id="runlist"', "</nav>")
    assert 'data-i18n="no_runs"' not in rail and "No runs yet" not in rail
    assert 'data-state="loading"' in _opening("runlist")
    assert '<div class="runlist__loading" role="status" aria-busy="true">' in rail
    assert '<span class="visually-hidden" data-i18n="runs_loading">' in rail
    assert rail.count('<span class="runlist__loading-row"></span>') >= 3


def test_where_the_account_will_be_there_is_a_placeholder_until_the_check_answers():
    placeholder = _opening("identity-loading")
    assert 'aria-hidden="true"' in placeholder and " hidden" not in placeholder
    foot = _INDEX.index('id="identity-loading"')
    assert _INDEX.index('id="runlist"') < foot < _INDEX.index('id="account-badge"')
    ensure = _APP[_APP.index("async function ensureAccess() {"):]
    ensure = ensure[:ensure.index("\n}\n")]
    assert 'identityKnown();' in ensure, "Put away however the boot ends"
    gate = _APP[_APP.index("function showGate("):]
    assert "identityKnown();" in gate[:gate.index("\n  const gate = ")], "...and when the card comes up instead"


def test_every_loading_and_failure_string_is_in_both_languages():
    for key in _KEYS:
        assert _STRINGS.count(f"    {key}: ") == 2, key
    chinese_at = _STRINGS.index('\n  "Simplified Chinese": {')
    english = dict(re.findall(r'^    (\w+): "([^"]*)",$', _STRINGS[_STRINGS.index("\n  English: {"):chinese_at], re.M))
    chinese = dict(re.findall(r'^    (\w+): "([^"]*)",$', _STRINGS[chinese_at:_STRINGS.index("\n};\n", chinese_at)], re.M))
    for key in _KEYS:
        assert re.search(r"[一-鿿]", chinese[key]), f"{key} is Chinese in the Chinese interface"
        assert english[key] and not re.search(r"[一-鿿]", english[key]), key
    # A failed read is not an empty one, and the page keeps trying by itself.
    assert "retry" in english["run_loading_failed"].lower() or "trying" in english["run_loading_failed"].lower()
    assert "重试" in chinese["run_loading_failed"]


def test_the_loading_styles_take_the_page_tokens_and_hold_still_for_reduced_motion():
    for selector in (".loading-view", ".loading-view__line", ".runlist__loading-row", ".identity-loading"):
        assert re.search(rf"^{re.escape(selector)}[ ,{{]", _STYLES, re.M), selector
    shimmer = re.search(r"^\.loading-view__line,\n\.runlist__loading-row,\n\.identity-loading span \{(.*?)\n\}",
                        _STYLES, re.M | re.S)
    assert shimmer, "One shimmer for all three"
    assert "var(--bg-raised)" in shimmer.group(1) and "var(--bg-hover)" in shimmer.group(1)
    reduced = _STYLES[_STYLES.index("@media (prefers-reduced-motion: reduce)"):]
    assert ".loading-view__line" in reduced[:reduced.index("\n}\n")] and "animation: none" in reduced[:reduced.index("\n}\n")]


def test_the_boot_bounds_its_access_check():
    bound = re.search(r"^const BOOT_READ_TIMEOUT_MS = ([\d_]+);$", _APP, re.M)
    assert bound and int(bound.group(1).replace("_", "")) == 15_000, "As long as a progress read may take"
    decide = _APP[_APP.index("async function decideAccess() {"):]
    decide = decide[:decide.index("\n}\n")]
    assert "api.checkAccess(api.getAccessCode(), { timeoutMs: BOOT_READ_TIMEOUT_MS })" in decide
    check = _API[_API.index("export const checkAccess"):]
    check = check[:check.index(";\n")]
    assert "AbortSignal.timeout(timeoutMs)" in check, "Only the boot's check is bounded; the gate's own checks are not"
    lists = _API[_API.index("export const listRuns"):]
    assert "AbortSignal.timeout(" in lists[:lists.index(";\n")], "A history read cannot hold the rail's loading rows for ever"


def test_the_run_poll_takes_the_boots_early_read_as_its_first():
    follow = _RUN[_RUN.index("export function follow("):]
    assert follow.startswith("export function follow(runId, { onUpdate, onDone, onError, onConnection }, { first = null } = {}) {")
    ask = follow[:follow.index("async function tick()")]
    assert "first ?? api.getProgress(runId, seenSteps)" in ask and "first = null;" in ask
    assert "export function prefetch()" in _SIDEBAR and "export function forgetPrefetch()" in _SIDEBAR
    assert "export function loading(container)" in _SIDEBAR
