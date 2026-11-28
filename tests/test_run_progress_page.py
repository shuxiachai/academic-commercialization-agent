"""What the run page says while a run is going, after it stopped, and after a resume.

Three production runs of 2026-11-18 are behind every test here:

- a run whose page said "about 7 min" at its start and took 24 min 40 s;
- a run that failed in scoring after 25 min 31 s and 141,193 tokens, whose
  page said it "produced no report" and to "contact the operator with the
  run ID" while showing neither the ID nor a contact;
- its resume, done in 3 min 48 s, whose stage list sat on the evidence stage
  throughout, whose header ended in "6 checkpoint stages reused", and which
  showed its own time and tokens only.

The figures are the server's (tests/test_run_wait.py, test_resume_progress.py,
test_run_draft.py). What is held here is the page's wording of them: the
shipped run.js, result.js and i18n.js run in Node.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from academic_agent import checkpoint_runtime

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "web" / "static" / "js"
RUN_JS = (JS / "run.js").read_text(encoding="utf-8")
RESULT_JS = (JS / "result.js").read_text(encoding="utf-8")
APP_JS = (JS / "app.js").read_text(encoding="utf-8")
STRINGS = (JS / "i18n.js").read_text(encoding="utf-8")
INDEX = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

EN, ZH = "English", "Simplified Chinese"

_HARNESS = """
    globalThis.localStorage = { getItem: () => null, setItem: () => {} };
    globalThis.document = { querySelectorAll: () => [], documentElement: {} };
    const run = await import("./run.mjs");
    const result = await import("./result.mjs");
    const i18n = await import("./i18n.js");
    const out = JSON.parse(process.argv[2]).map(([language, call, args]) => {
      i18n.setLanguage(language);
      if (call === "reusedStages") return [...run.reusedStages(...args)];
      if (call === "stages") return run.stageStates(...args).map((row) => [row.id, row.state, row.seconds, row.nodes]);
      if (call === "drawStages") {
        // The list as drawn: each row's state and the text beside its label.
        class Node { constructor() { this.children = []; this.dataset = {}; this.className = ""; this.textContent = ""; }
          set innerHTML(_v) { this.children = []; } append(...nodes) { this.children.push(...nodes); } }
        document.createElement = () => new Node();
        const box = new Node();
        run.renderStages(box, run.stageStates(...args));
        return box.children[0].children.map((row) => [row.dataset.state, row.children.at(-1).className,
                                                      row.children.at(-1).textContent]);
      }
      if (call === "hasDraft" || call === "ranWithoutReport" || call === "draftWording") return result[call](...args);
      if (call === "label") return i18n.t(...args);
      return run[call](...args);
    });
    console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    node = shutil.which("node")
    assert node, "Node must execute the page's own modules; skipping loses the seam"
    work = tmp_path_factory.mktemp("run-progress-page")
    for name, source in (("run.mjs", RUN_JS), ("result.mjs", RESULT_JS)):
        (work / name).write_text(source.replace('import * as api from "./api.js";', "const api = {};"), encoding="utf-8")
    shutil.copy2(JS / "i18n.js", work / "i18n.js")
    (work / "harness.mjs").write_text(textwrap.dedent(_HARNESS), encoding="utf-8")

    def ask(*calls):
        done = subprocess.run([node, "harness.mjs", json.dumps(list(calls))], capture_output=True, text=True,
                              encoding="utf-8", cwd=work, check=False)
        assert done.returncode == 0, done.stderr[-1500:]
        return json.loads(done.stdout)

    return ask


# ── The time left ───────────────────────────────────────────────────────────


def eta(low, high, *, runs=6, overdue=False, few=()):
    return {"remaining_seconds": (low + high) // 2, "low_seconds": low, "high_seconds": high, "basis_runs": runs,
            "basis": "stages", "overdue": overdue, "few_sample_stages": list(few)}


#: What #512's server said beside the range, for a page loaded before this change reached it.
BY_MODEL = {"model": None, "same_model": False, "other_model_stages": ["sources", "evidence", "report", "review", "scoring"]}


def test_the_time_left_is_a_range_from_recent_runs(page):
    english, chinese = page([EN, "etaSummary", [eta(700, 1480)]], [ZH, "etaSummary", [eta(700, 1480)]])
    # 11:40 to 24:40: rounded outward, so the range said is never narrower than the one measured.
    assert english == "about 11–25 min left"
    assert chinese == "预计还需约 11–25 分钟"


def test_one_run_or_two_alike_is_said_as_one_figure(page):
    assert page([EN, "etaSummary", [eta(300, 300)]], [ZH, "etaSummary", [eta(300, 300)]]) == [
        "about 5 min left", "预计还需约 5 分钟"]
    assert page([EN, "etaSummary", [eta(10, 45)]], [ZH, "etaSummary", [eta(10, 45)]]) == [
        "under a minute left", "预计不到 1 分钟"]
    # Never "0 min": under a minute at the low end is said as one.
    assert page([EN, "etaSummary", [eta(20, 200)]])[0] == "about 1–4 min left"


def test_a_range_widened_for_few_runs_says_so_and_no_line_speaks_of_models(page):
    """The deployment's model is changed often (free allowances run out), and the user asked on
    2026-11-28 that the estimate not depend on it: every run is told the same range from the
    recent runs of whatever model. The line says why only when the range was widened for steps
    few runs have finished, and never "on other models", even beside a reply that says so."""
    few = eta(340, 1070, few=["review", "scoring"])
    few_zh, few_en, plain_zh, old_zh, old_en = page(
        [ZH, "etaSummary", [few, REPORT]], [EN, "etaSummary", [few, REPORT]],
        [ZH, "etaSummary", [eta(340, 1070), REPORT]],
        [ZH, "etaSummary", [{**eta(340, 1070), **BY_MODEL}, SOURCES, "brand-new-model"]],
        [EN, "etaSummary", [{**eta(340, 1070), **BY_MODEL}, SOURCES, "brand-new-model"]])
    assert few_zh == "预计还需约 5–18 分钟（本站完成过这些步骤的运行还少，区间已放宽）"
    assert few_en == "about 5–18 min left (few runs here have finished these steps yet, so the range is widened)"
    assert plain_zh == old_zh == "预计还需约 5–18 分钟"
    assert old_en == "about 5–18 min left"


