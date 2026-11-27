"""What the run page offers when a run did not finish, cause by cause.

A run on the live site (2026-11-15) used an OCR model. It failed two minutes
in, at the evidence step, after nine requests and 44,338 tokens whose answers
were 250 to 300 tokens each. The page said "did not pass the evidence-quality
checks. Retry the analysis.", and its one prominent button was "Resume from
checkpoint": the same step, on the same model, for another of the day's runs.

The cause's code and how a failure is classified are the API's and are not
touched here (api/runs.py). What is held here is display: one table,
``FAILURE_NEXT`` in web/static/js/run.js, that says for each code which
action is the main one, and the functions that read it. The page's own run.js
and i18n.js run in Node.
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
from api import runs

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "web" / "static" / "js"
RUN_JS = (JS / "run.js").read_text(encoding="utf-8")

_HARNESS = """
    globalThis.localStorage = { getItem: () => null, setItem: () => {} };
    globalThis.document = { querySelectorAll: () => [], documentElement: {} };
    const run = await import("./run.mjs");
    const i18n = await import("./i18n.js");
    const out = JSON.parse(process.argv[2]).map(([language, call, args]) => {
      i18n.setLanguage(language);
      if (call === "table") return run.FAILURE_NEXT;
      if (call === "constants") return { short: run.SHORT_EVIDENCE_ANSWER, roles: run.EVIDENCE_ROLES, steps: run.RESUME_STEPS };
      const value = run[call](...args);
      return value instanceof Set ? [...value] : value;
    });
    console.log(JSON.stringify(out));
"""

EN, ZH = "English", "Simplified Chinese"
OCR = "qwen-vl-ocr-2025-11-20"
ROLES = ("Academic Literature Analyst for x\n", "Patent Landscape Analyst for x\n",
         "Market and Competitive Intelligence Analyst for x\n", "Commercialization Readiness Scorer for x",
         "Technology Commercialization Report Writer", "Scientific Report Quality Reviewer")


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    node = shutil.which("node")
    assert node, "Node must execute the page's own module; skipping loses the seam"
    work = tmp_path_factory.mktemp("failure-next")
    (work / "run.mjs").write_text(RUN_JS.replace('import * as api from "./api.js";', "const api = {};"), encoding="utf-8")
    shutil.copy2(JS / "i18n.js", work / "i18n.js")
    (work / "harness.mjs").write_text(textwrap.dedent(_HARNESS), encoding="utf-8")

    def ask(*calls):
        done = subprocess.run([node, "harness.mjs", json.dumps(list(calls))], capture_output=True, text=True,
                              encoding="utf-8", cwd=work, check=False)
        assert done.returncode == 0, done.stderr[-1500:]
        return json.loads(done.stdout)

    return ask


def usage(per_answer=(280, 270, 290), requests=3, model=OCR, later=0):
    """A run's usage as the status carries it: three evidence analysts, then the three that follow."""
    answers = [*per_answer, later, later, later]
    return {"agents": [{"role": role, "model": model, "requests": requests if index < 3 or later else 0,
                        "completion_tokens": answer * (requests if index < 3 or later else 0)}
                       for index, (role, answer) in enumerate(zip(ROLES, answers, strict=True))]}


def guide(page, language=EN, **facts):
    facts = {"state": "failed", "funded_by": "own_keys", "resumable": True, "canModify": True, **facts}
    return page([language, "failureGuide", [facts]])[0]


# ── The table ──────────────────────────────────────────────────────────────

#: For each cause: the main action for a reader whose own keys paid, and for anyone else.
EXPECTED = {
    "quality_checks": ("resume", "resume"),
    "provider_response_format": ("resume", "resume"),
    "provider_empty_answer": ("resume", "resume"),
    "provider_auth": ("keys", None),
    "provider_billing": ("keys", None),
    "provider_free_quota": ("keys", None),
    "provider_model_unavailable": ("keys", None),
    "provider_request_rejected": ("keys", None),
    "provider_output_limit": ("keys", None),
    "provider_rate_limited": ("resume", "resume"),
    "provider_unreachable": ("resume", "resume"),
    "topic_not_translated": ("keys", "again"),
    "insufficient_evidence": ("again", "again"),
    "timeout": ("again", "again"),
    "timeout_resumable": ("resume", "resume"),
    "cancelled": ("resume", "resume"),
    "unknown": ("resume", "resume"),
}


