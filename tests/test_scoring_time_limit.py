"""A run whose scoring the time budget refused, and the resume that finished it.

Production, 2026-11-27, run 20261127T084855Z-fe95b989 on qwen3.8-2.4t-a95b, a
model that cannot turn thinking off. Sources 0:34, evidence 5:09, report 10:47,
review 8:57: the reviewer's one attempt returned at 09:14:34.88 and the scoring
stage ended 0.08 s later with no provider attempt in its step log. The hard
deadline was 09:18:55.75, so the scorer had 200.8 s before the finalization
edge (runtime_budget.paid_work_deadline), and a thinking model's attempt asks
for a 300-second window (llm_config._give_thinking_time). The budget refused
the attempt before anything was sent (RunDeadlineExceeded), the worker
recorded "worker failed", and the page said "The analysis failed. Retry or
contact the operator with the run ID", the sentence for a cause nobody could
name. Its owner suspected their key and their topic. The resume, with nothing
changed, ran the same scoring in 213.7 s. Run 20261118T090017Z-7d84b0d1 has
the same record: reviewer back at 25:31, scoring 0 s, no attempt.

Held here: the refusal reaches the API as its own cause; every cause that is
the server's says it was not the reader's topic or key and leads to the
resume; the toast after a resume says what it does again; and a resumed run's
stage list marks what it takes from its parent from the first read, not ten
seconds later once the worker has started. The time limit and the quota are
not changed: the refused run stays charged as before.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import textwrap
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from crewai import Agent, Crew, Task
from fastapi.testclient import TestClient

from academic_agent import checkpoint_runtime, llm_config, pipeline_worker
from academic_agent.checkpoint_runtime import TASK_NODES, pipeline_revision, retrieval_identity
from academic_agent.checkpoints import CheckpointIdentity, CheckpointStore, hash_text
from academic_agent.llm_config import RunDeadlineExceeded, configure_llm_deadline, create_llm
from academic_agent.run_spec import RunSpec
from academic_agent.run_terminal import TerminalRecord, UsageAccounting, commit_terminal_record
from api import access, runs
from api.main import app

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "web" / "static" / "js"
RUN_JS = (JS / "run.js").read_text(encoding="utf-8")
APP_JS = (JS / "app.js").read_text(encoding="utf-8")
I18N_JS = (JS / "i18n.js").read_text(encoding="utf-8")

TOPIC = "Phase change thermal energy storage materials for cold chain insulated containers"
SCORER = f"Commercialization Readiness Scorer for {TOPIC}"
# What the run had saved when the scorer was refused (production, 2026-11-27).
SAVED = ["retrieval", "academic", "patent", "market", "writer", "reviewer"]
NOT_YOURS_EN = "Nothing in your topic or keys caused this."
NOT_YOURS_ZH = "这不是你的题目或 Key 的问题。"


def _refusal_text(remaining: float = 200.8, required: float = 300.0) -> str:
    """The worker's record of the refusal, made by the code that makes it."""
    budget = llm_config._CallBudget(
        deadline_monotonic=time.monotonic() + remaining, stage=SCORER, request_timeout_seconds=required)
    with pytest.raises(RunDeadlineExceeded) as refused:
        budget.require_window()
    return pipeline_worker._error_text(refused.value)


# ── The refusal, through CrewAI, as the worker meets it ─────────────────────


@pytest.fixture
def provider(monkeypatch):
    """Counts every HTTP request a provider object would send; answers none."""
    class Counting:
        requests = 0

    def send(client, request, **_):
        Counting.requests += 1
        raise AssertionError("the budget refused this attempt; nothing may be sent")

    monkeypatch.setattr(httpx.Client, "send", send)
    monkeypatch.setattr(llm_config.time, "sleep", lambda seconds: None)
    for name, value in (("CREWAI_DISABLE_TELEMETRY", "true"), ("OTEL_SDK_DISABLED", "true"),
                        ("CREWAI_TRACING_ENABLED", "false")):
        monkeypatch.setenv(name, value)
    return Counting