def test_a_run_slower_than_every_recent_one_is_told_so_not_counted_down(page):
    later = eta(60, 240, overdue=True)
    last = eta(0, 0, overdue=True)
    english, chinese, final, total = page(
        [EN, "etaSummary", [later, REVIEW]], [ZH, "etaSummary", [later, REVIEW]],
        [ZH, "etaSummary", [last, SCORING]], [ZH, "etaSummary", [{**later, "basis": "total"}, REVIEW]])
    assert "cannot yet be estimated" in english and "(Scoring) took 1–4 min" in english
    assert "当前阶段剩余时间暂时无法估计" in chinese and "后续步骤（评分）合计用时 1–4 分钟" in chinese
    assert final == total == "当前阶段剩余时间暂时无法估计。"


def test_countdown_uses_this_runs_observed_budget_and_saved_checkpoints(page):
    live = {"runtime_budget": {"state": "active", "hard_timeout_seconds": 900, "remaining_seconds": 130},
            "checkpointing": {"committed_nodes": ["writer"]}, "artifacts": ["sources"]}
    near, at_limit, unknown, cap_only = page(
        [ZH, "deadlineView", [live, 5]], [ZH, "deadlineView", [live, 133]],
        [ZH, "deadlineView", [{}]], [ZH, "deadlineView", [{"runtime_budget": {
            "state": "active", "hard_timeout_seconds": 65}}]])
    assert "15:00" in near["line"] and "2:05" in near["line"]
    assert "报告草稿" in near["note"] and "来源" in near["note"]
    assert "等待服务器确认结果" in at_limit["line"]
    assert unknown == {"line": "暂未取得本次运行的时限。", "note": ""}
    assert "1:05" in cap_only["line"] and "暂未取得" in cap_only["line"]


def test_the_limit_line_warns_when_the_slowest_estimate_runs_past_it(page):
    """2026-11-27: writing and review alone took 20 to 25 minutes of a 30-minute limit, and the
    page never said so. When the high end of the estimate needs more time than is left before
    the limit, the limit's own line says it, from the first reading. The range is no longer any
    one model's, so neither is the warning, even beside a reply from before that change."""
    budget = {"state": "active", "hard_timeout_seconds": 1800, "remaining_seconds": 1788}
    near = {"runtime_budget": budget, "eta": eta(1204, 2079)}
    old = {"runtime_budget": budget, "eta": {**eta(1204, 2079), "model": "m", "same_model": True,
                                             "other_model_stages": []}}
    inside = {"runtime_budget": budget, "eta": eta(600, 1700)}
    (near_zh, near_en, old_zh, inside_zh, none_zh, stale_zh) = page(
        [ZH, "deadlineView", [near, 0]], [EN, "deadlineView", [near, 0]], [ZH, "deadlineView", [old, 0]],
        [ZH, "deadlineView", [inside, 0]], [ZH, "deadlineView", [{"runtime_budget": budget}, 0]],
        [ZH, "deadlineView", [near, None]])
    assert near_zh["line"] == "本次运行时限 30:00 · 最多还可运行 29:48（分:秒） · 按以往的运行估计，可能接近 30 分钟时限"
    assert near_en["line"].endswith("· Going by past runs, this run may come close to the 30-minute limit")
    assert old_zh["line"] == near_zh["line"]
    assert "接近" not in inside_zh["line"]
    assert "接近" not in none_zh["line"]
    # Without a current reading of the time left there is nothing to compare with.
    assert "接近" not in stale_zh["line"]
    # The comparison is made at the reading, so the warning does not come and go between polls.
    later = page([ZH, "deadlineView", [near, 600]])[0]
    assert later["line"].endswith("按以往的运行估计，可能接近 30 分钟时限")


def test_no_estimate_is_no_text(page):
    for nothing in (None, {}, {"remaining_seconds": 300}, {"low_seconds": 300}, {"low_seconds": 400, "high_seconds": 300},
                    {"low_seconds": -5, "high_seconds": 300}, {"low_seconds": "a", "high_seconds": 300}):
        assert page([EN, "etaSummary", [nothing]])[0] == "", nothing


def test_the_tooltip_says_how_the_range_is_drawn_whatever_the_model(page):
    zh, en, few, old = page(
        [ZH, "etaTitle", [eta(700, 1480)]], [EN, "etaTitle", [eta(700, 1480)]],
        [EN, "etaTitle", [eta(340, 1070, few=["scoring"])]],
        [ZH, "etaTitle", [{**eta(340, 1070, runs=10), **BY_MODEL}, "brand-new-model"]])
    assert zh.startswith("按本站最近的运行估计，不分模型")
    assert "包括后来失败或超时的运行" in zh and "共参考 6 次运行" in zh and "不是保证" in zh
    # Why a model change can still move the real time, said where the method is.
    assert "用的模型不同，实际用时可能相差很多" in zh
    assert en.startswith("Going by recent runs here, whatever model they ran on")
    assert "fewer than three times" in few and "widened" in few
    assert old.startswith("按本站最近的运行估计，不分模型") and "brand-new-model" not in old and "还没有完成过" not in old
    assert page([EN, "etaTitle", [None]])[0] == ""


def test_the_header_asks_for_the_estimate_without_the_runs_model():
    assert "runView.etaTitle(eta)" in APP_JS
    assert "runView.etaSummary(eta, progress.stage)" in APP_JS
    assert re.search(r"function paintHeader\(progress\)\s*\{\s*const \{[^}]*\bllm_model, lineage, run_id, continued_by,", APP_JS)


