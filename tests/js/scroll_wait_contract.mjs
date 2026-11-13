/* The browser smoke's wait for a page that has come to rest, on a scripted clock.
 *
 * argv: <file holding the wait's source> <scenario>
 *
 * A timeline is a list of frames, each [ms since the last frame, position].
 * The position is window.scrollY, or the top of the watched heading inside
 * the window (null: the heading is not in the document). After the last frame
 * the page stays where it is, one frame every 16 ms.
 */
import assert from "node:assert/strict";
import fs from "node:fs";

const [file, scenario] = process.argv.slice(2);
const source = fs.readFileSync(file, "utf8");

// One page for the whole scenario, as the smoke has: what a wait leaves on it, the next one finds.
const world = { now: 1000, position: 0, id: null, queued: null };
globalThis.performance = { now: () => world.now };
// While a heading is watched the page's own position is a number that never changes, so a wait
// that read the page instead of the heading would see stillness and never an arrival.
globalThis.window = { get scrollY() { return world.id === null ? world.position : 7777; } };
globalThis.document = {
  getElementById: (wanted) => (wanted === world.id && world.position !== null
    ? { getBoundingClientRect: () => ({ top: world.position }) } : null),
};
globalThis.requestAnimationFrame = (callback) => { world.queued = callback; };

function run(frames, id = null) {
  let settled = null, count = 0;
  const timeline = frames.slice(1);
  Object.assign(world, { position: frames[0][1], id, queued: null });
  const began = world.now;
  const wait = (0, eval)(`(${source})`)(id);
  wait.then((value) => { settled = { ok: true, value }; }, (error) => { settled = { ok: false, message: error.message }; });
  const step = async () => {
    const [gap, next] = timeline.length ? timeline.shift() : [16, world.position];
    world.now += gap;
    world.position = next;
    count += 1;
    const callback = world.queued;
    world.queued = null;
    if (callback) callback(world.now);
    await Promise.resolve();
    await Promise.resolve();
  };
  return {
    async finish(limit = 5000) {
      while (settled === null && count < limit) await step();
      assert(settled !== null, `the wait had not settled after ${count} frames`);
      return { ...settled, frames: count, ms: world.now - began };
    },
  };
}

const still = (count, gap = 16, at = 0) => Array.from({ length: count }, () => [gap, at]);
const glide = (from, to, count, gap = 16) =>
  Array.from({ length: count }, (_, i) => [gap, Math.round(from + ((to - from) * (i + 1)) / count)]);

