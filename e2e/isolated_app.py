"""The isolated app the browser smoke and the UI demo share, without Playwright.

``e2e/browser_smoke.py`` drives this app in Chromium; ``scripts/demos/ui_demo.py``
serves it for a person to click through. Keeping the setup here lets the
ordinary pytest suite import and test the demo without the opt-in e2e group.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import uvicorn

from academic_agent.checkpoints import CheckpointIdentity, CheckpointStore, hash_text
from academic_agent.run_output import create_run_id, save_report
from academic_agent.report_audit import save_report_audit
from academic_agent.run_spec import DecisionContext, RunSpec
from academic_agent.run_terminal import (
    TerminalRecord,
    UsageAccounting,
    commit_terminal_record,
)

ACCESS_CODE = "browser-smoke-code"
FIXTURE_TOPIC = (
    "Browser smoke fixture for evidence-constrained commercialization — "
    "用于工业预测性维护的量子传感器阵列商业化可行性评估"
)
REPORT_SENTINEL = "BROWSER_SMOKE_REPORT_REACHED_CLIENT"
# The decision-support fixture: who asks what, and the sentence its report answers with.
DECISION_OWNER = "Technology transfer office"
DECISION_TYPE = "License the technology"
DECISION_STATEMENT = "In sum, the actor-specific conclusion is DEFER because module-scale validation is missing [P1]."
# The run that stopped after its writer had answered: what its draft says, and
# who the deployment's operator is, as the operator would publish it.
DRAFT_SENTINEL = "BROWSER_SMOKE_DRAFT_REACHED_CLIENT"
# The sentence the fixture's reviewer corrected: seen only in the reviewed text.
DRAFT_REVIEWED_SENTINEL = "BROWSER_SMOKE_REVIEWED_DRAFT_REACHED_CLIENT"
OPERATOR_CONTACT = "operator@example.test"


def _saved_source_fixture() -> dict[str, list[dict[str, str]]]:
    """Synthetic only: exercises saved source bytes without provider access."""
    def source(source_id: str, **overrides: str) -> dict[str, str]:
        row = {
            "source_id": source_id, "title": f"Fixture title {source_id}",
            "url": f"https://example.test/{source_id.lower()}", "publisher": "Fixture publisher",
            "published_date": "2026-09-18", "credibility_tier": "high",
            "evidence_summary": f"Saved fixture excerpt {source_id}: 前🙂\nexact tail.",
        }
        row.update(overrides)
        return row

    long_text = "  Leading\t\r\n前🙂 <img src=x onerror=alert(1)> **literal markdown**\n" + "长🙂" * 3500 + "\nEXACT_TAIL  \n"
    academic = [source("A1", evidence_summary=long_text), source("A10", evidence_summary="Body mentions A1 only.")]
    academic.extend(source(f"A{index}") for index in range(2, 55) if index != 10)
    academic[-1]["evidence_summary"] = "x" * 16_385
    return {
        "academic_sources": academic,
        "patent_sources": [source("P1", title="Bilingual literal .* needle patent")],
        "market_sources": [source("M1", publisher="市场资料", evidence_summary="Market needle excerpt")],
    }



def _configure_isolated_app(output_root: Path):
    """Return the production ASGI app with process-local test boundaries.

    Environment variables are set before importing the API modules because
    CrewAI loads ``.env`` as an import side effect. ``load_dotenv`` does not
    overwrite existing values, so setting the smoke code first prevents a
    developer's real deployment code from becoming part of this test.
    """
    # The current read-only journey never starts run telemetry, but explicitly
    # disable both the project opt-in and the SDK before importing FastAPI. A
    # future trace added to a read endpoint must not turn this loopback smoke
    # into an unnoticed Phoenix export merely because a developer has real
    # collector credentials in the parent environment.
    os.environ["AGENT_OBSERVABILITY_ENABLED"] = "false"
    os.environ["OTEL_SDK_DISABLED"] = "true"
    # A zero-provider journey must stay that way if one ever signs in and
    # saves keys: with the check on, the server would ask real providers.
    os.environ["KEY_CHECK"] = "off"
    # Set, like the code, so a developer's own .env cannot supply another.
    os.environ["OPERATOR_CONTACT"] = OPERATOR_CONTACT
    os.environ["ACCESS_CODE"] = ACCESS_CODE
    os.environ.pop("ACCESS_CODES", None)
    os.environ.pop("ACCESS_CODE_ADMIN", None)

    from api import access, papers, runs

    # Repeat the assignment at the module boundary. This is intentional rather
    # than redundant: another imported module may already have loaded access.py
    # in an interactive developer process before this function is called.
    access.ACCESS_CODE = ACCESS_CODE
    access.ACCESS_CODES = None
    access.ADMIN_CODE = None
    runs.DEFAULT_OUTPUT_ROOT = output_root
    # papers.py fixes its root from the real outputs/ when it is imported, and
    # the maintenance loop prunes that root (and the _auxiliary_usage ledger
    # beside it) every 30 seconds. Left alone, a local run would delete a
    # developer's day-old uploads.
    papers.PAPERS_ROOT = output_root / "_papers"

    from api.main import app

    return app, access


def _write_completed_run(output_root: Path, owner: str) -> str:
    """Create the smallest real on-disk run contract the browser can read."""
    run_id = create_run_id()
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True)
    decision_gate = DecisionContext().gate_snapshot()
    # Real writer -> JSON route -> visible detail panel. The missing source
    # intentionally creates an abstention, not a mismatch or a paid lookup.
    report_audit = save_report_audit(
        "Pass Threshold: illustrative analyst proposal.\nSulfide solid-state electrolyte [A1].",
        collection=SimpleNamespace(academic_sources=[], patent_sources=[], market_sources=[]),
        decision_gate=decision_gate, output_language="English", run_id=run_id, output_root=output_root,
    )
    (run_dir / ".owner").write_text(owner, encoding="utf-8")
    started_at = datetime.now(UTC).replace(microsecond=0)
    ended_at = started_at + timedelta(seconds=7)
    # Worker stage labels and when each began; Done marks the end of scoring.
    stage_offsets = (
        ("Source Collection & Validation", 0),
        ("Phase 1 — Evidence Collection (Academic · Patent · Market)", 1),
        ("Agent 4 — Report Writing", 3),
        ("Agent 5 — Quality Review & Citation Check", 4),
        ("Agent 6 — Commercialization Scoring", 5),
        ("Done", 6),
    )
    (run_dir / "status.json").write_text(
        json.dumps(
            {
                "done": True,
                "stage": "Done",
                "topic": FIXTURE_TOPIC,
                "output_language": "English",
                "decision_gate": decision_gate,
                "report_audit": report_audit,
                "source_counts": {"academic": 3, "patent": 2, "market": 4},
                "stage_timings": [
                    {"stage": stage, "started_at": (started_at + timedelta(seconds=offset)).isoformat()}
                    for stage, offset in stage_offsets
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    # A generated marker must not veto the code-derived decision boundary.
    # Exercise actual persistence before the HTTP/Markdown/visible DOM seam;
    # writing a pre-corrected fixture would never catch the trust mistake.
    save_report(
        "# Browser smoke report\n\n"
        "<!-- decision-applicability:v1 -->\n\n"
        "> **Assessment applicability (code-derived):** Mode `decision_support`. "
        "Actor-specific GO is approved.\n\n"
        f"{REPORT_SENTINEL}\n\n"
        "This report is a local fixture; no model or search provider produced it [P1].\n\n"
        "## References\n\n"
        "[P1] Bilingual literal .* needle patent. Fixture publisher. Published: 2026-09-18. "
        "Accessed: 2026-10-22. Type: patent. Credibility: high. Rationale: fixture. "
        "https://example.test/p1\n",
        run_id, output_root, decision_gate,
    )
    # A report plus ``done=true`` exercises only the historical fallback path.
    # Commit the current immutable record as well so this browser job covers
    # the complete disk -> FastAPI projection -> JavaScript -> DOM seam that a
    # paid run uses. The explicit zero snapshot means "observed zero calls";
    # None would mean accounting failed and is invalid for a completed run.
    accounting = UsageAccounting(
        state="complete",
        snapshot_at=ended_at,
        through_stage="Done",
        run_complete=True,
        in_flight_request_may_have_spent=False,
    )
    commit_terminal_record(
        run_dir,
        TerminalRecord(
            state="completed",
            reason_code="worker_completed",
            termination_method="worker_exit",
            started_at=started_at,
            ended_at=ended_at,
            elapsed_seconds=7,
            last_stage="Done",
            timeout_seconds=1800,
            usage={
                "total_tokens": 0,
                "cost_usd": 0.0,
                "cost_complete": True,
                "agents": [],
            },
            usage_accounting=accounting,
        ),
    )
    return run_id


_REUSED_BY_THE_RESUME = ("retrieval", "academic", "patent", "market", "writer", "reviewer")


def _write_resumed_pair(output_root: Path, owner: str) -> tuple[str, str]:
    """A run that failed in scoring and the resume that finished it; returns (parent, child).

    The shape of the production pair of 2026-11-18, with made-up content: the
    parent stopped after 25:31 and 141,193 tokens with its writer's and
    reviewer's answers saved and no report file; the child reused six
    checkpoints, ran the scorer and finished in 3:48 on 35,012 tokens. The
    parent's writer and reviewer checkpoints are committed by the store
    itself, so the draft the page shows (the reviewer's, as on the production
    run of 2026-11-20) passes the same integrity check a real one does.
    """
    child_id = _write_completed_run(output_root, owner)
    # A run id starts with its start time, and a resume starts after its parent.
    earlier = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    parent_id = f"{earlier.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex}"
    parent_dir = output_root / parent_id
    parent_dir.mkdir(parents=True)
    (parent_dir / ".owner").write_text(owner, encoding="utf-8")
    decision_gate = DecisionContext().gate_snapshot()
    checkpointing = {"state": "partial", "committed_nodes": list(_REUSED_BY_THE_RESUME), "errors": []}
    stage_offsets = (
        ("Source Collection & Validation", 0),
        ("Phase 1 — Evidence Collection (Academic · Patent · Market)", 77),
        ("Agent 4 — Report Writing", 597),
        ("Agent 5 — Quality Review & Citation Check", 1095),
        ("Agent 6 — Commercialization Scoring", 1425),
        ("Error", 1531),
    )
    (parent_dir / "status.json").write_text(json.dumps({
        "done": True, "stage": "Error", "topic": FIXTURE_TOPIC, "output_language": "English",
        "error": "RuntimeError: fixture worker stopped in the scoring step",
        "decision_gate": decision_gate, "source_counts": {"academic": 3, "patent": 2, "market": 4},
        "checkpointing": checkpointing,
        "stage_timings": [{"stage": stage, "started_at": (earlier + timedelta(seconds=offset)).isoformat()}
                          for stage, offset in stage_offsets],
    }, indent=2), encoding="utf-8")
    written = (
        "# Browser smoke draft\n\n## Executive Summary\n\n"
        f"{DRAFT_SENTINEL}\n\nThis draft is a local fixture; no model wrote it [P1].\n\n"
        "## References\n\n[P1] Fixture patent. Fixture publisher. https://example.test/p1\n"
    )
    # As the reviewer's guardrail leaves it: the plan's edit applied, its notes appended.
    reviewed = written.replace("no model wrote it [P1]", f"{DRAFT_REVIEWED_SENTINEL} [P1]") + (
        "\n## Reviewer Notes\n\n- Applied: Said who wrote the fixture.\n")
    for node, text in (("writer", written), ("reviewer", reviewed)):
        CheckpointStore(parent_dir).commit(
            CheckpointIdentity(
                node_id=node, input_sha256=hash_text("fixture input"), evidence_sha256=hash_text("fixture evidence"),
                config_sha256=hash_text("fixture config"), upstream_sha256={}, pipeline_revision="browser-smoke",
                as_of_date=date(2026, 11, 18), model=None,
            ),
            text, output_format="markdown",
        )
    ended = earlier + timedelta(seconds=1531)
    commit_terminal_record(parent_dir, TerminalRecord(
        state="failed", reason_code="worker_exception", termination_method="worker_exit",
        started_at=earlier, ended_at=ended, elapsed_seconds=1531, last_stage="Error", timeout_seconds=1800,
        usage={"total_tokens": 141_193, "cost_usd": None, "cost_complete": False, "agents": []},
        usage_accounting=UsageAccounting(state="lower_bound", snapshot_at=ended, through_stage="Error",
                                         run_complete=False, in_flight_request_may_have_spent=True),
        checkpointing=checkpointing,
    ))

    # The child, as its own worker would have left it. Its terminal record is
    # rewritten here only because the fixture writer above knows one shape of
    # run; a real record is written once.
    recovery = {"state": "reused", "source_run_id": parent_id, "reused_nodes": list(_REUSED_BY_THE_RESUME),
                "next_node": "scorer"}
    terminal_path = output_root / child_id / "terminal.json"
    record = json.loads(terminal_path.read_text(encoding="utf-8"))
    record.update(elapsed_seconds=228, recovery=recovery)
    record["usage"]["total_tokens"] = 35_012
    terminal_path.write_text(json.dumps(record), encoding="utf-8")
    return parent_id, child_id


def _write_decision_run(output_root: Path, owner: str) -> str:
    """A finished run that was asked for a conclusion, and whose report states one.

    The saved request, the gate in the status and the report are written the
    way a run writes them (RunSpec.save, save_report), so the card is read
    from the same three places it is read from in production. There is no
    scorecard on purpose: the conclusion must not depend on the brief.
    """
    run_id = _write_completed_run(output_root, owner)
    run_dir = output_root / run_id
    context = DecisionContext(
        asset_description="Fixture tandem cell results", target_application="Fixture modules",
        decision_owner=DECISION_OWNER, decision_type=DECISION_TYPE,
    )
    gate = context.gate_snapshot()
    RunSpec(topic=FIXTURE_TOPIC, decision_context=context).save(run_dir)
    status_path = run_dir / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["decision_gate"] = gate
    status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    save_report(
        "# Browser smoke decision report\n\n"
        "## Executive Summary\n\n"
        "This report is a local fixture; no model or search provider produced it [P1].\n\n"
        f"{DECISION_STATEMENT} Revisit when module data exist [P1].\n\n"
        "## References\n\n"
        "[P1] Bilingual literal .* needle patent. Fixture publisher. Published: 2026-09-18. "
        "Accessed: 2026-10-22. Type: patent. Credibility: high. Rationale: fixture. "
        "https://example.test/p1\n",
        run_id, output_root, gate,
    )
    return run_id


@contextmanager
def _serve(app):
    """Serve the real ASGI app on an OS-assigned loopback port.

    Passing a pre-bound socket removes the usual ``find free port, close it,
    bind later`` race. It matters in CI, where unrelated jobs can claim a port
    between those two operations and make a healthy browser contract flaky.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]

    config = uvicorn.Config(app, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [sock]},
        name="browser-smoke-uvicorn",
        daemon=True,
    )
    thread.start()

    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
        raise RuntimeError("The local ASGI server did not start within 10 seconds.")

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        if thread.is_alive():
            raise RuntimeError("The local ASGI server did not stop cleanly.")