def test_the_refused_scorer_sends_nothing_and_its_reason_reaches_the_worker_whole(provider):
    """CrewAI runs a node again when its agent raises (max_retry_limit 2); the
    node is not asked again (llm_config gave_up), and the exception the worker
    catches is the budget's own, which the API then names."""
    llm = create_llm(provider="qwen", api_key="made-up-key-never-sent", model="qwen3.8-2.4t-a95b", stream=True)
    configure_llm_deadline(llm, deadline_monotonic=time.monotonic() + 200.8, stage=SCORER,
                           request_timeout_seconds=300.0)
    agent = Agent(role=SCORER, goal="Score it.", backstory="Scores.", llm=llm, verbose=False)
    task = Task(description="Score it.", expected_output="A scorecard.", agent=agent)

    with pytest.raises(RunDeadlineExceeded) as refused:
        Crew(agents=[agent], tasks=[task], verbose=False).kickoff()

    assert provider.requests == 0
    text = pipeline_worker._error_text(refused.value)
    assert re.fullmatch(rf"{re.escape(SCORER)} has 2\d\d\.\ds remaining; a bounded provider attempt requires 300\.0s",
                        text), text
    assert runs._public_failure(text)[0] == "run_time_limit"


# ── What the API says ────────────────────────────────────────────────────────


def test_the_refusal_is_named_and_every_reader_is_told_it_was_not_theirs():
    text = _refusal_text()
    for funded_by in (None, "deployment", "own_keys"):
        code, sentence = runs._public_failure(text, funded_by=funded_by)
        assert code == "run_time_limit", funded_by
        assert NOT_YOURS_EN in sentence
        assert "time limit" in sentence and "resum" in sentence.lower()
        # The provider's words and the topic never cross the boundary.
        assert TOPIC not in sentence and "300.0s" not in sentence


def test_a_refusal_whose_text_also_reads_as_an_earlier_cause_keeps_that_cause():
    """Placed last on purpose. The refund for an unreachable provider is decided
    by the same reading (runs._refund_unreachable_failure_locked), and the
    scorer's role carries the topic, so a refusal whose cause or topic matches
    an earlier category must keep the code it has today: no run's charge moves."""
    order = [category.code for category in runs._PUBLIC_FAILURE_CATEGORIES]
    assert order[-1] == "run_time_limit"
    for category in runs._PUBLIC_FAILURE_CATEGORIES[:-1]:
        for marker in category.markers:
            text = f"Commercialization Readiness Scorer for {marker} sensors has 1.0s remaining; " \
                   "a bounded provider attempt requires 300.0s"
            before = category.code
            assert runs._public_failure(text)[0] in (before, "provider_unreachable"), (marker, before)
    # A refusal after a dead connection is still the unreachable provider, refunded as before.
    after_dead = _refusal_text(5.0, 64.2) + " (caused by APIConnectionError: Connection error.)"
    assert runs._public_failure(after_dead)[0] == "provider_unreachable"


def test_the_other_causes_that_are_the_servers_say_so_too():
    unreachable = runs._public_failure("openai.APIConnectionError: Connection error.", funded_by="own_keys")
    assert unreachable[0] == "provider_unreachable" and NOT_YOURS_EN in unreachable[1]


# ── The failed run as the worker leaves it, read through the API ─────────────


def _failed_at_scoring(root: Path, owner: str | None = "user:4242", *, error: str | None = None) -> str:
    run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{'fe95b989' * 4}"
    run_dir = root / run_id
    run_dir.mkdir()
    if owner is not None:
        (run_dir / ".owner").write_text(owner, encoding="utf-8")
    now = datetime.now(UTC)
    (run_dir / "status.json").write_text(json.dumps({
        "stage": "Error", "done": True, "topic": TOPIC, "error": error or _refusal_text(),
        "checkpointing": {"state": "partial", "committed_nodes": SAVED, "errors": []},
    }), encoding="utf-8")
    commit_terminal_record(run_dir, TerminalRecord(
        state="failed", reason_code="worker_exception", termination_method="worker_exit",
        started_at=now - timedelta(seconds=1538), ended_at=now, elapsed_seconds=1538,
        last_stage="Error", timeout_seconds=1800, usage=None,
        usage_accounting=UsageAccounting(state="lower_bound", snapshot_at=now, through_stage="Error",
                                         run_complete=False, in_flight_request_may_have_spent=True)))
    return run_id