def test_the_table_has_a_row_for_every_cause_the_api_can_name(page):
    table = page([EN, "table", []])[0]
    api = {runs._UNKNOWN_FAILURE[0], "cancelled", "timeout_resumable",
           *(category.code for category in runs._PUBLIC_FAILURE_CATEGORIES)}
    assert set(table) == api == set(EXPECTED)
    assert {code: tuple(row) for code, row in table.items()} == EXPECTED
    # One table, in one place: the page's other modules do not decide this again.
    assert RUN_JS.count("export const FAILURE_NEXT = {") == 1
    for name in ("app.js", "result.js"):
        assert "FAILURE_NEXT" not in (JS / name).read_text(encoding="utf-8"), name


@pytest.mark.parametrize("code", sorted(EXPECTED))
def test_each_cause_has_its_main_action_for_each_reader(page, code):
    own, other = EXPECTED[code]
    state = "cancelled" if code == "cancelled" else "timeout" if code.startswith("timeout") else "failed"
    mine = guide(page, state=state, error_code=code)
    assert mine["primary"] == own, code
    assert mine["keys"] == ({"provider_auth": "keys", "provider_billing": "keys"}.get(code, "model") if own == "keys" else None)
    # The deployment's keys: its model and its key are not the reader's to change.
    theirs = guide(page, state=state, error_code=code, funded_by="deployment")
    assert theirs["primary"] == other and theirs["keys"] is None
    # A run nobody's markers describe is read as the cautious one.
    assert guide(page, state=state, error_code=code, funded_by=None)["primary"] == other
    # Nothing to resume from: the same topic as a new run stands in for it.
    cold = guide(page, state=state, error_code=code, resumable=False)
    assert cold["primary"] == ("again" if own == "resume" else own)
    # Someone else's run: nothing here is theirs to do.
    assert guide(page, state=state, error_code=code, canModify=False) == {"primary": None, "keys": None, "suspect": None, "advice": ""}


def test_a_cause_the_table_does_not_know_is_treated_as_unknown(page):
    assert guide(page, error_code="a_code_from_the_future")["primary"] == "resume"
    assert guide(page, error_code=None)["primary"] == "resume"
    for state in ("running", "completed", "unknown", None):
        assert page([EN, "failureGuide", [{"state": state, "error_code": "quality_checks"}]])[0] is None, state


def test_a_cancelled_run_is_read_by_its_state_whatever_cause_it_carries(page):
    # The reader stopped it. A cause left on its record (a refusal met just before, a time limit) is
    # not why it ended, and must not send them to the key form or to a new run.
    for code in ("provider_auth", "timeout", "insufficient_evidence", "quality_checks", None):
        stopped = guide(page, state="cancelled", error_code=code, usage=usage())
        assert (stopped["primary"], stopped["keys"], stopped["suspect"]) == ("resume", None, None), code


def test_the_rule_about_a_models_name_is_written_once():
    kinds = (JS / "model_kind.js").read_text(encoding="utf-8")
    assert kinds.count("export const MODEL_KINDS = [") == 1 and "import " not in kinds
    pair = re.compile(r'\[\s*"[a-z]+",\s*/')          # ["ocr", /.../]: a kind beside its pattern
    assert len(pair.findall(kinds)) >= 8
    for path in sorted(JS.glob("*.js")):
        if path.name != "model_kind.js":
            assert not pair.search(path.read_text(encoding="utf-8")), f"{path.name} holds a copy of the rule"
    fields = (JS / "byok_fields.js").read_text(encoding="utf-8")
    assert 'import { MODEL_KINDS, modelKind } from "./model_kind.js";' in fields
    assert fields.count("MODEL_KINDS") == 2 + fields.count("MODEL_KINDS.")   # the import and the re-export, and its uses


# ── A model that cannot do the step ────────────────────────────────────────