# ── The draft while the review runs ─────────────────────────────────────────


def test_a_run_in_review_offers_its_draft_under_a_label_that_says_what_it_is(page):
    """2026-11-27: nine minutes of review with the writer's report saved, shown only after the
    run failed. The label and the notice above the text say it is a draft and not the result."""
    writer = {"state": "running", "artifacts": ["sources", "draft"], "draft_stage": "writer"}
    reviewer = {**writer, "draft_stage": "reviewer"}
    wording, reviewed, stopped, none = page(
        [ZH, "liveDraftWording", [writer]], [ZH, "liveDraftWording", [reviewer]],
        [ZH, "liveDraftWording", [{**writer, "state": "failed"}]],
        [ZH, "liveDraftWording", [{"state": "running", "artifacts": ["sources"]}]])
    assert wording == {"label": "live_draft", "note": "live_draft_note"}
    assert reviewed == {"label": "live_draft_reviewed", "note": "live_draft_reviewed_note"}
    # A stopped run keeps its Draft tab (result.js hasDraft); nothing to offer without a draft.
    assert stopped is None and none is None
    label_zh, note_zh, label_en, note_en, reviewed_zh = page(
        [ZH, "label", ["live_draft"]], [ZH, "label", ["live_draft_note"]],
        [EN, "label", ["live_draft"]], [EN, "label", ["live_draft_note"]], [ZH, "label", ["live_draft_reviewed"]])
    assert label_zh == "先读草稿（审查中、未评分）"
    assert "不是这次评估的结论" in note_zh and "审查还在进行" in note_zh
    assert label_en == "Read the draft now (in review, not scored)"
    assert "not the assessment's conclusion" in note_en
    assert reviewed_zh == "先读草稿（已核查、未评分）"


def test_the_page_draws_the_draft_beside_the_stages_and_drops_it_when_the_run_ends():
    update = APP_JS[APP_JS.index("    onUpdate(progress) {"):APP_JS.index("    onDone(progress) {")]
    assert "paintLiveDraft(body, runId, progress);" in update
    done = APP_JS[APP_JS.index("    onDone(progress) {"):APP_JS.index("    onError(err) {")]
    assert "dropLiveDraft();" in done
    start = APP_JS.index("function paintLiveDraft(")
    assert "runView.liveDraftWording(progress)" in APP_JS[start:APP_JS.index("\n}\n", start)]
    # The text itself is read only when the fold is opened (the browser smoke opens it).
    start = APP_JS.index("function liveDraftFold(")
    fold = APP_JS[start:APP_JS.index("\n}\n", start)]
    assert 'api.getArtifact(runId, "draft")' in fold and "result.renderMarkdown(" in fold
    assert fold.index('addEventListener("toggle"') < fold.index('api.getArtifact(runId, "draft")')


# ── A resumed run's stage list ──────────────────────────────────────────────

SOURCES, EVIDENCE, REPORT, REVIEW, SCORING = (
    "Source Collection & Validation", "Phase 1 — Evidence Collection (Academic · Patent · Market)",
    "Agent 4 — Report Writing", "Agent 5 — Quality Review & Citation Check", "Agent 6 — Commercialization Scoring")
ALL_BUT_SCORING = {"state": "reused", "source_run_id": "p", "next_node": "scorer",
                   "reused_nodes": ["retrieval", "academic", "patent", "market", "writer", "reviewer"]}


def test_the_stages_and_the_checkpoints_behind_them_are_the_pipelines_own(page):
    rows = page([EN, "stages", [SOURCES, "running"]])[0]
    nodes = [node for row in rows for node in row[3]]
    assert nodes == ["retrieval", *checkpoint_runtime.TASK_NODES], "A node added to the pipeline needs a stage here"


def test_a_resume_with_only_scoring_left_shows_four_stages_reused_and_scoring_running(page):
    timings = [{"stage": SOURCES, "duration_seconds": 3, "active": False},
               {"stage": SCORING, "duration_seconds": 40, "active": True}]
    rows = page([EN, "stages", [SCORING, "running", timings, ALL_BUT_SCORING]])[0]
    assert [row[:3] for row in rows] == [
        ["sources", "reused", None], ["evidence", "reused", None], ["report", "reused", None],
        ["review", "reused", None], ["scoring", "active", 40]]


def test_a_finished_resume_keeps_saying_which_stages_were_not_its_own(page):
    timings = [{"stage": SOURCES, "duration_seconds": 3, "active": False},
               {"stage": SCORING, "duration_seconds": 225, "active": False}]
    rows = page([EN, "stages", ["Done", "completed", timings, ALL_BUT_SCORING]])[0]
    assert [row[1:3] for row in rows] == [["reused", None]] * 4 + [["done", 225]]


def test_a_stage_reused_only_in_part_ran_here(page):
    part = {"state": "reused", "source_run_id": "p", "reused_nodes": ["retrieval", "academic", "patent"]}
    assert page([EN, "reusedStages", [part]])[0] == ["sources"]
    rows = page([EN, "stages", [REPORT, "running", [], part]])[0]
    assert [row[1] for row in rows] == ["reused", "done", "active", "pending", "pending"]


def test_the_stage_a_resume_stopped_in_is_its_own_failure(page):
    rows = page([EN, "stages", [SCORING, "failed", [], ALL_BUT_SCORING]])[0]
    assert [row[1] for row in rows] == ["reused"] * 4 + ["failed"]


