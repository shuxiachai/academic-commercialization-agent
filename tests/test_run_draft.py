"""The draft of a run that stopped before it had a report: the reviewer's text, else the writer's.

A production run (2026-11-18) failed in scoring 25 minutes and about 141,000
tokens in. Its three analysts, its writer and its reviewer had all returned;
the report file is written only after the scorer has, so the page said "this
run produced no report". The writer's and the reviewer's answers were on disk
the whole time, as the checkpoints a resume reuses.

`runs.draft_report` reads the later of the two, the reviewer's when it is
usable, and the run's reads advertise it as the artifact `draft` with
`draft_stage` saying which it is (until 2026-11-20 it was always the
writer's, under a notice that said it came before the review). These tests
hold when there is one, when there is not, and that it opens to exactly the
readers the run's other artifacts open to, through the route they already use.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import api.runs as runs
from academic_agent.checkpoints import CheckpointIdentity, CheckpointStore, hash_text
from academic_agent.run_terminal import TerminalRecord, UsageAccounting, commit_terminal_record
from api import access
from api.main import app

DRAFT = (
    "# Commercialization Assessment: Sodium-Ion Storage\n\n"
    "## Executive Summary\n\nSodium-ion cells are in pilot production [A1]. "
    "An actor-specific GO/NO_GO is not assessed.\n\n"
    "## References\n\n- [A1] A paper. URL: https://example.org/a1\n"
)
# The same text after the review, as the reviewer's guardrail leaves it: the
# plan's one correction applied and its notes appended.
REVIEWED = DRAFT.replace("in pilot production [A1]", "in pilot-line production [A1]") + (
    "\n## Reviewer Notes\n\n- Applied: Named the production stage the cited paper reports.\n"
)
_START = datetime(2026, 11, 18, 9, tzinfo=UTC)


@pytest.fixture
def root(tmp_path: Path):
    with patch.object(runs, "DEFAULT_OUTPUT_ROOT", tmp_path), patch.object(runs, "_registry", {}), \
            patch.object(access, "ACCESS_CODE", None), patch.object(access, "ACCESS_CODES", None), \
            patch.object(access, "ADMIN_CODE", None):
        yield tmp_path


def _commit(run_dir: Path, node: str, text: str) -> None:
    CheckpointStore(run_dir).commit(
        CheckpointIdentity(
            node_id=node, input_sha256=hash_text("input"), evidence_sha256=hash_text("evidence"),
            config_sha256=hash_text("config"), upstream_sha256={}, pipeline_revision="test-revision",
            as_of_date=date(2026, 11, 18), model=None,
        ),
        text, output_format="markdown",
    )


def _run(root: Path, serial: int, *, state: str = "failed", writer: str | None = DRAFT, report: str | None = None,
         language: str = "English") -> str:
    run_id = f"202611{serial:02d}T090000Z-" + f"{serial:x}" * 32
    run_dir = root / run_id
    run_dir.mkdir()
    status = {"stage": "Done" if state == "completed" else "Error", "done": True, "topic": "sodium-ion storage",
              "error": None if state == "completed" else "boom", "output_language": language}
    (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
    if writer is not None:
        _commit(run_dir, "writer", writer)
    if report is not None:
        (run_dir / "commercialization_report.md").write_text(report, encoding="utf-8")
    end = _START + timedelta(seconds=1531)
    reasons = {"completed": "worker_completed", "failed": "worker_exception", "cancelled": "user_cancelled",
               "timeout": "hard_timeout"}
    commit_terminal_record(run_dir, TerminalRecord(
        state=state, reason_code=reasons[state],
        termination_method="worker_exit" if state in {"completed", "failed"} else "terminate",
        started_at=_START, ended_at=end, elapsed_seconds=1531,
        last_stage=status["stage"], timeout_seconds=1800, usage=None,
        usage_accounting=UsageAccounting(state="unavailable", snapshot_at=end, run_complete=state == "completed",
                                         in_flight_request_may_have_spent=state != "completed"),
    ))
    return run_id


@pytest.mark.parametrize("state", ["failed", "cancelled", "timeout"])
def test_a_run_that_stopped_after_writing_has_its_draft(root: Path, state: str) -> None:
    run_id = _run(root, 1, state=state)
    assert runs.draft_report(run_id, state) == runs.Draft(stage="writer", text=DRAFT)
    client = TestClient(app)
    for path in (f"/api/runs/{run_id}", f"/api/runs/{run_id}/progress"):
        artifacts = client.get(path).json()["artifacts"]
        assert "draft" in artifacts and "report" not in artifacts, path
    reply = client.get(f"/api/runs/{run_id}/draft")
    assert reply.status_code == 200
    assert reply.headers["content-type"].startswith("text/markdown")
    assert "Sodium-ion cells are in pilot production [A1]." in reply.text


def test_the_draft_is_served_in_the_words_the_page_shows_a_report_in(root: Path) -> None:
    run_id = _run(root, 1, language="Simplified Chinese")
    text = TestClient(app).get(f"/api/runs/{run_id}/draft").text
    # report_display: the fixed heading table for the run's language, and the spelling of the gate.
    assert "## 执行摘要" in text and "## Executive Summary" not in text
    assert "GO / NO-GO" in text and "GO/NO_GO" not in text
    # The saved checkpoint is what a resume reuses: showing it changes no byte of it.
    assert runs.draft_report(run_id, "failed").text == DRAFT


def test_a_run_that_stopped_before_writing_has_none(root: Path) -> None:
    run_id = _run(root, 1, writer=None)
    assert runs.draft_report(run_id, "failed") is None
    client = TestClient(app)
    assert "draft" not in client.get(f"/api/runs/{run_id}").json()["artifacts"]
    reply = client.get(f"/api/runs/{run_id}/draft")
    assert reply.status_code == 409
    assert "no draft" in reply.json()["detail"]


def test_a_completed_run_shows_its_report_not_a_draft(root: Path) -> None:
    run_id = _run(root, 1, state="completed", report="# Report\n\nFinal.")
    client = TestClient(app)
    artifacts = client.get(f"/api/runs/{run_id}").json()["artifacts"]
    assert "report" in artifacts and "draft" not in artifacts
    assert client.get(f"/api/runs/{run_id}/draft").status_code == 409


def test_a_stopped_run_that_does_have_a_report_shows_that(root: Path) -> None:
    """A failure after the report was saved: the report is the later, fuller text."""
    run_id = _run(root, 1, report="# Report\n\nFinal.")
    assert runs.draft_report(run_id, "failed") is None
    assert "draft" not in TestClient(app).get(f"/api/runs/{run_id}").json()["artifacts"]


@pytest.mark.parametrize("state", ["running", "completed", "unknown"])
def test_no_draft_is_read_for_a_run_that_has_not_stopped(root: Path, state: str) -> None:
    run_id = _run(root, 1)
    assert runs.draft_report(run_id, state) is None


def test_a_checkpoint_that_does_not_match_its_manifest_is_no_draft(root: Path) -> None:
    run_id = _run(root, 1)
    [output] = (root / run_id / "checkpoints" / "writer").glob("output-*.md")
    output.write_text(DRAFT + "\nA line added after the commit.\n", encoding="utf-8")
    assert runs.draft_report(run_id, "failed") is None
    client = TestClient(app)
    assert "draft" not in client.get(f"/api/runs/{run_id}").json()["artifacts"]
    assert client.get(f"/api/runs/{run_id}/draft").status_code == 409


def test_an_empty_checkpoint_is_no_draft(root: Path) -> None:
    run_id = _run(root, 1, writer="  \n")
    assert runs.draft_report(run_id, "failed") is None


def test_a_run_whose_reviewer_had_answered_shows_the_reviewed_report(root: Path) -> None:
    """Production, 2026-11-20: a run failed in scoring with the reviewer's
    checkpoint saved, and its page showed the writer's text under "before
    the review that checks its citations and claims".

    The reviewer's checkpoint is the reviewed report, not the reviewer's
    plan: evidence.make_reviewer_guardrail applies the plan to the writer's
    text, re-checks it and appends the Reviewer Notes, and the checkpoint
    holds that text (checkpoint_runtime commits a task's output after its
    guardrail). On the local run of 2026-11-20 whose report is on disk, the
    report is that checkpoint with its Reviewer Notes moved to their own
    file and the code's applicability paragraph put in after the title, and
    nothing else changed."""
    run_id = _run(root, 1)
    _commit(root / run_id, "reviewer", REVIEWED)
    client = TestClient(app)
    text = client.get(f"/api/runs/{run_id}/draft").text
    assert "in pilot production [A1]" not in text, "the writer's sentence the reviewer corrected"
    assert "Sodium-ion cells are in pilot-line production [A1]." in text
    assert "## Reviewer Notes" in text
    for path in (f"/api/runs/{run_id}", f"/api/runs/{run_id}/progress"):
        body = client.get(path).json()
        assert "draft" in body["artifacts"] and body.get("draft_stage") == "reviewer", path
    draft = runs.draft_report(run_id, "failed")
    assert (draft.stage, draft.text) == ("reviewer", REVIEWED)


def test_a_writers_draft_says_so_on_both_reads(root: Path) -> None:
    run_id = _run(root, 1)
    client = TestClient(app)
    for path in (f"/api/runs/{run_id}", f"/api/runs/{run_id}/progress"):
        assert client.get(path).json().get("draft_stage", "absent") == "writer", path
    no_draft = _run(root, 2, writer=None)
    for path in (f"/api/runs/{no_draft}", f"/api/runs/{no_draft}/progress"):
        assert client.get(path).json().get("draft_stage", "absent") is None, path


def test_a_reviewers_checkpoint_that_does_not_match_its_manifest_leaves_the_writers(root: Path) -> None:
    run_id = _run(root, 1)
    _commit(root / run_id, "reviewer", REVIEWED)
    [output] = (root / run_id / "checkpoints" / "reviewer").glob("output-*.md")
    output.write_text(REVIEWED + "\nA line added after the commit.\n", encoding="utf-8")
    client = TestClient(app)
    assert "in pilot production [A1]" in client.get(f"/api/runs/{run_id}/draft").text
    assert client.get(f"/api/runs/{run_id}").json().get("draft_stage") == "writer"
    draft = runs.draft_report(run_id, "failed")
    assert (draft.stage, draft.text) == ("writer", DRAFT)


def test_only_the_report_steps_checkpoints_are_a_draft(root: Path) -> None:
    run_id = _run(root, 1, writer=None)
    _commit(root / run_id, "scorer", DRAFT)
    assert runs.draft_report(run_id, "failed") is None
    # A reviewer's checkpoint verifies by its own manifest, writer or not.
    _commit(root / run_id, "reviewer", REVIEWED)
    assert TestClient(app).get(f"/api/runs/{run_id}/draft").status_code == 200
    assert runs.draft_report(run_id, "failed").stage == "reviewer"


def test_an_id_that_is_not_a_run_reads_nothing(root: Path) -> None:
    assert runs.draft_report("../outside", "failed") is None
    assert TestClient(app).get("/api/runs/not-a-run/draft").status_code == 404


def test_the_draft_is_one_more_name_on_the_artifact_route_and_no_route_of_its_own() -> None:
    """Showing a draft opened no new door: it is fetched the way every other artifact is."""
    assert runs.DRAFT_ARTIFACT in runs.artifact_names()
    paths = {route.path for route in app.routes}
    assert "/api/runs/{run_id}/{artifact}" in paths
    assert not [path for path in paths if "draft" in path]


def test_the_draft_opens_to_the_readers_the_runs_other_artifacts_open_to(root: Path) -> None:
    """A run link is a read capability; the draft is neither more open nor more closed than `sources`."""
    run_id = _run(root, 1)
    (root / run_id / "validated_sources.json").write_text("{}", encoding="utf-8")
    (root / run_id / ".owner").write_text(access.owner_id("for-alice"), encoding="utf-8")
    with patch.object(access, "ACCESS_CODES", "for-alice,for-bob"), patch.object(access, "ADMIN_CODE", "for-admin"):
        client = TestClient(app)
        for headers in ({}, {"X-Access-Code": "for-alice"}, {"X-Access-Code": "for-bob"},
                        {"X-Access-Code": "not-a-code"}):
            sources = client.get(f"/api/runs/{run_id}/sources", headers=headers).status_code
            draft = client.get(f"/api/runs/{run_id}/draft", headers=headers).status_code
            assert draft == sources == 200, headers
        # The list of a code's runs stays behind the code, as before.
        assert client.get("/api/runs").status_code == 401


# ── While the run is still going ─────────────────────────────────────────────
#
# The run of 2026-11-27 spent 8 min 57 s in its review, and its writer's report
# had been saved the whole time, as the checkpoint the review starts from. The
# page showed it only after the run had failed. A run in its review, or in the
# scoring after it, now lists the same saved text as `draft`, with
# `draft_stage` saying whose it is; the page offers it under a label that says
# it is not the assessment yet.

REVIEW = "Agent 5 — Quality Review & Citation Check"
SCORING = "Agent 6 — Commercialization Scoring"
WRITING = "Agent 4 — Report Writing"


class _Alive:
    def poll(self):
        return None


def _running(root: Path, serial: int, stage: str, *, writer: str | None = DRAFT,
             reviewer: str | None = None) -> str:
    run_id = f"202611{serial:02d}T090000Z-" + f"{serial:x}" * 32
    run_dir = root / run_id
    run_dir.mkdir()
    (run_dir / "status.json").write_text(json.dumps({
        "stage": stage, "done": False, "topic": "sodium-ion storage", "output_language": "English",
        "stage_timings": [{"stage": stage, "started_at": datetime.now(UTC).isoformat()}],
    }), encoding="utf-8")
    if writer is not None:
        _commit(run_dir, "writer", writer)
    if reviewer is not None:
        _commit(run_dir, "reviewer", reviewer)
    runs._registry[run_id] = runs._Handle(run_id=run_id, topic="sodium-ion storage", proc=_Alive())
    return run_id


def test_a_run_in_its_review_offers_what_its_writer_finished(root: Path) -> None:
    run_id = _running(root, 1, REVIEW)
    client = TestClient(app)
    for path in (f"/api/runs/{run_id}", f"/api/runs/{run_id}/progress"):
        body = client.get(path).json()
        assert body["state"] == "running", path
        assert "draft" in body["artifacts"] and body["draft_stage"] == "writer", path
    reply = client.get(f"/api/runs/{run_id}/draft")
    assert reply.status_code == 200
    assert "Sodium-ion cells are in pilot production [A1]." in reply.text


def test_a_run_in_its_scoring_offers_the_reviewed_report(root: Path) -> None:
    run_id = _running(root, 1, SCORING, reviewer=REVIEWED)
    client = TestClient(app)
    assert client.get(f"/api/runs/{run_id}").json()["draft_stage"] == "reviewer"
    assert "pilot-line production [A1]" in client.get(f"/api/runs/{run_id}/draft").text


def test_a_run_still_writing_offers_no_draft(root: Path) -> None:
    """Before the review starts there is nothing finished to read: a writer's checkpoint left
    from an earlier attempt is not this run's text yet."""
    run_id = _running(root, 1, WRITING)
    client = TestClient(app)
    body = client.get(f"/api/runs/{run_id}").json()
    assert "draft" not in body["artifacts"] and body["draft_stage"] is None
    assert client.get(f"/api/runs/{run_id}/draft").status_code == 409