@pytest.mark.parametrize("code", ["quality_checks", "provider_response_format"])
def test_a_model_of_another_kind_makes_changing_it_the_main_action(page, code):
    """Resuming would run the same step on the same model: for another of the
    day's runs, and most likely to the same end."""
    said = guide(page, error_code=code, model=OCR, otherKind=True, usage=usage(per_answer=(900, 950, 1000)))
    assert (said["primary"], said["keys"], said["suspect"]) == ("keys", "model", "kind")
    assert said["advice"] == (f"The model this run used, {OCR}, does not look like a general chat model. Change to a model "
                              "this project has measured before trying again: resuming repeats the same step on the model "
                              "that is saved now.")
    chinese = guide(page, ZH, error_code=code, model=OCR, otherKind=True)["advice"]
    assert chinese == f"这次运行用的模型 {OCR} 看起来不是通用对话模型。请先换成本项目实测过的模型再试：续跑会在当前保存的模型上重做同一步。"
    # Not the reader's model: no advice to change what they cannot change.
    theirs = guide(page, error_code=code, model=OCR, otherKind=True, funded_by="deployment")
    assert (theirs["primary"], theirs["suspect"], theirs["advice"]) == ("resume", None, "")
    # Another cause is not explained by the model's name.
    assert guide(page, error_code="provider_unreachable", model=OCR, otherKind=True)["suspect"] is None


@pytest.mark.parametrize("code", ["quality_checks", "provider_response_format"])
def test_answers_far_shorter_than_any_saved_run_point_at_the_model_too(page, code):
    said = guide(page, error_code=code, model="some-model", usage=usage())
    assert (said["primary"], said["keys"], said["suspect"]) == ("keys", "model", "short")
    assert said["advice"] == ("Each answer some-model gave in the evidence step was under 500 tokens, where every run this "
                              "project has saved wrote more. Change to a model this project has measured before trying "
                              "again: resuming repeats the same step on the model that is saved now.")
    assert "不到 500 token" in guide(page, ZH, error_code=code, model="some-model", usage=usage())["advice"]
    # Answers of ordinary length: the model is not the suspect, and resuming stays the main action.
    ordinary = guide(page, error_code=code, model="some-model", usage=usage(per_answer=(900, 700, 1200)))
    assert (ordinary["primary"], ordinary["suspect"], ordinary["advice"]) == ("resume", None, "")
    # The name is the plainer reason where both hold.
    assert guide(page, error_code=code, model=OCR, otherKind=True, usage=usage())["suspect"] == "kind"


def test_short_answers_are_read_from_the_three_evidence_analysts_only(page):
    def short(value):
        return page([EN, "shortEvidenceAnswers", [value]])[0]

    assert short(usage()) is True
    assert short(usage(per_answer=(499, 499, 499))) is True
    # One analyst at the measure is enough to say "not short": the rule is about a model that cannot do the step.
    assert short(usage(per_answer=(499, 499, 500))) is False
    assert short(usage(per_answer=(900, 700, 1200))) is False
    # Nothing said where the record says nothing: no usage, no requests, an analyst missing, other roles only.
    for silent in (None, {}, {"agents": []}, {"agents": "damaged"}, usage(requests=0),
                   {"agents": usage()["agents"][:2]}, {"agents": usage()["agents"][3:]}):
        assert short(silent) is None, silent
    # A run that reached the later steps is judged on its evidence answers all the same.
    assert short(usage(later=4000)) is True


def test_the_measure_and_the_roles_are_the_ones_measured():
    """Over the 269 saved runs with all three analysts on record
    (outputs/, 2026-11-16), no analyst averaged under 643 completion tokens
    a request; the run that prompted this averaged 250 to 300."""
    assert re.search(r"^export const SHORT_EVIDENCE_ANSWER = 500;", RUN_JS, re.M)
    roles = re.search(r"^export const EVIDENCE_ROLES = \[(.*?)\];", RUN_JS, re.M | re.S)[1]
    named = re.findall(r'"([^"]+)"', roles)
    assert named == ["Academic Literature Analyst", "Patent Landscape Analyst", "Market and Competitive Intelligence Analyst"]
    # The names are the crew's own: a renamed agent must fail here, not go unread.
    agents = (ROOT / "src" / "academic_agent" / "config" / "agents.yaml").read_text(encoding="utf-8")
    for name in named:
        assert re.search(rf"^\s+{re.escape(name)} for \{{research_topic\}}$", agents, re.M), name
    assert "643" in RUN_JS and "269" in RUN_JS, "The comment says what was measured"


# ── Beside "Resume from checkpoint" ────────────────────────────────────────