@pytest.mark.parametrize("recovery", [
    None, {}, {"state": "not_requested", "reused_nodes": []}, {"state": "cold_start", "source_run_id": "p", "reused_nodes": []},
    # Not a reuse, whatever the list says; and a list that is not one.
    {"state": "cold_start", "reused_nodes": ["retrieval"]}, {"state": "reused", "reused_nodes": "retrieval"},
])
def test_a_run_that_reused_nothing_reads_as_it_always_did(page, recovery):
    timings = [{"stage": SOURCES, "duration_seconds": 40, "active": False},
               {"stage": EVIDENCE, "duration_seconds": 75, "active": True}]
    rows = page([EN, "stages", [EVIDENCE, "running", timings, recovery]])[0]
    assert [row[:3] for row in rows] == [
        ["sources", "done", 40], ["evidence", "active", 75], ["report", "pending", None],
        ["review", "pending", None], ["scoring", "pending", None]]
    assert page([EN, "reusedStages", [recovery]])[0] == []


def test_a_reused_row_is_drawn_with_its_words_in_place_of_a_time(page):
    timings = [{"stage": SOURCES, "duration_seconds": 3, "active": False},
               {"stage": SCORING, "duration_seconds": 40, "active": True}]
    english, chinese = page([EN, "drawStages", [SCORING, "running", timings, ALL_BUT_SCORING]],
                            [ZH, "drawStages", [SCORING, "running", timings, ALL_BUT_SCORING]])
    assert english[0] == ["reused", "stage__meta stage__meta--reused", "reused from the earlier run"]
    assert english[4] == ["active", "stage__meta", "0:40"]
    assert chinese[3] == ["reused", "stage__meta stage__meta--reused", "沿用上次结果"]


# What a worker before 2026-11-19 recorded for a resume that only scored: the
# scorer's 3 min 33 s under the evidence phase (production, 2026-11-18).
OLD_RESUME = [{"stage": SOURCES, "duration_seconds": 0, "active": False},
              {"stage": EVIDENCE, "duration_seconds": 213, "active": False},
              {"stage": SCORING, "duration_seconds": 0, "active": False}]


def test_an_old_resumes_time_is_shown_under_the_step_it_ran(page):
    english, chinese, as_recorded = page(
        [EN, "timingSummary", [OLD_RESUME, ALL_BUT_SCORING]], [ZH, "timingSummary", [OLD_RESUME, ALL_BUT_SCORING]],
        [EN, "timingSummary", [OLD_RESUME]])
    assert english == "Sources 0:00 · Scoring 3:33"
    assert chinese == "来源 0:00 · 评分 3:33"
    # Without the run's own word for what it reused, the record is shown as it stands.
    assert as_recorded == "Sources 0:00 · Evidence 3:33 · Scoring 0:00"
    rows = page([EN, "stages", ["Done", "completed", OLD_RESUME, ALL_BUT_SCORING]])[0]
    assert [row[1:3] for row in rows] == [["reused", None]] * 4 + [["done", 213]]


def test_an_old_resume_from_the_writer_on_shows_the_writers_time_under_the_report(page):
    recovery = {"state": "reused", "source_run_id": "p", "next_node": "writer",
                "reused_nodes": ["retrieval", "academic", "patent", "market"]}
    timings = [{"stage": SOURCES, "duration_seconds": 2}, {"stage": EVIDENCE, "duration_seconds": 300},
               {"stage": REVIEW, "duration_seconds": 100}, {"stage": SCORING, "duration_seconds": 40}]
    assert page([EN, "timingSummary", [timings, recovery]])[0] == "Sources 0:02 · Report 5:00 · Review 1:40 · Scoring 0:40"


@pytest.mark.parametrize(("recovery", "why"), [
    # The evidence stage ran here in part: its label was right.
    ({"state": "reused", "source_run_id": "p", "next_node": "market", "reused_nodes": ["retrieval", "academic", "patent"]},
     "a stage reused only in part ran here"),
    # The record does not say where the run began, so nothing says where the seconds belong.
    ({"state": "reused", "source_run_id": "p", "next_node": None,
      "reused_nodes": ["retrieval", "academic", "patent", "market", "writer", "reviewer"]}, "no first step on record"),
    ({"state": "reused", "source_run_id": "p",
      "reused_nodes": ["retrieval", "academic", "patent", "market", "writer", "reviewer"]}, "no first step on record"),
    # A record at odds with itself: the step it names is one it says it reused.
    ({"state": "reused", "source_run_id": "p", "next_node": "writer",
      "reused_nodes": ["retrieval", "academic", "patent", "market", "writer", "reviewer"]}, "the first step is itself reused"),
    ({"state": "cold_start", "source_run_id": "p", "next_node": "academic", "reused_nodes": []}, "nothing was reused"),
    (None, "not a resume"),
])
def test_seconds_stay_where_they_were_recorded_when_nothing_says_otherwise(page, recovery, why):
    assert page([EN, "timingSummary", [OLD_RESUME, recovery]])[0] == "Sources 0:00 · Evidence 3:33 · Scoring 0:00", why


def test_a_resume_recorded_since_the_fix_reads_as_it_was_recorded(page):
    timings = [{"stage": SOURCES, "duration_seconds": 4}, {"stage": SCORING, "duration_seconds": 224}]
    assert page([EN, "timingSummary", [timings, ALL_BUT_SCORING]])[0] == "Sources 0:04 · Scoring 3:44"
    # The run's own start-up, under the first stage, is never moved.
    began = [{"stage": SOURCES, "duration_seconds": 9}, {"stage": SCORING, "duration_seconds": 30}]
    assert page([EN, "timingSummary", [began, ALL_BUT_SCORING]])[0] == "Sources 0:09 · Scoring 0:30"
    # Seconds shown under the step it ran are added to what that step already has, not put in its place.
    both = [{"stage": SOURCES, "duration_seconds": 0}, {"stage": EVIDENCE, "duration_seconds": 213},
            {"stage": SCORING, "duration_seconds": 12}]
    assert page([EN, "timingSummary", [both, ALL_BUT_SCORING]])[0] == "Sources 0:00 · Scoring 3:45"