const scenarios = {
  /* The defect this replaces: the key is pressed, nothing has moved yet, and the
   * old wait, holding the last key's sample, called that stillness. */
  async waits_for_a_scroll_that_has_not_begun() {
    for (const lead of [1, 2, 3, 4, 5]) {
      const frames = [[0, 0], ...still(lead), ...glide(0, 1515, 30)];
      const done = await run(frames).finish();
      assert.equal(done.ok, true);
      assert.equal(done.value, 1515, `a scroll beginning ${lead} frames after the key is waited out`);
      assert(done.frames >= lead + 30 + 6, `${done.frames} frames with a lead of ${lead}`);
    }
  },
  async nothing_from_an_earlier_wait_is_used() {
    // Two waits on one page, as two key presses make them. The second starts at the
    // position the first one ended on, and must not take that as its answer.
    const first = await run([[0, 0], ...glide(0, 900, 20)]).finish();
    assert.equal(first.value, 900);
    assert.deepEqual(Object.keys(globalThis.window), ["scrollY"], "the wait leaves nothing on the page");
    const second = await run([[0, 900], ...still(3, 16, 900), ...glide(900, 1482, 20)]).finish();
    assert.equal(second.value, 1482);
  },
  async a_still_page_costs_six_frames_and_a_tenth_of_a_second() {
    const quick = await run([[0, 40]]).finish();
    assert.equal(quick.ok, true);
    assert.equal(quick.value, 40);
    assert(quick.frames >= 6 && quick.frames <= 8, `${quick.frames} frames at 16 ms`);
    assert(quick.ms >= 100 && quick.ms <= 130, `${quick.ms} ms at 16 ms a frame`);
    // Fast frames: six of them are over in 30 ms, which is not yet a tenth of a second.
    const fast = await run([[0, 40], ...still(40, 5, 40)]).finish();
    assert(fast.ms >= 100 && fast.ms <= 110, `${fast.ms} ms at 5 ms a frame`);
    assert(fast.frames >= 20, `${fast.frames} frames at 5 ms`);
  },
  async a_stalled_page_is_not_a_still_one() {
    // No frame for 400 ms: time passed, but the page was never looked at while it
    // could have moved. Six frames are still owed after the stall.
    const frames = [[0, 0], [400, 0], [16, 0], [16, 0], ...glide(0, 600, 20)];
    const done = await run(frames).finish();
    assert.equal(done.value, 600);
    const slow = await run([[0, 0], ...still(5, 60), ...glide(0, 300, 10, 60)]).finish();
    assert.equal(slow.value, 300, "five slow frames are 300 ms and still not six looks");
    // Looks from before a movement do not count after it: five still frames, a scroll,
    // one frame after a stall, and the scroll goes on.
    const again = await run([[0, 0], ...still(5), ...glide(0, 300, 10), [400, 300], ...glide(300, 600, 10)]).finish();
    assert.equal(again.value, 600);
  },
  async a_pause_in_the_middle_starts_the_count_again() {
    const frames = [[0, 0], ...glide(0, 400, 10), ...still(5, 16, 400), ...glide(400, 800, 10)];
    const done = await run(frames).finish();
    assert.equal(done.value, 800);
    // The tenth of a second is counted from the last movement, not from the start:
    // 200 ms of scrolling at 5 ms a frame, then at least 100 ms of rest.
    const quick = await run([[0, 0], ...glide(0, 500, 40, 5), ...still(60, 5, 500)]).finish();
    assert.equal(quick.value, 500);
    assert(quick.ms >= 300 && quick.ms <= 310, `${quick.ms} ms`);
  },
  async a_page_that_never_rests_is_an_error_that_says_so() {
    const done = await run([[0, 0], ...glide(0, 100000, 1200)]).finish();
    assert.equal(done.ok, false);
    assert.match(done.message, /still moving after 15000 ms/);
    assert.match(done.message, /page/);
    assert(done.ms >= 15000 && done.ms < 15100, `${done.ms} ms`);
  },
  async a_heading_is_waited_for_until_it_rests_near_the_top() {
    const done = await run([[0, 2400], ...glide(2400, 24, 30)], "section-3").finish();
    assert.equal(done.ok, true);
    assert.equal(done.value, 24);
    for (const top of [0, 64]) {
      const edge = await run([[0, top]], "section-3").finish();
      assert.equal(edge.ok, true, `${top} px from the top is near it`);
    }
  },
  async a_heading_that_rests_elsewhere_fails_and_says_where() {
    // What the four CI failures looked like: the URL named the section, the page
    // had stopped, and the heading was most of a screen away.
    for (const top of [968, 65, -1]) {
      const done = await run([[0, 2400], ...glide(2400, top, 20)], "section-1").finish();
      assert.equal(done.ok, false, `${top} px is not near the top`);
      assert.match(done.message, /#section-1/);
      assert(done.message.includes(`${top} px`), done.message);
      assert.match(done.message, /came to rest/);
      assert(done.ms >= 15000, `${done.ms} ms: the jump is given the whole limit to begin`);
    }
  },
  async a_heading_still_on_its_way_is_not_judged_early() {
    // Far from the top and unmoved for a moment (the jump has not begun), then it comes.
    const frames = [[0, 2400], ...still(10, 16, 2400), ...glide(2400, 24, 30)];
    const done = await run(frames, "section-2").finish();
    assert.equal(done.ok, true);
    assert.equal(done.value, 24);
  },
  async a_heading_that_is_not_there_yet_is_waited_for() {
    const frames = [[0, null], ...still(30, 16, null), [16, 2400], ...glide(2400, 24, 20)];
    const done = await run(frames, "section-4").finish();
    assert.equal(done.ok, true);
    assert.equal(done.value, 24);
    const never = await run([[0, null]], "section-9").finish();
    assert.equal(never.ok, false);
    assert.match(never.message, /#section-9/);
    assert.match(never.message, /not in the document/);
    assert(never.ms >= 15000, `${never.ms} ms`);
  },
};

assert(scenarios[scenario], `unknown scenario ${scenario}`);
await scenarios[scenario]();
console.log(`PASS ${scenario}`);