def test_the_note_beside_resume_says_what_it_costs_where_it_starts_and_on_which_model(page):
    def note(language=EN, **facts):
        return page([language, "resumeNote", [{"committed": ["retrieval"], **facts}]])[0]

    assert note(quota=True, model="qwen3.8-max", ranOn="qwen3.8-max") == (
        "Resuming uses one more of today's runs. It starts again at the evidence analysis and reuses what was saved "
        "before it. It will run on qwen3.8-max.")
    # A model changed since: the new one, and that it is not the one this run used.
    assert note(quota=True, model="qwen3.8-max", ranOn=OCR).endswith(
        f"It will run on qwen3.8-max, not on {OCR}, which this run used.")
    # No daily allowance on this deployment: nothing is said about one.
    assert note(quota=False, model="qwen3.8-max", ranOn="qwen3.8-max").startswith("Resuming starts again at the evidence analysis")
    # The model is not known to the page: nothing is said about it rather than a guess.
    assert note(quota=True, model=None, ranOn=OCR) == (
        "Resuming uses one more of today's runs. It starts again at the evidence analysis and reuses what was saved before it.")
    # Further along.
    evidence = ["retrieval", "academic", "patent", "market"]
    assert "starts again at writing the report" in note(quota=True, committed=evidence)
    assert "starts again at the review and reuses" in note(quota=True, committed=[*evidence, "writer"])
    # Production, 2026-11-20: the run failed in scoring with the reviewer's
    # answer saved, and this line said "the review and scoring" while its
    # resume said "Run here: Scoring".
    assert "starts again at the scoring and reuses" in note(quota=True, committed=[*evidence, "writer", "reviewer"])
    assert note(ZH, quota=True, committed=[*evidence, "writer", "reviewer"]) == (
        "续跑会再用 1 次今日额度。它从评分重新开始，之前已保存的部分会沿用。")
    assert note(ZH, quota=True, committed=[*evidence, "writer"]).startswith("续跑会再用 1 次今日额度。它从核查重新开始")
    assert "starts again at the evidence analysis" in note(quota=True, committed=["retrieval", "academic"])
    # Nothing to resume from: no note.
    for nothing in ([], None, ["academic"], "retrieval"):
        assert note(quota=True, committed=nothing) == "", nothing
    chinese = note(ZH, quota=True, model="qwen3.8-max", ranOn=OCR)
    assert chinese == f"续跑会再用 1 次今日额度。它从证据分析重新开始，之前已保存的部分会沿用。它会在 qwen3.8-max 上运行，而不是这次运行所用的 {OCR}。"


def test_the_steps_a_resume_can_start_at_are_the_checkpoints_own(page):
    steps = page([EN, "constants", []])[0]["steps"]
    assert [name for group in steps for name in group["nodes"]] == list(checkpoint_runtime.TASK_NODES), \
        "A node added to the pipeline needs a place here"
    assert [group["label"] for group in steps] == [
        "resume_step_evidence", "resume_step_writing", "resume_step_review", "resume_step_scoring"]


def test_a_resume_is_said_to_start_where_the_resumed_run_says_it_started(page):
    """The note beside Resume and the resumed run's own "Run here" line are
    two readings of one fact. On 2026-11-20 they disagreed: the note grouped
    the reviewer with the scorer and said "the review and scoring" for a run
    whose reviewer was saved; the resume reused it and said "Run here:
    Scoring". So the steps are the run page's stages, one for one, and for
    every point a run can stop at, the step named is the first stage the
    resume does not take whole from it (reusedStages)."""
    rows = page([EN, "stageStates", ["", "failed"]])[0]
    stages = [(row["id"], row["nodes"]) for row in rows if row["id"] != "sources"]
    steps = page([EN, "constants", []])[0]["steps"]
    assert [(step["stage"], step["nodes"]) for step in steps] == stages
    order = [row["id"] for row in rows]
    for saved in range(len(checkpoint_runtime.TASK_NODES)):
        committed = ["retrieval", *checkpoint_runtime.TASK_NODES[:saved]]
        step, reused = page([EN, "resumeStep", [committed]],
                            [EN, "reusedStages", [{"state": "reused", "reused_nodes": committed}]])
        first_run_here = next(stage for stage in order if stage not in reused)
        assert step["stage"] == first_run_here, committed
    # Everything saved (a run that stopped after its scorer had answered): the last step.
    assert page([EN, "resumeStep", [["retrieval", *checkpoint_runtime.TASK_NODES]]])[0]["stage"] == "scoring"
    # The note is worded from that same step.
    assert "const next = resumeStep(committed);" in RUN_JS