@pytest.fixture
def output_root(tmp_path, monkeypatch):
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(runs, "_registry", {})
    return tmp_path


def test_the_failed_run_reads_as_the_time_limit_for_its_owner(output_root):
    state = runs.get_state(_failed_at_scoring(output_root))
    assert (state["state"], state["error_code"], state["funded_by"]) == ("failed", "run_time_limit", "own_keys")
    assert NOT_YOURS_EN in state["error"]


def test_a_watchdog_timeout_says_it_was_not_theirs_either(output_root):
    run_id = _failed_at_scoring(output_root)
    terminal = output_root / run_id / "terminal.json"
    record = json.loads(terminal.read_text(encoding="utf-8"))
    record.update(state="timeout", reason_code="hard_timeout", termination_method="kill")
    terminal.write_text(json.dumps(record), encoding="utf-8")
    state = runs.get_state(run_id)
    assert state["error_code"] == "timeout_resumable" and NOT_YOURS_EN in state["error"]


# ── The page: the reason, the next step, the toast, the first stage list ─────

_HARNESS = """
    globalThis.localStorage = { getItem: () => null, setItem: () => {} };
    globalThis.document = { querySelectorAll: () => [], documentElement: {} };
    const run = await import("./run.mjs");
    const i18n = await import("./i18n.js");
    const out = JSON.parse(process.argv[2]).map(([language, call, args]) => {
      i18n.setLanguage(language);
      const value = run[call](...args);
      return value instanceof Set ? [...value] : value;
    });
    console.log(JSON.stringify(out));
"""
EN, ZH = "English", "Simplified Chinese"


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    node = shutil.which("node")
    assert node, "Node must execute the page's own module; skipping loses the seam"
    work = tmp_path_factory.mktemp("time-limit-page")
    (work / "run.mjs").write_text(RUN_JS.replace('import * as api from "./api.js";', "const api = {};"),
                                  encoding="utf-8")
    shutil.copy2(JS / "i18n.js", work / "i18n.js")
    (work / "harness.mjs").write_text(textwrap.dedent(_HARNESS), encoding="utf-8")

    def ask(*calls):
        done = subprocess.run([node, "harness.mjs", json.dumps(list(calls))], capture_output=True, text=True,
                              encoding="utf-8", cwd=work, check=False)
        assert done.returncode == 0, done.stderr[-1500:]
        return json.loads(done.stdout)

    return ask


def test_the_failure_page_names_the_cause_in_chinese_and_offers_the_resume(page, output_root):
    progress = runs.get_state(_failed_at_scoring(output_root))
    shown = {key: progress[key] for key in ("state", "error", "error_code", "funded_by")}
    text, guide, operator = page(
        [ZH, "failureText", [shown]],
        [ZH, "failureGuide", [{**shown, "resumable": True}]],
        [ZH, "needsOperator", [shown]],
    )
    assert NOT_YOURS_ZH in text and "运行时限" in text and "续跑" in text
    assert guide["primary"] == "resume"
    assert operator is False, "the cause is named; nobody needs the run ID sent to them"
    for code in ("provider_unreachable", "timeout_resumable"):
        assert NOT_YOURS_ZH in page([ZH, "failureText", [{"state": "failed", "error_code": code}]])[0], code


def test_the_toast_says_what_the_resume_does_again(page):
    only_scoring, from_evidence, unknown, english = page(
        [ZH, "resumedToast", [SAVED]],
        [ZH, "resumedToast", [["retrieval"]]],
        [ZH, "resumedToast", [None]],
        [EN, "resumedToast", [SAVED]],
    )
    assert only_scoring == "已从检查点续跑，只重做评分。"
    assert "证据分析" in from_evidence and "凭据" not in from_evidence
    assert unknown == "已从检查点续跑。"
    assert english == "Resumed from the checkpoint: only the scoring runs again."