def test_the_timing_fold_is_given_the_runs_recovery_record():
    # Its owner's fold; a reader of someone else's run is not shown stage times
    # (tests/test_shared_link_pages.py, a_reader_of_a_shared_run_is_shown_a_header_written_for_them).
    assert 'timingEl.textContent = reader ? "" : runView.timingSummary(stage_timings, recovery);' in APP_JS


# ── The run a resume continued ─────────────────────────────────────────────


def test_a_run_that_was_resumed_later_says_so_with_the_way_there(page):
    assert page([EN, "headerLabel", ["continued_note"]], [EN, "headerLabel", ["continued_open"]],
                [ZH, "headerLabel", ["continued_note"]], [ZH, "headerLabel", ["continued_open"]]) == [
        "This run was resumed later.", "Open the run that continued it", "这次运行后来已被续跑。", "打开接着它做的那次运行"]
    assert 'id="run-continued" hidden' in INDEX
    assert INDEX.index('id="run-lineage"') < INDEX.index('id="run-continued"') < INDEX.index('id="run-outcome"')
    start = APP_JS.index("function paintContinued(runId) {")
    body = APP_JS[start:APP_JS.index("\n}\n", start)]
    assert 'const known = typeof runId === "string" && runId !== "";' in body
    assert "line.hidden = !known;" in body
    assert "open.onclick = known ? () => openRun(runId) : null;" in body
    assert "paintContinued(continued_by);" in APP_JS
    assert "llm_model, lineage, run_id, continued_by," in APP_JS


def test_the_page_hands_the_stage_list_the_runs_recovery_record():
    # And, since 2026-11-27, what the API expects a resume to reuse before its
    # worker has said (tests/test_scoring_time_limit.py).
    assert APP_JS.count(
        "progress.stage, progress.state, progress.stage_timings, progress.recovery, progress.resume_expected));") == 2


# ── A resumed run's line under its header ───────────────────────────────────

PARENT = "20261118T090017Z-" + "7" * 32


def resumed(**changes):
    facts = {
        "state": "completed", "elapsed_seconds": 228, "recovery": ALL_BUT_SCORING,
        "usage": {"total_tokens": 35_012}, "usage_accounting": {"state": "complete"},
        "lineage": {
            "earlier": [{"run_id": PARENT, "record": "available", "state": "failed", "elapsed_seconds": 1531,
                         "total_tokens": 141_193, "usage_state": "lower_bound", "cost_usd": None,
                         "cost_complete": False}],
            "combined": {"runs": 2, "elapsed_seconds": 1759, "elapsed_complete": True, "total_tokens": 176_205,
                         "usage_state": "lower_bound", "cost_usd": None, "cost_complete": False},
        },
    }
    facts.update(changes)
    return facts


def test_a_finished_resume_says_what_it_reused_and_what_both_runs_took(page):
    english, chinese = page([EN, "lineageSummary", [resumed()]], [ZH, "lineageSummary", [resumed()]])
    assert english == {
        "reuse": "This run continues {earlier}. Reused from it: Sources, Evidence, Report, Review. Run here: Scoring.",
        "earlier": PARENT,
        "totals": "In all: 29:19 (3:48 here + 25:31 before) · at least 176.2k tokens (35.0k here + at least 141.2k before).",
        "missing": "",
    }
    assert chinese["reuse"] == "这是一次续跑，接着{earlier}做。沿用上次结果：来源、证据分析、报告撰写、审查。本次重做：评分。"
    assert chinese["totals"] == "合计用时 29:19（本次 3:48 + 之前 25:31）；合计至少 17.6 万 token（本次 3.5 万 + 之前至少 14.1 万）。"
    # In the reader's words: the pipeline's own are gone from the line.
    for text in (*english.values(), *chinese.values()):
        assert "checkpoint" not in str(text) and "检查点" not in str(text)


def test_a_total_that_is_complete_is_said_plainly_and_only_then(page):
    facts = resumed()
    facts["lineage"]["earlier"][0].update(usage_state="complete", cost_usd=0.21, cost_complete=True)
    facts["lineage"]["combined"].update(usage_state="complete", cost_usd=0.26, cost_complete=True)
    assert page([EN, "lineageSummary", [facts]])[0]["totals"] == (
        "In all: 29:19 (3:48 here + 25:31 before) · 176.2k tokens (35.0k here + 141.2k before) · estimated cost $0.26.")
    # One priced run of two: the sum of prices is a floor even where the counts are whole.
    facts["lineage"]["combined"]["cost_complete"] = False
    assert page([EN, "lineageSummary", [facts]])[0]["totals"].endswith("estimated cost at least $0.26.")
    # This run's own count a floor: said of its part and of the sum.
    facts["usage_accounting"] = {"state": "lower_bound"}
    facts["lineage"]["combined"]["usage_state"] = "lower_bound"
    assert "at least 176.2k tokens (at least 35.0k here + 141.2k before)" in page([EN, "lineageSummary", [facts]])[0]["totals"]


def test_while_the_resume_runs_only_what_came_before_is_summed(page):
    running = resumed(state="running", elapsed_seconds=40, usage=None, usage_accounting=None)
    english, chinese = page([EN, "lineageSummary", [running]], [ZH, "lineageSummary", [running]])
    assert english["totals"] == "Before this run: 25:31 · at least 141.2k tokens."
    assert chinese["totals"] == "在这次之前：25:31，至少 14.1 万 token。"


def test_usage_that_is_not_on_record_is_said_to_be_missing_never_zero(page):
    facts = resumed()
    facts["lineage"]["earlier"][0].update(total_tokens=None, usage_state="unavailable")
    facts["lineage"]["combined"].update(total_tokens=35_012, usage_state="lower_bound")
    totals = page([EN, "lineageSummary", [facts]])[0]["totals"]
    assert totals == "In all: 29:19 (3:48 here + 25:31 before) · token use before this run is not on record."
    assert " 0 " not in totals and "0k" not in totals


