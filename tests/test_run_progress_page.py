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
      if (call === "hasDraft" || call === "ranWithoutReport") return result[call](...args);
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


def eta(low, high, *, runs=6, model="qwen3.8-max", same_model=True, overdue=False):
    return {"remaining_seconds": (low + high) // 2, "low_seconds": low, "high_seconds": high, "basis_runs": runs,
            "basis": "stages", "model": model if same_model else None, "same_model": same_model, "overdue": overdue}


def test_the_time_left_is_a_range_from_this_models_runs(page):
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


def test_a_range_from_other_models_runs_is_said_to_be_one(page):
    other = eta(340, 1070, same_model=False)
    assert page([EN, "etaSummary", [other]], [ZH, "etaSummary", [other]]) == [
        "about 5–18 min left, going by runs on other models", "预计还需约 5–18 分钟（按其他模型的运行）"]


def test_a_run_slower_than_every_recent_one_is_told_so_not_counted_down(page):
    later = eta(240, 280, overdue=True)
    last = eta(0, 0, overdue=True)
    assert page([EN, "etaSummary", [later]], [ZH, "etaSummary", [later]], [EN, "etaSummary", [last]],
                [ZH, "etaSummary", [last]]) == [
        "slower at this step than the last 6 runs; the steps after it took 4–5 min",
        "这一步比最近 6 次运行都慢；之后的步骤它们用了 4–5 分钟",
        "slower than the last 6 runs", "比最近 6 次运行都慢"]


def test_no_estimate_is_no_text(page):
    for nothing in (None, {}, {"remaining_seconds": 300}, {"low_seconds": 300}, {"low_seconds": 400, "high_seconds": 300},
                    {"low_seconds": -5, "high_seconds": 300}, {"low_seconds": "a", "high_seconds": 300}):
        assert page([EN, "etaSummary", [nothing]])[0] == "", nothing


def test_the_tooltip_says_whose_runs_and_how_many(page):
    same, others, unnamed = page(
        [EN, "etaTitle", [eta(700, 1480), "qwen3.8-max"]],
        [EN, "etaTitle", [eta(340, 1070, same_model=False, runs=10), "brand-new-model"]],
        [EN, "etaTitle", [eta(340, 1070, same_model=False, runs=10), None]])
    assert same == ("What the last 6 completed runs on qwen3.8-max here took from this step to the end, "
                    "fastest to slowest. Not a guarantee.")
    assert others.startswith("brand-new-model has fewer than three completed runs here, so this is what the last 10 "
                             "completed runs on other models took")
    assert unnamed.startswith("What the last 10 completed runs here took")
    assert page([ZH, "etaTitle", [eta(700, 1480), "qwen3.8-max"]])[0].startswith("本站最近 6 次用 qwen3.8-max 完成的运行")
    assert page([EN, "etaTitle", [None, "m"]])[0] == ""
    # A model's name is text: a "$&" in it is not a replacement pattern.
    assert "a$&b" in page([EN, "etaTitle", [eta(1, 2, model="a$&b"), "a$&b"]])[0]


def test_the_header_gives_the_estimate_the_runs_own_model():
    assert "runView.etaTitle(eta, llm_model)" in APP_JS
    assert re.search(r"paintHeader\(\{[^}]*\bllm_model, lineage, run_id, continued_by,", APP_JS, re.S)


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
    assert "timingEl.textContent = runView.timingSummary(stage_timings, recovery);" in APP_JS


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
    assert re.search(r"paintHeader\(\{[^}]*\bllm_model, lineage, run_id, continued_by,", APP_JS, re.S)


def test_the_page_hands_the_stage_list_the_runs_recovery_record():
    assert APP_JS.count("progress.stage, progress.state, progress.stage_timings, progress.recovery));") == 2


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
    assert "paintLineage({ state, recovery, lineage, elapsed_seconds, usage, usage_accounting });" in APP_JS
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


def test_the_draft_tab_is_drawn_from_the_draft_artifact_under_its_notice():
    assert "if (draft) views.push({ id: \"draft\", label: t(\"tab_draft\") });" in RESULT_JS
    assert 'api.getArtifact(runId, "draft")' in RESULT_JS
    start = RESULT_JS.index('} else if (id === "draft") {')
    body = RESULT_JS[start:RESULT_JS.index('} else if (id === "checks") {', start)]
    assert body.index('el("p", "draft-note"') < body.index("renderMarkdown(md)"), "The notice is read before the text"
    # A reader of someone else's run cannot resume it, and is not told to.
    assert 't(progress.viewer_can_modify === false ? "draft_note" : "draft_note_owner")' in body
    # A run with a draft and no report must not ask for the report it does not have.
    assert "(draft ? draftOnce() : reportOnce()).then(citationIndex)" in RESULT_JS
    assert 't(hasDraft(progress) ? "rel_no_report_draft" : "rel_no_report")' in RESULT_JS


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
    for key in ("eta_left", "eta_left_others", "eta_range", "eta_range_one", "eta_soon", "eta_over", "eta_over_later",
                "eta_title", "eta_title_others", "eta_title_any", "stage_reused", "lineage_reused", "lineage_reused_all",
                "lineage_cold", "lineage_earlier", "lineage_sep", "lineage_total", "lineage_total_running",
                "lineage_usage", "lineage_usage_before", "lineage_usage_none", "lineage_cost", "lineage_at_least",
                "lineage_missing", "continued_note", "continued_open", "help_run_id", "help_copy", "help_copied", "help_copy_failed", "help_contact",
                "help_no_contact"):
        assert english.count(f"    {key}: ") == 1 and chinese.count(f"    {key}: ") == 1, key
    for key in ("tab_draft", "draft_note", "draft_note_owner", "rel_no_report_draft", "runs_earlier_one", "runs_earlier_many",
                "run_earlier_row", "run_time", "run_time_one"):
        assert STRINGS.count(f"    {key}: ") == 2, key
