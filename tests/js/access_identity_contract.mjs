/* Two documents share persistent storage, never providers or browser mocks of auth. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const [scenario, variant] = process.argv.slice(2);
const source = fs.readFileSync(new URL('../../web/static/js/api.js', import.meta.url), 'utf8')
  .replace(/export /g, '');
const disk = new Map([['access-code', 'fixture-A']]);
let readDenied = false, removeDenied = false;
const shared = {
  getItem: key => { if (readDenied) throw Error('fixture read denied'); return disk.get(key) ?? null; },
  setItem: (key, value) => disk.set(key, value),
  removeItem: key => { if (removeDenied) throw Error('fixture remove denied'); disk.delete(key); },
};
function tab() {
  const requests = [], session = new Map();
  const context = vm.createContext({localStorage: shared, FormData, File,
    sessionStorage: {getItem: key => session.get(key) ?? null,
      setItem: (key, value) => session.set(key, value), removeItem: key => session.delete(key)},
    fetch: (path, options) => new Promise(resolve => requests.push({path, options, resolve})),
  });
  vm.runInContext(source, context);
  const run = code => vm.runInContext(code, context);
  const respond = (index, status = 200) => requests[index].resolve(new Response('{}', {
    status, headers: {'Content-Type': 'application/json'},
  }));
  return {run, requests, respond};
}
const a = tab(), b = tab();
assert.equal(a.run('getAccessCode()'), 'fixture-A');

if (scenario === 'cross_tab') {
  b.run("setAccessCode('fixture-B')");
  const expression = variant === 'run' ? "startRun({topic:'Fixture topic'})"
    : variant === 'pdf' ? "uploadPaper(new File(['%PDF-fixture'],'fixture.pdf'))"
    : variant === 'resume' ? "resumeRun('fixture-parent')"
    : variant === 'delete' ? "deleteRun('fixture-parent')" : 'listRuns()';
  const pending = a.run(expression);
  assert.equal(a.requests[0].options.headers['X-Access-Code'], 'fixture-A',
    'A document cannot silently send another tab\'s selected payer');
  a.respond(0); await pending;
  assert.equal(b.run('getAccessCode()'), 'fixture-B');
  const fresh = tab();
  assert.equal(fresh.run('getAccessCode()'), 'fixture-B', 'A new document reads the persisted selection');
} else if (scenario === 'rejected_request') {
  const candidate = variant === 'candidate';
  const pending = a.run(candidate ? "checkAccess('fixture-invalid')" : 'listRuns()');
  if (variant === 'same_page') a.run("setAccessCode('fixture-B')");
  if (variant === 'aba') a.run("setAccessCode('fixture-B'); setAccessCode('fixture-A')");
  if (variant === 'other_tab') b.run("setAccessCode('fixture-B')");
  if (variant === 'other_logout') b.run('setAccessCode(null)');
  a.respond(0, 401);
  await assert.rejects(pending, error => error.status === 401);
  const expected = variant === 'same_page' ? 'fixture-B'
    : ['aba', 'candidate'].includes(variant) ? 'fixture-A' : null;
  const read = a.run('health()');
  assert.equal(a.requests[1].options.headers['X-Access-Code'] ?? null, expected,
    'A stale or candidate 401 cannot clear the current document selection');
  a.respond(1); await read;
  assert.equal(disk.get('access-code') ?? null, variant === 'other_tab' ? 'fixture-B' : expected,
    'An old rejection cannot erase another tab\'s persisted selection');
} else if (scenario === 'logout') {
  if (variant === 'other_tab') b.run("setAccessCode('fixture-B')");
  if (variant === 'other_logout') b.run('setAccessCode(null)');
  if (variant === 'read_denied') readDenied = true;
  if (variant === 'remove_denied') removeDenied = true;
  const cleared = a.run('setAccessCode(null)');
  assert.equal(cleared, variant === 'normal');
  assert.equal(a.run('getAccessCode()'), null, 'Local logout must not resurrect any stored credential');
  assert.equal(disk.get('access-code') ?? null, variant === 'other_tab' ? 'fixture-B'
    : variant.endsWith('_denied') ? 'fixture-A' : null);
  assert.equal(a.run('accessCodeClearConflict()'), ['other_tab', 'other_logout'].includes(variant),
    'A different persistent selection is not a storage outage');
  assert.equal(a.run('storageDegraded()'), variant.endsWith('_denied'));
} else throw Error(`Unknown scenario ${scenario}`);
console.log(`PASS ${scenario} ${variant}`);