def test_an_earlier_run_whose_record_is_gone_is_said_and_not_linked(page):
    facts = resumed()
    facts["lineage"] = {"earlier": [{"run_id": PARENT, "record": "missing"}],
                        "combined": {"runs": 2, "elapsed_seconds": 228, "elapsed_complete": False, "total_tokens": 35_012,
                                     "usage_state": "lower_bound", "cost_usd": None, "cost_complete": False}}
    english, chinese = page([EN, "lineageSummary", [facts]], [ZH, "lineageSummary", [facts]])
    assert english["earlier"] is None and english["totals"] == ""
    assert english["missing"] == "The earlier run's record has been deleted, so these figures cover this run only."
    assert chinese["missing"] == "上一次运行的记录已被删除，所以这些数字只包含本次运行。"
    assert english["reuse"].startswith("This run continues {earlier}.")


def test_a_resume_that_could_reuse_nothing_says_every_step_ran_again(page):
    cold = resumed(recovery={"state": "cold_start", "source_run_id": PARENT, "reused_nodes": []})
    english, chinese = page([EN, "lineageSummary", [cold]], [ZH, "lineageSummary", [cold]])
    assert english["reuse"] == ("This run was started to continue {earlier}, but nothing that run had saved could be "
                                "reused, so every step ran again.")
    assert chinese["reuse"] == "这次运行本来要接着{earlier}做，但那次保存的结果都用不上，所以每一步都重做了。"
    assert english["totals"].startswith("In all: 29:19")


def test_a_run_that_was_not_a_resume_has_no_line(page):
    for facts in ({}, {"state": "completed", "recovery": {"state": "not_requested", "source_run_id": None}},
                  {"state": "completed", "recovery": None, "lineage": None}):
        assert page([EN, "lineageSummary", [facts]])[0] is None, facts


def test_three_runs_in_a_chain_are_summed_before_this_one(page):
    facts = resumed()
    facts["lineage"]["earlier"].append({"run_id": "20261118T080000Z-" + "6" * 32, "record": "available", "state": "failed",
                                        "elapsed_seconds": 300, "total_tokens": 1_000, "usage_state": "lower_bound"})
    facts["lineage"]["combined"].update(runs=3, elapsed_seconds=2059, total_tokens=177_205)
    assert page([EN, "lineageSummary", [facts]])[0]["totals"] == (
        "In all: 34:19 (3:48 here + 30:31 before) · at least 177.2k tokens (35.0k here + at least 142.2k before).")


def test_an_earlier_run_with_no_time_on_record_makes_the_time_a_floor(page):
    facts = resumed()
    facts["lineage"]["earlier"].append({"run_id": "20261118T080000Z-" + "6" * 32, "record": "available",
                                        "state": "failed", "elapsed_seconds": None, "total_tokens": 1_000,
                                        "usage_state": "lower_bound"})
    facts["lineage"]["combined"].update(runs=3, elapsed_complete=False, total_tokens=177_205)
    totals = page([EN, "lineageSummary", [facts]])[0]["totals"]
    assert totals.startswith("In all: at least 29:19 (3:48 here + at least 25:31 before)")


def test_a_keys_only_visitors_list_names_the_run_a_resume_continues():
    """That list is built in the page from each run's own read, which carries the lineage."""
    start = APP_JS.index("const runs = await Promise.all(entries.map(async ({ run_id, topic }) => {")
    body = APP_JS[start:APP_JS.index("if (!isCurrent()) return null;", start)]
    assert "resumed_from: status.lineage?.earlier?.[0]?.run_id ?? null," in body


def test_the_line_sits_under_the_header_and_links_the_earlier_run():
    lineage, outcome = INDEX.index('id="run-lineage"'), INDEX.index('id="run-outcome"')
    assert INDEX.index('id="run-recovery"') < lineage < outcome, "Directly under the header's line, before the outcome"
    assert 'id="run-lineage" hidden' in INDEX
    # Said to the run's owner; a reader has the total in the header line instead.
    assert "paintLineage(reader ? {} : { state, recovery, lineage, elapsed_seconds, usage, usage_accounting });" in APP_JS
    assert 'link.addEventListener("click", () => openRun(view.earlier));' in APP_JS
    # The count of checkpoints is gone from the page and from both languages.
    assert "recovery_reused_short" not in APP_JS and "recovery_reused_short" not in STRINGS
    assert "checkpoint stages reused" not in STRINGS and "个检查点阶段" not in STRINGS


# ── A failure the reader cannot fix alone ───────────────────────────────────


@pytest.mark.parametrize(("facts", "expected"), [
    ({"state": "failed", "error_code": "unknown", "funded_by": "own_keys"}, True),
    ({"state": "failed", "error_code": "unknown", "funded_by": "deployment"}, True),
    ({"state": "failed", "error_code": None}, True),
    ({"state": "failed", "error_code": "a_code_from_a_later_server"}, True),
    # The deployment's key or model: only its operator can act.
    ({"state": "failed", "error_code": "provider_auth", "funded_by": "deployment"}, True),
    ({"state": "failed", "error_code": "provider_billing", "funded_by": None}, True),
    ({"state": "failed", "error_code": "provider_output_limit", "funded_by": "deployment"}, True),
    # The reader's own key or model: theirs to fix, in the key form.
    ({"state": "failed", "error_code": "provider_auth", "funded_by": "own_keys"}, False),
    ({"state": "failed", "error_code": "provider_output_limit", "funded_by": "own_keys"}, False),
    # A cause with a next step for everyone.
    ({"state": "failed", "error_code": "provider_unreachable", "funded_by": "deployment"}, False),
    ({"state": "failed", "error_code": "quality_checks", "funded_by": "own_keys"}, False),
    ({"state": "timeout", "error_code": "timeout_resumable", "funded_by": "deployment"}, False),
    ({"state": "timeout", "error_code": "unknown", "funded_by": "own_keys"}, True),
    ({"state": "timeout", "error_code": None}, True),
    # Not a failure at all, whatever cause the record carries.
    ({"state": "cancelled", "error_code": "cancelled"}, False),
    ({"state": "cancelled", "error_code": "unknown"}, False),
    ({"state": "cancelled", "error_code": "a_code_from_a_later_server"}, False),
    ({"state": "completed", "error_code": None}, False),
    ({"state": "running", "error_code": None}, False),
    ({}, False),
])
def test_which_failures_show_the_run_id_and_the_operator(page, facts, expected):
    assert page([EN, "needsOperator", [facts]])[0] is expected


