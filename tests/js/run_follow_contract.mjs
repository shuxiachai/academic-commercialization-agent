// The run follower's poll(): ask now instead of at the next interval.
//
// A run past its first ninety seconds is polled every four. After the user
// cancels it, the header went on saying "running" until the next poll came
// round. poll() lets the page ask at once. The real run.js and api.js are
// used; fetch is intercepted and answered by this file, and no timer is
// waited on: every assertion is about what was requested immediately.
import assert from "node:assert/strict";

globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
globalThis.sessionStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };

const requests = [];
globalThis.fetch = (url) => new Promise((resolve) => requests.push({ url, resolve }));
const answer = (index, body) => requests[index].resolve(new Response(JSON.stringify(body), {
  status: 200, headers: { "Content-Type": "application/json" } }));
const progress = (state) => ({ state, steps: [], steps_next_cursor: 0, stage: "", artifacts: [] });
const settle = async () => { for (let i = 0; i < 10; i++) await new Promise((resolve) => setImmediate(resolve)); };

const runView = await import("../../web/static/js/run.js");
const scenario = process.argv[2];

const scenarios = {
  async asks_now() {
    const updates = [];
    const handle = runView.follow("run-one", { onUpdate: (p) => updates.push(p.state) });
    assert.equal(requests.length, 1, "Following asks once at the start");
    answer(0, progress("running"));
    await settle();
    assert.deepEqual(updates, ["running"]);
    assert.equal(requests.length, 1, "The next question waits for its interval");
    handle.poll();
    assert.equal(requests.length, 2, "poll() asks now");
    answer(1, progress("cancelled"));
    await settle();
    assert.deepEqual(updates, ["running", "cancelled"]);
    handle.poll();
    assert.equal(requests.length, 2, "A run that has ended is not asked about again");
    handle.stop();
  },
  async not_twice_at_once() {
    const updates = [];
    const handle = runView.follow("run-one", { onUpdate: (p) => updates.push(p.state) });
    handle.poll();
    handle.poll();
    assert.equal(requests.length, 1, "A question already out is not asked again beside itself");
    // That answer may have been formed before the cancel took effect, so the
    // follower asks once more as soon as it arrives rather than in four seconds.
    answer(0, progress("running"));
    await settle();
    assert.equal(requests.length, 2, "...but its answer is followed by the one poll() asked for");
    answer(1, progress("running"));
    await settle();
    assert.equal(requests.length, 2, "One extra question, not a stream of them");
    handle.stop();
  },
  async not_after_stop() {
    const handle = runView.follow("run-one", {});
    answer(0, progress("running"));
    await settle();
    handle.stop();
    handle.poll();
    assert.equal(requests.length, 1, "A view that was left asks nothing more");
  },
};

const run = scenarios[scenario];
if (!run) throw new Error(`Unknown scenario ${scenario}`);
await run();
console.log(`PASS ${scenario}`);
process.exit(0);