def test_the_resumed_run_marks_what_it_reuses_before_its_worker_reports(page):
    expected = {"reused_nodes": SAVED}
    # The worker's first word, written while its stage is still the first one:
    # the retrieval it has checked, before it inspects the rest.
    provisional = {"state": "reused", "reused_nodes": ["retrieval"], "next_node": "academic"}
    worker = {"state": "reused", "reused_nodes": SAVED, "next_node": "scorer"}
    first, cold, early, settled = page(
        [ZH, "stageStates", ["", "running", [], None, expected]],
        [ZH, "stageStates", ["", "running", [], None, None]],
        [ZH, "stageStates", ["Source Collection & Validation", "running", [], provisional, expected]],
        [ZH, "stageStates", ["Agent 6 — Commercialization Scoring", "running", [], worker, None]],
    )
    assert [stage["state"] for stage in first] == ["reused"] * 4 + ["pending"]
    assert [stage["state"] for stage in cold] == ["pending"] * 5
    # Not back to one reused stage for the second before the worker settles.
    assert [stage["state"] for stage in early] == ["reused"] * 4 + ["pending"]
    assert [stage["state"] for stage in settled] == ["reused"] * 4 + ["active"]


def test_the_page_wires_both_in():
    # The toast reads the parent's saved checkpoints, captured with the button.
    assert 'toast(t("msg_resumed")' not in APP_JS and "msg_resumed" not in I18N_JS
    assert "runView.resumedToast(" in APP_JS
    # Both renders of the stage list pass what the API expects a resume to reuse.
    assert APP_JS.count("progress.recovery, progress.resume_expected)") == 2


# ── A resumed run's first read ───────────────────────────────────────────────


def _committed_parent(root: Path, *, revision: str | None = None, nodes=SAVED) -> tuple[str, RunSpec]:
    # Each parent its own ID: a test that makes two in the same second must not collide.
    run_id = f"{(datetime.now(UTC) - timedelta(minutes=30)).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex}"
    run_dir = root / run_id
    run_dir.mkdir()
    spec = RunSpec(topic=TOPIC)
    spec.save(run_dir)
    revision = revision or pipeline_revision()
    today = datetime.now(UTC).date()
    store = CheckpointStore(run_dir)
    store.commit(retrieval_identity(spec, revision=revision, as_of_date=today), '{"topic": "fixture"}',
                 output_format="json")
    for node in nodes[1:]:
        store.commit(CheckpointIdentity(
            node_id=node, input_sha256=hash_text("input"), evidence_sha256=hash_text("evidence"),
            config_sha256=hash_text("config"), upstream_sha256={}, pipeline_revision=revision,
            as_of_date=today, model=None,
        ), f"# {node}\n", output_format="markdown")
    now = datetime.now(UTC)
    (run_dir / "status.json").write_text(json.dumps({"stage": "Error", "done": True, "error": _refusal_text(),
                                                     "topic": TOPIC}), encoding="utf-8")
    commit_terminal_record(run_dir, TerminalRecord(
        state="failed", reason_code="worker_exception", termination_method="worker_exit",
        started_at=now - timedelta(seconds=1538), ended_at=now, elapsed_seconds=1538, last_stage="Error",
        timeout_seconds=1800, usage=None,
        usage_accounting=UsageAccounting(state="lower_bound", snapshot_at=now, through_stage="Error",
                                         run_complete=False, in_flight_request_may_have_spent=True)))
    return run_id, spec


@pytest.fixture
def client(output_root, monkeypatch):
    monkeypatch.setattr(access, "ACCESS_CODE", None)
    monkeypatch.setattr(access, "ACCESS_CODES", None)
    monkeypatch.setattr(runs, "DAILY_CAP", 0)
    monkeypatch.setattr(runs, "_daily_counts", {})
    monkeypatch.setattr(runs, "_daily_date", None)
    monkeypatch.setattr(runs, "_inline_paid_operations", {})
    yield TestClient(app)
    runs._registry.clear()