def test_a_run_in_its_review_has_no_draft_pdf(root: Path) -> None:
    """An export is cached for good, and this text changes when the review finishes: the PDF
    of a draft stays for a run that has stopped (runs.draft_report)."""
    run_id = _running(root, 1, REVIEW)
    assert runs.draft_report(run_id, "running") is None
    assert TestClient(app).get(f"/api/runs/{run_id}/report.pdf").status_code == 409
    assert not (root / run_id / "commercialization_draft.pdf").exists()


def test_a_running_runs_draft_opens_to_the_readers_its_other_artifacts_open_to(root: Path) -> None:
    run_id = _running(root, 1, REVIEW)
    (root / run_id / "validated_sources.json").write_text("{}", encoding="utf-8")
    (root / run_id / ".owner").write_text(access.owner_id("for-alice"), encoding="utf-8")
    with patch.object(access, "ACCESS_CODES", "for-alice,for-bob"), patch.object(access, "ADMIN_CODE", "for-admin"):
        client = TestClient(app)
        for headers in ({}, {"X-Access-Code": "for-alice"}, {"X-Access-Code": "for-bob"}):
            sources = client.get(f"/api/runs/{run_id}/sources", headers=headers).status_code
            draft = client.get(f"/api/runs/{run_id}/draft", headers=headers).status_code
            assert draft == sources == 200, headers
