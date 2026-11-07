/* Two runs side by side: the rows are right, and what is missing is shown
 * as missing rather than as a number. Runs the shipped module with a fake
 * document; nothing here opens a socket. */
import assert from "node:assert/strict";

globalThis.localStorage = { getItem: () => null, removeItem: () => {}, setItem: () => {} };
globalThis.sessionStorage = { getItem: () => null };

class Element {
  constructor(tag) {
    Object.assign(this, { tag, children: [], listeners: {}, dataset: {}, className: "", textContent: "", hidden: false });
  }
  append(...nodes) { this.children.push(...nodes); }
  addEventListener(event, handler) { this.listeners[event] = handler; }
  set innerHTML(value) { this.children = []; }
  get text() { return this.children.length ? this.children.map((c) => c.text).join("|") : this.textContent; }
  find(pred) {
    if (pred(this)) return this;
    for (const child of this.children) { const hit = child.find(pred); if (hit) return hit; }
    return null;
  }
  all(pred, out = []) {
    if (pred(this)) out.push(this);
    for (const child of this.children) child.all(pred, out);
    return out;
  }
}
globalThis.document = { createElement: (tag) => new Element(tag) };

const compare = await import("../../web/static/js/compare.js");

const SCORES_A = { overall_score: 48.6, trl_score: 5, mrl_score: 5, patent_strength: 3, market_accessibility: 2,
  key_risks: ["Lack of field data"], trl_source_ids: ["A1"] };
const SCORES_B = { overall_score: 61.2, trl_score: 6, mrl_score: 5, patent_strength: 4, market_accessibility: 3,
  key_risks: ["Manufacturing scale"], trl_source_ids: ["A2"] };
const REPORT = "# Report\n\n## Executive summary\n\nThe technology is at pilot stage. More follows.\n\n## Commercialization Opportunities\n\n1. Run a field trial.\n";
const run = (id, state, scores, markdown = REPORT, extra = {}) => ({
  id, scores, markdown,
  status: { state, topic: `Topic ${id.slice(-2)}`, source_counts: { academic: 3, patent: 2, market: 4 },
    usage: { agents: [{ model: "qwen3.8-flash" }] }, ...extra },
});
const A = "20261021T022241Z-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const B = "20261105T090000Z-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

const scenarios = {
  rows() {
    const model = compare.comparison(run(A, "completed", SCORES_A), run(B, "completed", SCORES_B));
    assert.equal(model.same, false);
    assert.deepEqual(model.rows.map((r) => [r.key, ...r.values, r.delta]), [
      ["overall_score", 48.6, 61.2, 12.6],
      ["trl_score", 5, 6, 1],
      ["mrl_score", 5, 5, 0],
      ["patent_strength", 3, 4, 1],
      ["market_accessibility", 2, 3, 1],
    ], "the difference is B minus A, to a tenth; a dimension neither run scored is left out");
    const [a, b] = model.sides;
    assert.equal(a.topic, "Topic aa");
    assert.equal(a.startedAt.toISOString(), "2026-10-21T02:22:41.000Z", "the start is read from the id, in UTC");
    assert.equal(b.model, "qwen3.8-flash");
    assert.equal(a.brief.summary, "The technology is at pilot stage.");
    assert.equal(a.brief.risk, "Lack of field data");
    assert.equal(a.brief.next, "Run a field trial.");
    assert.equal(a.brief.weakest.key, "market_accessibility");
  },
  unfinished() {
    // A failed run has no scorecard: dashes, never zeros, and no difference.
    const failed = { id: B, scores: null, markdown: "", status: { state: "failed", topic: "Broken" } };
    const model = compare.comparison(run(A, "completed", SCORES_A), failed);
    assert.equal(model.sides[1].finished, false);
    assert.equal(model.sides[1].brief, null);
    assert.equal(model.rows[0].values[1], null);
    assert.equal(model.rows[0].delta, null);
    assert.equal(model.rows.length, 5, "A's dimensions still show");
    // A run that failed after scoring left a scores file: not its result, not compared.
    const leftover = { id: B, scores: SCORES_B, markdown: REPORT, status: { state: "failed", topic: "Broken late" } };
    const late = compare.comparison(run(A, "completed", SCORES_A), leftover);
    assert.equal(late.sides[1].brief, null);
    assert.deepEqual(late.rows.map((r) => r.values[1]), [null, null, null, null, null]);
    assert.deepEqual(late.rows.map((r) => r.delta), [null, null, null, null, null]);
    // A scorecard with impossible numbers is unreadable, not a score.
    const odd = run(B, "completed", { overall_score: 140, trl_score: 0, mrl_score: "4", patent_strength: 9 });
    const strange = compare.comparison(run(A, "completed", SCORES_A), odd);
    assert.deepEqual(strange.rows.map((r) => r.values[1]), [null, null, null, null, null]);
  },
  nothing_to_compare() {
    const bare = { id: B, scores: null, markdown: "", status: null };
    const model = compare.comparison(bare, { ...bare, id: A });
    assert.equal(model.rows.length, 1, "only the overall row stays when nothing was scored");
    assert.equal(model.sides[0].topic, B, "with no status, the id names the run");
    assert.equal(model.sides[0].state, "unknown");
    const same = compare.comparison(run(A, "completed", SCORES_A), run(A, "completed", SCORES_A));
    assert.equal(same.same, true);
  },
  drawn() {
    const container = new Element("div");
    const opened = [];
    compare.render(container, compare.comparison(run(A, "completed", SCORES_A), run(B, "completed", SCORES_B)),
      { onOpen: (id) => opened.push(id) });
    const cells = container.all((n) => n.tag === "td").map((n) => n.textContent);
    assert.deepEqual(cells.slice(0, 6), ["48.6", "61.2", "+12.6", "5 / 9", "6 / 9", "+1"]);
    const deltas = container.all((n) => n.className.includes("compare__delta"));
    assert.deepEqual(deltas.map((n) => n.dataset.sign), ["up", "up", "same", "up", "up"]);
    const link = container.find((n) => n.tag === "a");
    assert.equal(link.href, `/run/${A}`);
    link.listeners.click({ preventDefault() {} });
    assert.deepEqual(opened, [A], "the topic opens its run in the page, not a new document");
    const briefRows = container.all((n) => n.className === "compare__brief-row");
    assert.equal(briefRows.length, 6);
    assert.equal(briefRows[0].children[1].textContent, "The technology is at pilot stage.");
    assert.equal(briefRows[5].children[1].textContent, "9 · 3 academic · 2 patent · 4 market");
    // No markup from data: every value is a text node on its own element.
    assert.equal(container.all((n) => typeof n.textContent !== "string").length, 0);

    const again = new Element("div");
    compare.render(again, compare.comparison(run(A, "completed", SCORES_A), run(A, "completed", SCORES_A)));
    assert.equal(again.children.length, 1);
    assert.equal(again.children[0].textContent, "These are the same run. Choose another to compare with.");
  },
};
assert.ok(scenarios[process.argv[2]], "Unknown contract scenario");
await scenarios[process.argv[2]]();
console.log(`PASS ${process.argv[2]}`);