def _resume(client, parent: str) -> str:
    process = MagicMock()
    process.poll.return_value = None     # the worker is alive and has written nothing yet
    with patch("api.runs.subprocess.Popen", return_value=process):
        accepted = client.post(f"/api/runs/{parent}/resume", json={})
    assert accepted.status_code == 202, accepted.text
    return accepted.json()["run_id"]


def test_the_first_read_of_a_resume_says_what_it_will_take_from_its_parent(client, output_root):
    parent, _spec = _committed_parent(output_root)
    child = _resume(client, parent)
    for path in (f"/api/runs/{child}", f"/api/runs/{child}/progress"):
        body = client.get(path).json()
        assert body["state"] == "running" and body["stage"] in ("", None), path
        assert body["recovery"] is None, "nothing the worker validated is claimed"
        assert body["resume_expected"] == {"reused_nodes": SAVED}, path

    # The worker's first word covers only the retrieval it has checked, while
    # its stage is still the first one (pipeline_worker, after source
    # collection): that is not where it starts, and the expectation stands.
    status = output_root / child / "status.json"
    status.write_text(json.dumps({
        "stage": "Source Collection & Validation", "topic": TOPIC,
        "recovery": {"state": "reused", "source_run_id": parent, "reused_nodes": ["retrieval"],
                     "next_node": "academic", "inspections": {}},
    }), encoding="utf-8")
    assert client.get(f"/api/runs/{child}/progress").json()["resume_expected"] == {"reused_nodes": SAVED}

    # Once the worker reports where it really starts, its word is the one shown.
    status.write_text(json.dumps({
        "stage": "Agent 6 — Commercialization Scoring", "topic": TOPIC,
        "recovery": {"state": "reused", "source_run_id": parent, "reused_nodes": SAVED,
                     "next_node": "scorer", "inspections": {}},
    }), encoding="utf-8")
    assert client.get(f"/api/runs/{child}/progress").json()["resume_expected"] is None


def test_nothing_is_expected_that_the_worker_would_refuse(client, output_root):
    # Saved by another deployment: the worker cold-starts every node.
    parent, _spec = _committed_parent(output_root, revision="git:0123456789abcdef0123456789abcdef01234567")
    child = _resume(client, parent)
    assert client.get(f"/api/runs/{child}/progress").json()["resume_expected"] is None

    # The worker already said it starts cold, while still in its first stage.
    parent, _spec = _committed_parent(output_root)
    child = _resume(client, parent)
    (output_root / child / "status.json").write_text(json.dumps({
        "stage": "Source Collection & Validation", "topic": TOPIC,
        "recovery": {"state": "cold_start", "source_run_id": parent, "reused_nodes": [],
                     "next_node": "academic", "inspections": {}},
    }), encoding="utf-8")
    assert client.get(f"/api/runs/{child}/progress").json()["resume_expected"] is None


def test_only_the_saved_prefix_is_expected(client, output_root):
    """The worker reuses the longest unbroken prefix (CheckpointRuntime.restore_contiguous_prefix)."""
    assert list(TASK_NODES[:5]) == SAVED[1:] and checkpoint_runtime.TASK_NODES[-1] == "scorer"
    parent, _spec = _committed_parent(output_root, nodes=["retrieval", "academic", "patent", "market", "writer"])
    child = _resume(client, parent)
    assert client.get(f"/api/runs/{child}/progress").json()["resume_expected"] == {
        "reused_nodes": ["retrieval", "academic", "patent", "market", "writer"]}

    # A gap ends it: the writer and reviewer saved after a missing market
    # analysis are run again, not taken.
    parent, _spec = _committed_parent(output_root, nodes=["retrieval", "academic", "patent", "writer", "reviewer"])
    child = _resume(client, parent)
    assert client.get(f"/api/runs/{child}/progress").json()["resume_expected"] == {
        "reused_nodes": ["retrieval", "academic", "patent"]}