def test_the_help_line_shows_the_id_a_copy_button_and_the_published_contact():
    for element in ('id="run-help" hidden', 'id="run-help-id"', 'id="run-help-copy"', 'id="run-help-contact"'):
        assert element in INDEX, element
    assert INDEX.index('id="run-outcome"') < INDEX.index('id="run-help"'), "Under the sentence that says to use it"
    start = APP_JS.index("function paintRunHelp(")
    body = APP_JS[start:APP_JS.index("\n}\n", start)]
    assert "runView.needsOperator({ state, error_code, funded_by })" in body
    assert "await copyText(runId)" in body
    # The contact is the deployment's own published line, from the two reads the page already makes.
    assert "authConfig.contact" in body and "deploymentContact" in body
    assert "help_no_contact" in body, "No contact published is said, not left blank"
    # Nothing is written into the page: no address, no name.
    assert not re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", body)
    assert "paintRunHelp({ state, error_code, funded_by, run_id });" in APP_JS


def test_the_health_reading_is_where_the_page_learns_the_contact():
    start = APP_JS.index("function noteHealthFacts(")
    body = APP_JS[start:APP_JS.index("\n}\n", start)]
    assert "const { llm_model, contact, run_minutes } = reading ?? {};" in body
    assert "deploymentContact = typeof contact === \"string\" && contact.trim() ? contact.trim() : null;" in body


# ── The writer's draft ──────────────────────────────────────────────────────


@pytest.mark.parametrize(("progress", "draft", "without"), [
    ({"state": "failed", "artifacts": ["sources", "draft"]}, True, True),
    ({"state": "cancelled", "artifacts": ["draft"]}, True, True),
    ({"state": "timeout", "artifacts": ["draft", "sources"]}, True, True),
    ({"state": "failed", "artifacts": ["sources"]}, False, True),
    # A report is the later, fuller text; a run still going or done shows no draft.
    ({"state": "failed", "artifacts": ["report", "draft"]}, False, False),
    ({"state": "completed", "artifacts": ["report", "draft"]}, False, False),
    ({"state": "running", "artifacts": ["draft"]}, False, False),
    ({"state": "failed"}, False, True),
])
def test_when_a_stopped_run_shows_a_draft(page, progress, draft, without):
    assert page([EN, "hasDraft", [progress]], [EN, "ranWithoutReport", [progress]]) == [draft, without]


def test_the_draft_is_named_for_what_it_is_in_both_languages(page):
    tab_en, tab_zh, note_en, note_zh, none_en, none_zh, with_en, with_zh = page(
        [EN, "label", ["tab_draft"]], [ZH, "label", ["tab_draft"]], [EN, "label", ["draft_note"]],
        [ZH, "label", ["draft_note"]], [EN, "label", ["rel_no_report"]], [ZH, "label", ["rel_no_report"]],
        [EN, "label", ["rel_no_report_draft"]], [ZH, "label", ["rel_no_report_draft"]])
    assert tab_en == "Draft (not reviewed or scored)" and tab_zh == "草稿（未经审稿和打分）"
    assert note_en.startswith("This is an unreviewed, unscored draft.") and "Do not treat it as the assessment." in note_en
    assert note_zh.startswith("这是一份未经审稿和打分的草稿。")
    # Said to a reader: what the text is, and nothing about resuming, which they cannot do.
    assert "Resum" not in note_en and "续跑" not in note_zh
    owner_en, owner_zh = page([EN, "label", ["draft_note_owner"]], [ZH, "label", ["draft_note_owner"]])
    assert owner_en == note_en + " Resuming the run finishes the remaining steps and reuses this text."
    assert owner_zh == note_zh + "续跑会完成剩下的步骤，并沿用这份文字。"
    # "No report" is said only where there is no draft either.
    assert "produced no report" in none_en and "没有生成报告" in none_zh
    assert "produced no report" not in with_en and "没有生成报告" not in with_zh
    assert "draft" in with_en and "草稿" in with_zh


@pytest.mark.parametrize(("progress", "wording"), [
    # The writer's text, to its owner and to a reader of the link.
    ({"draft_stage": "writer"}, ("tab_draft", "draft_note_owner", "rel_no_report_draft")),
    ({"draft_stage": "writer", "viewer_can_modify": False}, ("tab_draft", "draft_note", "rel_no_report_draft")),
    # Production, 2026-11-20: the run failed in scoring with its review done.
    ({"draft_stage": "reviewer"},
     ("tab_draft_reviewed", "draft_reviewed_note_owner", "rel_no_report_draft_reviewed")),
    ({"draft_stage": "reviewer", "viewer_can_modify": False},
     ("tab_draft_reviewed", "draft_reviewed_note", "rel_no_report_draft_reviewed")),
    # A server that does not say which text it is: the writer's wording, as before.
    ({}, ("tab_draft", "draft_note_owner", "rel_no_report_draft")),
    ({"draft_stage": "something new"}, ("tab_draft", "draft_note_owner", "rel_no_report_draft")),
])
def test_the_draft_is_named_for_the_step_whose_text_it_is(page, progress, wording):
    said = page([EN, "draftWording", [{"state": "failed", "artifacts": ["draft"], **progress}]])[0]
    assert (said["tab"], said["note"], said["reliability"]) == wording