def test_the_outcome_line_no_longer_carries_the_resume_sentence(page):
    """It is beside the button now, with the rest of what resuming means."""
    line = page([EN, "outcomeSummary", [{"state": "failed", "error": "The API's sentence.", "error_code": "quality_checks",
                                         "funded_by": "own_keys", "daily_charge": "charged",
                                         "checkpointing": {"committed_nodes": ["retrieval"]}}]])[0]
    assert line == "The API's sentence. This run counted toward today's quota."
    assert "outcome_charged_resume" not in RUN_JS


# ── The page ───────────────────────────────────────────────────────────────

def test_the_lines_under_a_stopped_run_are_in_the_page_and_start_hidden():
    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "web" / "static" / "css" / "workbench.css").read_text(encoding="utf-8")
    order = [index.index(f'id="{name}"') for name in ("run-outcome", "run-advice", "run-resume-note", "run-leave", "run-actions")]
    assert order == sorted(order), "Why it stopped, what its record suggests, what resuming means; then the buttons"
    for name in ("run-advice", "run-resume-note", "run-leave"):
        assert re.search(rf'<p class="run-outcome [a-z-]+" id="{name}" hidden>', index), name
    assert re.search(r'<button type="button" class="gate__switch" id="run-leave-notify" hidden></button>', index)
    # The advice is a caution. Its colour must be named with the pane, or the outcome line's own rule wins.
    assert re.search(r"^#pane-run \.run-advice \{ color: var\(--warning\); \}", css, re.M)
    assert not re.search(r"^\.run-advice \{", css, re.M)
    # On a phone the main action takes a row to itself, as "Resume" does.
    phone = css[css.index("#pane-run .pane__actions [data-resume-run] { grid-column: 1 / -1; }"):][:500]
    assert "#pane-run .pane__actions #run-fix," in phone and "#run-again.btn--primary { grid-column: 1 / -1; }" in phone
    app = (JS / "app.js").read_text(encoding="utf-8")
    # The rule about a model's name is the form's own, read from one module.
    assert 'import { modelKind } from "./model_kind.js";' in app
    assert "otherKind: Boolean(modelKind(ranOn))" in app
    assert app.count("runView.failureGuide(") == 1 and app.count("runView.resumeNote(") == 1


def test_the_operating_guide_says_what_the_page_offers_and_what_it_reads():
    guide = (ROOT / "docs" / "operating-guide.md").read_text(encoding="utf-8")
    for said in ("`FAILURE_NEXT` in `web/static/js/run.js`", "`quality_checks` and `provider_response_format`",
                 "`web/static/js/model_kind.js`", "averaged under 500 tokens", "the least was 643 over the\n269 on record",
                 "The cause's code and how a failure is classified are\nunchanged",
                 "This run produced no report, so there are no check results", '"worker failed", "hard timeout"',
                 "the model saved with it at that moment and not the one the run used"):
        assert said in guide, said
    # The figures in the prose are the module's.
    assert re.search(r"^export const SHORT_EVIDENCE_ANSWER = 500;", RUN_JS, re.M)


# ── The words ──────────────────────────────────────────────────────────────

def test_the_two_format_causes_say_what_happened_and_do_not_say_retry():
    """ "Retry the analysis." after a failure the model caused sends the
    reader back to the same failure. The sentence says what happened; what
    to do next is the page's buttons and the note beside them."""
    by_code = {category.code: category for category in runs._PUBLIC_FAILURE_CATEGORIES}
    for code in ("quality_checks", "provider_response_format"):
        category = by_code[code]
        for sentence in (category.message, category.own_keys):
            assert sentence and "Retry the analysis" not in sentence and "retry" not in sentence.lower(), sentence
        assert "did not come back in the form" in category.message
        assert "API keys" in category.own_keys and "another model" in category.own_keys
        # Still nobody's alert but the reader's: the operator is paged for causes only the operator can remove.
        assert category.deployment is None and code not in runs.OPERATOR_FAILURE_CODES
    table = RUN_JS[RUN_JS.index("const FAILURE_STRINGS = {"):RUN_JS.index("/** The sentence to show for why a run stopped")]
    for code in ("quality_checks", "provider_response_format"):
        for key in (code, f'"{code}:own_keys"'):
            sentence = re.search(rf'^\s+{re.escape(key)}: "([^"]+)",$', table, re.M)[1]
            assert "请重试" not in sentence and "没有按要求的格式返回" in sentence, sentence


