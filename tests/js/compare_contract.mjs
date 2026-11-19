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
  setAttribute(name, value) { (this.attributes ??= {})[name] = value; }
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
    // Each run's card stands over its column of the table and says which it is.
    const heads = container.find((n) => n.className === "compare__heads");
    assert.deepEqual(heads.children.map((n) => n.className),
      ["compare__corner", "compare__run", "compare__run", "compare__corner"],
      "four cells, as the table has four columns: the label's, A's, B's and the difference's");
    assert.deepEqual(heads.children.slice(1, 3).map((card) => [card.dataset.side, card.children[0].className, card.children[0].textContent]),
      [["a", "compare__letter", "A"], ["b", "compare__letter", "B"]]);
    const columns = container.find((n) => n.tag === "colgroup").children.map((col) => col.className);
    assert.deepEqual(columns, ["compare__col--label", "compare__col--run", "compare__col--run", "compare__col--delta"]);
    assert.deepEqual(container.all((n) => n.tag === "thead")[0].children[0].children.map((th) => th.textContent),
      ["Score", "A", "B", "B − A"]);
    // "Topic aa" and "Topic bb" are two topics, which is said before anything else (see `topics`).
    assert.deepEqual(container.children.slice(0, 2).map((n) => n.className), ["compare__notice", "compare__heads"]);
    const link = container.find((n) => n.tag === "a");
    assert.equal(link.href, `/run/${A}`);
    link.listeners.click({ preventDefault() {} });
    assert.deepEqual(opened, [A], "the topic opens its run in the page, not a new document");
    const briefRows = container.all((n) => n.className === "compare__brief-row");
    assert.equal(briefRows.length, 6, "runs from before the decision gate get no decision rows");
    assert.equal(briefRows[0].children[1].textContent, "The technology is at pilot stage.");
    assert.equal(briefRows[5].children[1].textContent, "9 · 3 academic · 2 patent · 4 market");
    // No markup from data: every value is a text node on its own element.
    assert.equal(container.all((n) => typeof n.textContent !== "string").length, 0);

    const again = new Element("div");
    compare.render(again, compare.comparison(run(A, "completed", SCORES_A), run(A, "completed", SCORES_A)));
    assert.equal(again.children.length, 1);
    assert.equal(again.children[0].textContent, "These are the same run. Choose another to compare with.");
  },
  topics() {
    // Two runs on different topics can be laid side by side, and until
    // 2026-11-18 nothing said that their scores are not two readings of one thing.
    const on = (id, topic, scores = SCORES_A) => ({ ...run(id, "completed", scores), status: { state: "completed", topic } });
    const notice = (left, right) => {
      const container = new Element("div");
      const model = compare.comparison(left, right);
      compare.render(container, model);
      const found = container.find((n) => n.className === "compare__notice");
      return { same: model.sameTopic, first: container.children[0].className, text: found?.textContent ?? null,
        role: found?.attributes?.role ?? null };
    };
    assert.deepEqual(notice(on(A, "hyperloop"), on(B, "space-based solar power")), { same: false, first: "compare__notice",
      text: "These two assessments are on different topics; the score differences are for reference only.", role: "note" },
      "said first, above the cards and the table");
    assert.deepEqual(notice(on(A, "hyperloop"), on(B, "hyperloop")), { same: true, first: "compare__heads", text: null, role: null });
    // The same topic typed a little differently is the same topic.
    for (const [left, right] of [["Hyperloop", "hyperloop."], ["  solid-state   batteries ", "Solid-State Batteries"],
      ["特高压直流输电", "特高压直流输电。"], ["ＣＧＭ for diabetes", "cgm for diabetes"]]) {
      assert.equal(compare.sameTopic(left, right), true, `${left} / ${right}`);
    }
    for (const [left, right] of [["hyperloop", "hyperloop for freight"], ["CRISPR", "CRISPR-Cas9"], ["特高压直流输电", "特高压交流输电"]]) {
      assert.equal(compare.sameTopic(left, right), false, `${left} / ${right}`);
    }
    // A run whose topic is not on record is not said to differ from anything.
    const unnamed = { id: B, scores: SCORES_B, markdown: REPORT, status: { state: "completed" } };
    assert.deepEqual(notice(on(A, "hyperloop"), unnamed), { same: null, first: "compare__heads", text: null, role: null });
    assert.deepEqual(notice(unnamed, { ...unnamed, id: A }).same, null);
    for (const empty of ["", "   ", "。", null, undefined, 7]) assert.equal(compare.sameTopic(empty, "hyperloop"), null, String(empty));
  },
  picker_order() {
    // Which run to compare with: the ones on this run's topic are what the
    // comparison is for, and they stood wherever their dates put them.
    const listed = [
      { run_id: "20261116T110000Z-f", state: "completed", topic: "pig kidney xenotransplantation" },
      { run_id: "20261114T160000Z-e", state: "completed", topic: "Continuous glucose monitoring for diabetes." },
      { run_id: "20261112T081000Z-d", state: "failed", topic: "continuous glucose monitoring for diabetes" },
      { run_id: "20261110T140500Z-c", state: "completed", topic: "space-based solar power" },
      { run_id: "20261108T101500Z-a", state: "completed", topic: "continuous glucose monitoring for diabetes" },
      { run_id: "20261107T101500Z-0", state: "completed" },
    ];
    const order = (runId, topic) => compare.pickerOrder(listed, runId, topic).map((entry) => [entry.run.run_id.slice(-1), entry.same]);
    assert.deepEqual(order("20261108T101500Z-a"), [["e", true], ["f", false], ["c", false], ["0", false]],
      "the same topic first, then the rest in the order the list gave them; only finished runs, never the run itself");
    assert.deepEqual(order("20261116T110000Z-f"), [["e", false], ["c", false], ["a", false], ["0", false]],
      "no other run on this topic: the list as it was");
    // The run being compared is not in the list (another account's, or past the list's end): its topic is handed in.
    assert.deepEqual(order("20261201T000000Z-z", "continuous glucose monitoring for diabetes"),
      [["e", true], ["a", true], ["f", false], ["c", false], ["0", false]]);
    assert.deepEqual(order("20261201T000000Z-z"), [["f", false], ["e", false], ["c", false], ["a", false], ["0", false]],
      "a run whose topic is not known has no same-topic group");
    assert.deepEqual(compare.pickerOrder(null, "x"), []);
    assert.deepEqual(compare.pickerOrder([null, 7, { state: "completed" }], "x").length, 0, "an entry without an id cannot be opened");
  },
  decision_rows() {
    // What each run was asked and what its report answered, ahead of the rest.
    const row = (model, name) => {
      const container = new Element("div");
      compare.render(container, model);
      const rows = container.all((n) => n.className === "compare__brief-row");
      const found = rows.find((n) => n.dataset.row === name);
      return found && { at: rows.indexOf(found), label: found.children[0].textContent,
        cells: found.children.slice(1).map((n) => [n.text, n.dataset.tone ?? null]) };
    };
    const asked = { decision_gate: { mode: "decision_support", go_no_go_allowed: true } };
    const orientation = { decision_gate: { mode: "orientation", go_no_go_allowed: false } };
    const stated = { run_id: A, asked: true,
      question: { decision_owner: "Technology transfer office", decision_type: "License the technology" },
      conclusion: { status: "stated", verdict: "defer", statement: "The conclusion is DEFER because module data are missing [A2].",
        section: "Executive Summary", follows: [], needle: "The conclusion is DEFER", statements: [] } };
    const left = { ...run(A, "completed", SCORES_A, REPORT, asked), decision: stated };
    const model = compare.comparison(left, run(B, "completed", SCORES_B, REPORT, orientation));
    assert.deepEqual(row(model, "compare_context"), { at: 0, label: "Decision context", cells: [
      ["Decision owner: Technology transfer office · Decision to make: License the technology", null],
      ["None given: an orientation brief", null]] });
    assert.deepEqual(row(model, "compare_verdict"), { at: 1, label: "Decision conclusion", cells: [
      ["DEFER: “The conclusion is DEFER because module data are missing [A2].”", "warning"],
      // Not a dash: the other run's DEFER is not a difference in the evidence.
      ["Not asked for: this run gives no GO / NO-GO", "muted"]] });

    const cell = (decision, extra = asked, state = "completed") =>
      row(compare.comparison({ ...run(A, state, SCORES_A, REPORT, extra), decision }, run(B, "completed", SCORES_B)), "compare_verdict").cells;
    const none = { ...stated, conclusion: { status: "not_stated", verdict: null, statement: null, section: null,
      follows: [], needle: null, statements: [] } };
    assert.deepEqual(cell(none), [["The report states no clear conclusion", "muted"], ["—", null]],
      "said, not left as a dash; the run from before the gate has nothing to say");
    // The read failed, or was never made: said as that, never as "no conclusion".
    assert.deepEqual(cell(undefined)[0], ["The report's conclusion could not be read", "muted"]);
    assert.deepEqual(cell(null)[0], ["The report's conclusion could not be read", "muted"]);
    // A reply for a run the server says was not asked contradicts its own status: nothing is claimed.
    assert.deepEqual(cell({ run_id: A, asked: false, question: null, conclusion: null })[0],
      ["The report's conclusion could not be read", "muted"]);
    // A decision-support run that failed has an unreviewed report: no conclusion is shown from it.
    assert.deepEqual(cell(stated, asked, "failed")[0], ["None: this run did not finish", "muted"]);
    const incomplete = { decision_gate: { mode: "decision_context_incomplete", go_no_go_allowed: false } };
    const partial = compare.comparison(run(A, "completed", SCORES_A, REPORT, incomplete), run(B, "completed", SCORES_B, REPORT, orientation));
    assert.deepEqual(row(partial, "compare_context").cells.map((c) => c[0]),
      ["Incomplete: not all four required fields were given", "None given: an orientation brief"]);
  },
  next_step_expand() {
    const long = "License the architecture to an established module manufacturer under a field-limited agreement, "
      + "because the patent family covers the recombination junction and the passivation stack while the remaining "
      + "encapsulation and scale-up questions may be the licensee's to answer in its own pilot line over two years.";
    const report = `## Commercialization Opportunities\n\n1. ${long} More.\n`;
    const container = new Element("div");
    compare.render(container, compare.comparison(run(A, "completed", SCORES_A, report), run(B, "completed", SCORES_B)));
    const next = container.all((n) => n.className === "compare__brief-row").find((n) => n.dataset.row === "compare_next");
    const [cut, whole] = next.children.slice(1);
    const [text, button] = cut.children;
    assert.ok(text.textContent.endsWith("…") && text.textContent.length <= 240);
    assert.equal(button.textContent, "Show the whole sentence");
    button.onclick();
    assert.equal(text.textContent, long, "one press shows the sentence as the report has it");
    assert.equal(button.hidden, true);
    assert.equal(whole.textContent, "Run a field trial.");
    assert.equal(whole.children.length, 0, "a step that fits has no button");
  },
  async loads_the_decision_only_when_asked() {
    // The reads the comparison makes, through the shipped api.js and a scripted fetch.
    const asked = { decision_gate: { mode: "decision_support", go_no_go_allowed: true } };
    const seen = [];
    const scripted = (answers) => { globalThis.fetch = async (url) => {
      const path = String(url);
      seen.push(path);
      const [status, body] = answers(path);
      const json = typeof body !== "string";
      return { ok: status < 400, status, headers: { get: () => (json ? "application/json" : "text/markdown") },
        json: async () => body, text: async () => (json ? JSON.stringify(body) : body) };
    }; };
    const answers = (status, decision) => (path) => (path.endsWith("/decision") ? decision
      : path.endsWith("/scores") ? [200, SCORES_A] : path.includes("/report") ? [200, REPORT]
      : [200, { run_id: A, state: "completed", topic: "T", ...status }]);
    const reply = { run_id: A, asked: true, question: null, conclusion: { status: "not_stated" } };

    scripted(answers(asked, [200, reply]));
    const loaded = await compare.load(A);
    assert.deepEqual(loaded.decision, reply);
    assert.equal(seen.filter((path) => path.endsWith(`/api/runs/${A}/decision`)).length, 1);

    seen.length = 0;
    scripted(answers({ decision_gate: { mode: "orientation", go_no_go_allowed: false } }, [200, reply]));
    assert.equal((await compare.load(A)).decision, null);
    assert.equal(seen.some((path) => path.endsWith("/decision")), false, "a run that was not asked is not asked about");

    scripted(answers(asked, [500, { detail: "boom" }]));
    const failed = await compare.load(A);
    assert.equal(failed.decision, undefined, "a failed read is kept apart from no conclusion");
    assert.equal(compare.comparison(failed, run(B, "completed", SCORES_B)).sides[0].decision.verdict.text,
      "The report's conclusion could not be read");
  },
};
assert.ok(scenarios[process.argv[2]], "Unknown contract scenario");
await scenarios[process.argv[2]]();
console.log(`PASS ${process.argv[2]}`);
