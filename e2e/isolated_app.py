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
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import uvicorn

from academic_agent.run_output import create_run_id, save_report
from academic_agent.report_audit import save_report_audit
from academic_agent.run_spec import DecisionContext
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