def test_the_markers_and_codes_are_as_they_were():
    """Display only: which raw reason means which cause is not this change's."""
    by_code = {category.code: category.markers for category in runs._PUBLIC_FAILURE_CATEGORIES}
    assert by_code["quality_checks"] == ("guardrail", "blocking validation errors", "evidence validation failed",
                                         "final report validation failed")
    assert by_code["provider_response_format"] == ("response_format", "failed to convert text into a pydantic model",
                                                   "not json serializable", "jsondecodeerror", "invalid json")
    assert runs._public_failure("Evidence validation failed for the academic task")[0] == "quality_checks"
    assert runs._REFUND_REASONS == frozenset({"launch_failed", "provider_unreachable"}), "The refund rule is not this change's"


def test_every_new_string_is_in_both_languages():
    english = RUN_JS[RUN_JS.index("const HEADER_STRINGS = {"):RUN_JS.index('  "Simplified Chinese": {', RUN_JS.index("const HEADER_STRINGS = {"))]
    chinese = RUN_JS[RUN_JS.index('  "Simplified Chinese": {', RUN_JS.index("const HEADER_STRINGS = {")):RUN_JS.index("export function headerLabel")]
    keys = ("advice_model_kind", "advice_model_short", "resume_note_quota", "resume_note_step", "resume_note_step_first",
            "resume_note_model", "resume_note_model_changed", "resume_step_evidence", "resume_step_writing",
            "resume_step_review", "fix_model", "fix_keys", "leave_note", "leave_notify")
    for key in keys:
        for table, pattern in ((english, r"[一-鿿]"), (chinese, None)):
            found = re.search(rf'^\s+{key}: "((?:[^"\\]|\\.)*)",$', table, re.M)
            assert found, key
            if pattern:
                assert not re.search(pattern, found[1]), key
            else:
                assert re.search(r"[一-鿿]", found[1]), key
        slots = [set(re.findall(r"\{(\w+)\}", re.search(rf'^\s+{key}: "((?:[^"\\]|\\.)*)",$', table, re.M)[1]))
                 for table in (english, chinese)]
        assert slots[0] == slots[1], key


def test_a_topic_never_turned_into_english_is_said_so_in_each_language(page):
    """Four production runs (2026-11-23) searched a Chinese topic as typed, then failed as "unknown".
    The stop that replaces them names itself, and is not worded as a count of papers found."""
    for funded_by in (None, "deployment", "own_keys"):
        code, sentence = runs._public_failure(
            "Topic planning produced no English search phrase: the topic was not translated", funded_by=funded_by)
        facts = {"state": "failed", "error": sentence, "error_code": code, "funded_by": funded_by,
                 "artifacts": ["retrieval"],
                 "retrieval_shortfall": {"stage": "topic_planning", "accepted_sources": 0, "required_sources": 3}}
        english, chinese = page([EN, "failureText", [facts]], [ZH, "failureText", [facts]])
        assert code == "topic_not_translated"
        assert english == sentence and "nothing was searched" in english
        assert chinese.startswith("题目没有被转成英文检索词，所以没有进行任何检索。")
        assert ("API Key" in chinese) == (funded_by == "own_keys")
        assert "已校验证据" not in chinese


def test_the_page_refuses_the_scripts_the_worker_refuses(page):
    """The preview refuses a search phrase the run would stop on, and no other.

    A run stops before any search when its phrase is in a script
    detect_language reads as not English (topic_not_translated), and the stop
    counts as the day's run. The page's own test must draw the line in the
    same place: checked at each end of each of the worker's ranges, and one
    code point beyond.
    """
    from academic_agent.language import detect_language

    ranges = ((0x0400, 0x052F), (0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0x1100, 0x11FF),
              (0x3040, 0x30FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xAC00, 0xD7AF), (0xFB50, 0xFDFF),
              (0xFE70, 0xFEFF))
    probes = sorted({point for low, high in ranges for point in (low - 1, low, high, high + 1)})
    phrases = ["drowning rescue " + chr(point) for point in probes]
    said = page(*([EN, "searchPhraseProblem", [phrase]] for phrase in phrases))
    for point, phrase, problem in zip(probes, phrases, said, strict=True):
        worker_refuses = not detect_language(phrase).startswith("en")
        assert (problem == "not_english") == worker_refuses, hex(point)
    assert any(problem == "not_english" for problem in said)
    assert page([EN, "searchPhraseProblem", ["drowning rescue"]]) == [None]
    assert page([EN, "searchPhraseProblem", ["ab"]]) == ["too_short"]