def test_a_reviewed_draft_says_it_was_reviewed_and_not_scored_in_both_languages(page):
    tab_en, tab_zh, note_en, note_zh, owner_en, owner_zh, rel_en, rel_zh = page(
        [EN, "label", ["tab_draft_reviewed"]], [ZH, "label", ["tab_draft_reviewed"]],
        [EN, "label", ["draft_reviewed_note"]], [ZH, "label", ["draft_reviewed_note"]],
        [EN, "label", ["draft_reviewed_note_owner"]], [ZH, "label", ["draft_reviewed_note_owner"]],
        [EN, "label", ["rel_no_report_draft_reviewed"]], [ZH, "label", ["rel_no_report_draft_reviewed"]])
    assert tab_en == "Draft (reviewed, not scored)" and tab_zh == "草稿（已核查、未评分）"
    assert note_en.startswith("This is a reviewed draft with no score.")
    assert "after the review that checks its citations and claims" in note_en
    assert "Do not treat it as the assessment." in note_en
    assert note_zh.startswith("这是一份已核查、未评分的草稿。") and "请不要把它当作评估结论。" in note_zh
    # Nothing in it says the text came before the review, as the writer's notice does.
    assert "unreviewed" not in note_en and "before the review" not in note_en and "未经审稿" not in note_zh
    assert "Resum" not in note_en and "续跑" not in note_zh
    assert owner_en == note_en + " Resuming the run finishes the remaining steps and reuses this text."
    assert owner_zh == note_zh + "续跑会完成剩下的步骤，并沿用这份文字。"
    assert "produced no report" not in rel_en and "draft" in rel_en and "review" in rel_en
    assert "没有生成报告" not in rel_zh and "草稿" in rel_zh and "审查" in rel_zh


def test_the_draft_tab_is_drawn_from_the_draft_artifact_under_its_notice():
    assert "if (draft) views.push({ id: \"draft\", label: t(draftWording(progress).tab) });" in RESULT_JS
    assert 'api.getArtifact(runId, "draft")' in RESULT_JS
    start = RESULT_JS.index('} else if (id === "draft") {')
    body = RESULT_JS[start:RESULT_JS.index('} else if (id === "checks") {', start)]
    assert body.index('el("p", "draft-note"') < body.index("renderMarkdown(md)"), "The notice is read before the text"
    # The notice is the one for this text and this reader (draftWording).
    assert 'el("p", "draft-note", t(draftWording(progress).note))' in body
    # A run with a draft and no report must not ask for the report it does not have.
    assert "(draft ? draftOnce() : reportOnce()).then(citationIndex)" in RESULT_JS
    assert 't(hasDraft(progress) ? draftWording(progress).reliability : "rel_no_report")' in RESULT_JS


# ── How long a run takes, said on the landing and the sign-in card ──────────


def test_no_page_states_a_run_time_written_by_hand():
    """ "6 to 15 minutes" was written once, from a handful of runs on one model."""
    for text in (INDEX, STRINGS):
        assert not re.search(r"\d+ to \d+ minutes", text.replace("{low} to {high} minutes", ""))
        assert not re.search(r"\d+ 到 \d+ 分钟", text)
    assert INDEX.count("data-run-time hidden") == 3, "The landing's third step and both sign-in cards"
    assert STRINGS.count("    run_time: ") == 2 and STRINGS.count("    run_time_one: ") == 2


def test_the_sentence_is_this_deployments_own_recent_runs_or_nothing(page):
    assert page([EN, "label", ["run_time"]], [ZH, "label", ["run_time"]]) == [
        "Here, the last {runs} completed assessments took {low} to {high} minutes each.",
        "本站最近 {runs} 次完成的评估，每次用了 {low} 到 {high} 分钟。"]
    start = APP_JS.index("function paintRunTimes(")
    body = APP_JS[start:APP_JS.index("\n}\n", start)]
    assert 'const text = !runMinutes ? ""' in body and "node.hidden = !text;" in body
    assert '$$("[data-run-time]")' in body


# ── Both languages ──────────────────────────────────────────────────────────


def test_every_new_string_is_in_both_languages():
    header = RUN_JS[RUN_JS.index("const HEADER_STRINGS = {"):RUN_JS.index("// English keeps the API's own state words")]
    english, chinese = header.split('"Simplified Chinese": {')
    for key in ("eta_left", "eta_why_few", "eta_with_why",
                "eta_range", "eta_range_one", "eta_soon", "eta_over", "eta_over_later", "eta_title",
                "eta_title_few", "deadline_near", "stage_reused", "lineage_reused", "lineage_reused_all",
                "lineage_cold", "lineage_earlier", "lineage_sep", "lineage_total", "lineage_total_running",
                "lineage_usage", "lineage_usage_before", "lineage_usage_none", "lineage_cost", "lineage_at_least",
                "lineage_missing", "continued_note", "continued_open", "help_run_id", "help_copy", "help_copied", "help_copy_failed", "help_contact",
                "help_no_contact"):
        assert english.count(f"    {key}: ") == 1 and chinese.count(f"    {key}: ") == 1, key
    # The wording of a range drawn by model went with it (2026-11-28).
    for key in ("eta_why_others", "eta_why_some", "eta_why_any", "eta_title_others", "eta_title_any",
                "deadline_near_model"):
        assert f"    {key}: " not in header, key
    for key in ("tab_draft", "draft_note", "draft_note_owner", "rel_no_report_draft", "live_draft", "live_draft_note",
                "live_draft_reviewed", "live_draft_reviewed_note", "live_draft_loading", "live_draft_failed",
                "runs_earlier_one", "runs_earlier_many",
                "run_earlier_row", "run_time", "run_time_one"):
        assert STRINGS.count(f"    {key}: ") == 2, key
