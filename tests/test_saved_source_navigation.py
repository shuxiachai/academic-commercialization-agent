"""SPA locator links follow logical run state, not fragile history state."""

import json
from pathlib import Path
import subprocess

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
RUN_A = "20260926T010101Z-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
RUN_B = "20260926T020202Z-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def test_locator_link_is_stable_and_server_fragment_is_capability_only(monkeypatch):
    """The served SPA has one stable locator anchor and never emits unsafe fragments."""
    # _spa only needs the registration sentinel to project the optional link;
    # isolate that server-rendered seam without reloading the global ASGI app.
    from api import main

    monkeypatch.setattr(main, "_source_locator", object())
    client = TestClient(main.app)
    home = client.get("/")
    assert home.status_code == 200
    assert home.text.count('id="source-locator-link"') == 1
    assert 'href="/source-locator"' in home.text
    deep = client.get(f"/run/{RUN_A}")
    assert deep.status_code == 200
    assert f'href="/source-locator#{RUN_A}"' in deep.text
    malformed = client.get("/run/not-a-run")
    assert malformed.status_code == 200
    assert 'href="/source-locator"' in malformed.text
    assert "not-a-run" not in malformed.text.split('id="source-locator-link"', 1)[1].split(">", 1)[0]
    monkeypatch.setattr(main, "_source_locator", None)
    disabled = client.get(f"/run/{RUN_A}")
    assert disabled.status_code == 200
    assert 'id="source-locator-link"' not in disabled.text


def test_real_spa_view_functions_update_and_clear_the_locator_fragment():
    """Execute shipped view functions; reinjecting old sync omission leaves A stale at B."""
    source = (ROOT / "web/static/js/app.js").read_text(encoding="utf-8")
    probe = r'''
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const {source, A, B} = JSON.parse(fs.readFileSync(0, 'utf8'));
const between = (start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));
const query = between('const $ =', 'const $$ =');
const stop = between('function stopFollowing()', 'const locatorRunPattern');
const locator = between('const locatorRunPattern', 'function showCompose()');
const compose = between('function showCompose()', 'function showRun(runId)');
const showRun = between('function showRun(runId)', '/* ── Run pane');
const route = between('function routeFromLocation()', 'window.addEventListener');
for (const part of [stop, locator, compose, showRun, route]) assert.ok(part.length > 40, 'real function extraction');
function runtime({ old = false, absent = false } = {}) {
  const link = { href: '/source-locator' }, composePane = { hidden: true }, runPane = { hidden: false }, topic = { focus() {} };
  const ids = {'source-locator-link': link, 'pane-compose': composePane, 'pane-run': runPane, topic};
  if (absent) delete ids['source-locator-link'];
  // Use the shipped $ helper with the same DOM API as the composer harness.
  const context = { document: { querySelector: sel => ids[sel.slice(1)] ?? null }, location: { pathname: '/' }, topic,
    history: { pushState() {} }, stopClock() {}, refreshSidebar() {}, scheduleCapacity() {}, toast() {}, t: x => x,
    openRun: id => { context.opened = id; } };
  const active = 'let activeRunId = null; let follower = null;';
  const oldShowRun = showRun.replace('  syncSourceLocatorLink();\n', '');
  assert.notEqual(oldShowRun, showRun, 'negative control actually removes the hook');
  const body = [query, active, stop, locator, compose, old ? oldShowRun : showRun, route,
    'globalThis.probe = { showRun, showCompose, routeFromLocation, syncSourceLocatorLink, active: () => activeRunId, href: () => $("#source-locator-link").href };'].join('\n');
  vm.runInNewContext(body, context);
  return { ...context, link, composePane, runPane };
}
const live = runtime();
live.probe.showRun(A); assert.equal(live.probe.href(), `/source-locator#${A}`);
live.probe.showRun(B); assert.equal(live.probe.href(), `/source-locator#${B}`);
live.location.pathname = '/'; live.probe.routeFromLocation(); assert.equal(live.probe.href(), '/source-locator');
const old = runtime({old: true});
live.location.pathname = '/run/' + A;
live.history.pushState = () => { throw Error('history unavailable'); };
live.probe.showRun(B); assert.equal(live.link.href, '/source-locator#' + B);
assert.equal(live.location.pathname, '/run/' + A, 'logical view wins over stale URL');
live.probe.showCompose(); assert.equal(live.link.href, '/source-locator');
assert.equal(live.composePane.hidden, false); assert.equal(live.runPane.hidden, true);
assert.equal(live.probe.active(), null);
live.probe.showRun(B); live.location.pathname = '/'; live.probe.routeFromLocation();
assert.equal(live.link.href, '/source-locator'); assert.equal(live.probe.active(), null);
for (const bad of [null, 42, {}, [A], {toString() { throw Error('must not coerce'); }},
  A + '\n', A + '?code=secret', A + '#receipt', '<img>', '../run/' + A, A.toUpperCase()]) {
  live.probe.syncSourceLocatorLink(bad); assert.equal(live.link.href, '/source-locator');
}
const absent = runtime({absent: true});
absent.probe.showRun(B); absent.probe.showCompose(); absent.probe.routeFromLocation();
old.probe.showRun(A); old.probe.showRun(B);
assert.equal(old.probe.href(), '/source-locator', 'controlled old function cannot manufacture a current link');
old.link.href = '/source-locator#' + A;
old.probe.showRun(B);
assert.throws(() => assert.equal(old.probe.href(), `/source-locator#${B}`), /Expected values/);
console.log('real SPA view probe and stale-link reinjection verified');
'''
    completed = subprocess.run(["node", "--input-type=module", "-e", probe],
                               input=json.dumps({"source": source, "A": RUN_A, "B": RUN_B}),
                               capture_output=True, text=True, encoding="utf-8", timeout=15, check=False)
    assert completed.returncode == 0, completed.stderr
    assert "real SPA view probe and stale-link reinjection verified" in completed.stdout
