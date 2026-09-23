"""Production projections cannot mutate frozen scripts or omit consent hooks."""

import json
import subprocess

import pytest

from api import saved_source_production_assets as assets


def test_exact_aliases_preserve_frozen_bytes():
    """Directory mounting exposed unrelated lab files; only named aliases ship."""
    for name, path in (
        ("result.js", "saved-source-receipts/result.js"),
        ("receipt.css", "saved-source-receipts/app.css"),
    ):
        reply = assets.asset_response(name)
        assert reply.status_code == 200
        assert reply.body == (assets.WEB_ROOT / path).read_bytes()
    for name in ("../app.js", "index.html", "result.js/anything", "app.js"):
        assert assets.asset_response(name).status_code == 404


def test_production_only_script_hooks_and_import():
    """Consent must run before storage and cannot be attached to recovery GET."""
    original = (assets.WEB_ROOT / "saved-source-receipts/app.js").read_text(encoding="utf-8")
    reply = assets.asset_response("receipt.js")
    assert reply.status_code == 200
    script = reply.body.decode()
    assert script.index("if (beforeSubmit() !== true) return;") < script.index("if (!recover && !beginIntent()) return;")
    assert script.index("const candidate = requestHeaders();") < script.index("if (!recover && !beginIntent()) return;")
    assert 'headers: { ...extraHeaders, "Idempotency-Key": input.key, "X-Access-Code": input.code }' in script
    assert 'beforeSubmit = () => true, requestHeaders = () => ({})' in script
    assert "beforeSubmit" not in original and "requestHeaders" not in original
    assert (assets.WEB_ROOT / "saved-source-receipts/app.js").read_text(encoding="utf-8") == original
    accounting = (assets.WEB_ROOT / "saved-source-usage/accounting.js").read_bytes()
    assert accounting.count(b"/receipt-static/result.js") == 1
    assert assets.asset_response("accounting.js").body == accounting.replace(
        b"/receipt-static/result.js", b"/source-locator-static/result.js", 1)


@pytest.mark.parametrize("anchor", [
    "  clearExtra = () => {}, renderExtra = () => {},\n",
    "  if (!recover && !beginIntent()) return;",
    'headers: { "Idempotency-Key": input.key, "X-Access-Code": input.code },',
])
@pytest.mark.parametrize("mode", ["missing", "duplicate"])
def test_script_anchor_drift_refuses_projection(anchor, mode):
    """A vendor/script change cannot silently serve a partially hooked page."""
    original = (assets.WEB_ROOT / "saved-source-receipts/app.js").read_text(encoding="utf-8")
    changed = original.replace(anchor, "") if mode == "missing" else original + anchor
    with pytest.raises(ValueError, match="asset_contract_changed"):
        assets.receipt_script(changed)


@pytest.mark.parametrize("allowed", [False, True])
def test_execution_marker_is_fixed_server_boolean(tmp_path, allowed):
    """HTML must reflect execution mode without interpolating a client value."""
    directory = tmp_path / "source-locator"
    directory.mkdir()
    page = directory / "index.html"
    page.write_text('<html data-execution="{{SOURCE_LOCATOR_EXECUTION_ALLOWED}}">', encoding="utf-8")
    reply = assets.page_response(allowed, root=tmp_path)
    assert reply.status_code == 200
    assert reply.body == f'<html data-execution="{str(allowed).lower()}">'.encode()
    page.write_text("missing-marker", encoding="utf-8")
    assert assets.page_response(allowed, root=tmp_path).status_code == 503


def test_projected_hook_exceptions_precede_storage_and_get_never_calls_hooks():
    """Execute the served pre-intent block: hook faults cannot strand a receipt."""
    script = assets.asset_bytes("receipt.js").decode()
    probe = r'''
import assert from 'node:assert/strict';
import fs from 'node:fs';
const source = JSON.parse(fs.readFileSync(0, 'utf8'));
const block = source.slice(source.indexOf('  let extraHeaders = {};'), source.indexOf('  const input ='));
const execute = new Function('recover', 'beforeSubmit', 'requestHeaders', 'beginIntent', 'status', block + '\nreturn extraHeaders;');
let stores = 0, errors = 0, hookCalls = 0;
const begin = () => { stores++; return true; };
const status = () => { errors++; };
const throwHook = () => { hookCalls++; throw Error('private hook detail'); };
execute(false, throwHook, throwHook, begin, status);
assert.equal(stores, 0); assert.equal(errors, 1); assert.equal(hookCalls, 1);
execute(false, () => true, throwHook, begin, status);
assert.equal(stores, 0); assert.equal(errors, 2); assert.equal(hookCalls, 2);
execute(false, () => false, throwHook, begin, status);
assert.equal(stores, 0); assert.equal(hookCalls, 2);
execute(true, throwHook, throwHook, begin, status);
assert.equal(stores, 0); assert.equal(errors, 2); assert.equal(hookCalls, 2);
for (const candidate of [null, [], {}, {Authorization: 'bad'},
  {'X-Source-Locator-Consent': 'question-catalog-v1', 'Idempotency-Key': 'bad'},
  {'X-Source-Locator-Consent': 'wrong'},
  Object.create({'X-Source-Locator-Consent': 'question-catalog-v1'}),
  Object.defineProperty({}, 'X-Source-Locator-Consent', {get: throwHook})]) {
  execute(false, () => true, () => candidate, begin, status);
  assert.equal(stores, 0);
}
assert.equal(hookCalls, 2, 'Accessors must not be read');
assert.deepEqual(execute(false, () => true, () => ({'X-Source-Locator-Consent': 'question-catalog-v1'}), begin, status),
  {'X-Source-Locator-Consent': 'question-catalog-v1'});
assert.equal(stores, 1);
console.log('served pre-intent hooks verified');
'''
    completed = subprocess.run(["node", "--input-type=module", "-e", probe], input=json.dumps(script),
                               capture_output=True, text=True, timeout=15, check=False)
    assert completed.returncode == 0, completed.stderr
    assert "served pre-intent hooks verified" in completed.stdout
