"""A failed run's page says whether it counted from the first read that says it failed.

Production, 2026-11-20: run 20261120T124622Z-1827116d6b583b33bec4105490f163d1
failed in scoring with provider_unreachable. The page that had been open
through the run said "This run counted toward today's quota."; GET
/api/runs/{id} said refunded; only a reload showed the refund sentence.

Measured on main 166130d, with the tests below:

- `runs.get_state` reports "running" for as long as the worker's process is
  alive (its handle occupies a slot) and "failed" from the moment it has
  exited, whether or not the handle has been reaped yet.
- The refund (`_refund_unreachable_failure_locked`) runs only when an exited
  worker's handle is reaped. The run's own reads, GET /api/runs/{id} and
  /progress, reaped nothing. Admission, GET /health, GET /api/runs and the
  alert loop do (the loop every 30 s, and only where alerts are configured).
- The page stops polling at its first terminal read (`follow()` in run.js),
  so it kept the "charged" it read between the worker's exit and the reap.

A run's reads now reap that run's own exited worker before they read it. A
read that says "failed" has therefore already had the refund decided, so the
page's first terminal read is its last word and needs no second look. The
fourth unreachable failure of an owner's day is still charged, and says so.

Who reads decides nothing: the refund goes to the run's owner, under the
unchanged rule and bound, and GET /health, which needs no credentials at all,
already reaped every exited worker. A read only makes the decision when the
run is looked at instead of at the next health check.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from academic_agent.run_terminal import TerminalRecord, UsageAccounting, commit_terminal_record
from api import access, runs
from api.main import app

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "web" / "static" / "js"

OWNER = "code-owner-a"
UNREACHABLE = "APIConnectionError: Connection error."
REFUNDED = ("This run did not count toward today's quota: the model provider could not be reached, "
            "which nothing in your request caused.")
REFUNDED_ZH = "本次运行未计入今日额度：模型服务暂时无法连接，与你的请求无关。"
CHARGED = "This run counted toward today's quota."


class _Worker:
    """A worker process the test ends: alive until `exit()`."""

    def __init__(self) -> None:
        self.code: int | None = None

    def exit(self, code: int = 1) -> None:
        self.code = code

    def poll(self) -> int | None:
        return self.code

    def terminate(self) -> None:
        self.code = -15

    def kill(self) -> None:
        self.code = -9

    def wait(self, timeout=None) -> int:
        return self.code if self.code is not None else 0


@pytest.fixture
def root(tmp_path: Path):
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    patches = [
        patch.object(runs, "DEFAULT_OUTPUT_ROOT", outputs),
        patch.object(runs, "MAX_CONCURRENT", 50), patch.object(runs, "BYOK_MAX_CONCURRENT", None),
        patch.object(runs, "DAILY_CAP", 10), patch.object(runs, "ACCOUNT_DAILY_CAP", 10),
        patch.object(runs, "_daily_counts", {}), patch.object(runs, "_daily_date", None),
        patch.object(runs, "_registry", {}), patch.object(runs, "_settled", []),
        patch.object(runs, "_inline_paid_operations", {}), patch.object(runs, "_inline_owners", {}),
        patch.object(runs, "_stop_claims", {}),
        patch.object(runs, "_unreachable_refunds", {}), patch.object(runs, "_unreachable_refund_date", None),
        patch.object(access, "ACCESS_CODE", None), patch.object(access, "ACCESS_CODES", None),
        patch.object(access, "ADMIN_CODE", None),
    ]
    for item in patches:
        item.start()
    try:
        yield outputs
    finally:
        for item in reversed(patches):
            item.stop()


_SERIAL = iter(range(1, 10_000))


def _run(root: Path, *, owner: str = OWNER, error: str = UNREACHABLE) -> tuple[str, _Worker]:
    """A charged run on the deployment's keys, its worker still going, its outcome already on disk.

    The worker writes its status and its terminal record and then exits:
    the order pipeline_worker.py keeps. The test decides when it exits.
    """
    run_id = f"20261120T{next(_SERIAL):06d}Z-{'cd' * 16}"
    run_dir = root / run_id
    run_dir.mkdir()
    (run_dir / ".owner").write_text(owner, encoding="utf-8")
    with runs._registry_lock:
        charged_on = runs._admit_paid_operation_locked(owner=owner, byok=False)
    runs._write_daily_charge(run_dir, charged_on)
    (run_dir / "status.json").write_text(json.dumps({
        "stage": "Error", "done": True, "topic": "solid-state lithium-metal cells", "error": error,
    }), encoding="utf-8")
    now = datetime.now(UTC)
    commit_terminal_record(run_dir, TerminalRecord(
        state="failed", reason_code="worker_exception", termination_method="worker_exit",
        started_at=now - timedelta(seconds=1456), ended_at=now, elapsed_seconds=1456,
        last_stage="Error", timeout_seconds=1800, usage=None,
        usage_accounting=UsageAccounting(state="lower_bound", snapshot_at=now, through_stage="Error",
                                         run_complete=False, in_flight_request_may_have_spent=True),
    ))
    worker = _Worker()
    runs._registry[run_id] = runs._Handle(run_id=run_id, topic="t", proc=worker, owner=owner)
    return run_id, worker


def _used(owner: str = OWNER) -> int:
    return runs.daily_quota(owner)["used"]


# ── The page, as it follows a run ─────────────────────────────────────────

_FOLLOW = """
    globalThis.localStorage = { getItem: () => null, setItem: () => {} };
    globalThis.document = { querySelectorAll: () => [], documentElement: {} };
    // The page's own poll loop, with its waits taken out: the replies are
    // what the API gave, read by the test in the order the page asks.
    globalThis.setTimeout = (fn) => { setImmediate(fn); return 1; };
    const [replies, language] = JSON.parse(process.argv[2]);
    let asked = 0;
    globalThis.__api = { getProgress: async () => replies[Math.min(asked++, replies.length - 1)] };
    const run = await import("./run.mjs");
    const i18n = await import("./i18n.js");
    i18n.setLanguage(language);
    const done = await new Promise((resolve) => run.follow("r", { onDone: resolve }));
    // Let any further tick that was going to happen happen.
    await new Promise((resolve) => setImmediate(() => setImmediate(resolve)));
    console.log(JSON.stringify({ line: run.outcomeSummary(done), asked }));
"""


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    node = shutil.which("node")
    assert node, "Node must execute the page's own module; skipping loses the seam"
    work = tmp_path_factory.mktemp("charge-on-read")
    source = (JS / "run.js").read_text(encoding="utf-8")
    (work / "run.mjs").write_text(
        source.replace('import * as api from "./api.js";', "const api = globalThis.__api;"), encoding="utf-8")
    shutil.copy2(JS / "i18n.js", work / "i18n.js")
    (work / "follow.mjs").write_text(textwrap.dedent(_FOLLOW), encoding="utf-8")

    def follow(replies: list[dict], language: str = "English") -> dict:
        done = subprocess.run([node, "follow.mjs", json.dumps([replies, language])], capture_output=True,
                              text=True, encoding="utf-8", cwd=work, check=False)
        assert done.returncode == 0, done.stderr[-1500:]
        return json.loads(done.stdout)

    return follow


def _watch(client: TestClient, run_id: str, worker: _Worker, path: str = "progress") -> list[dict]:
    """What a page open through the run reads: one poll while it runs, then the exit, then two more."""
    url = f"/api/runs/{run_id}/progress" if path == "progress" else f"/api/runs/{run_id}"
    replies = [client.get(url).json()]
    worker.exit()
    replies += [client.get(url).json(), client.get(url).json()]
    return replies


# ── The two cases the page must say right ─────────────────────────────────

def test_a_page_open_when_the_provider_became_unreachable_ends_on_the_refund(root: Path, page) -> None:
    run_id, worker = _run(root)
    assert _used() == 1
    replies = _watch(TestClient(app), run_id, worker)
    # The page stops at its first terminal read and keeps that read's line.
    seen = page(replies)
    assert seen["asked"] == 2, "follow() ends at the first terminal read"
    assert seen["line"].endswith(" " + REFUNDED) and CHARGED not in seen["line"]
    assert page(replies, "Simplified Chinese")["line"].endswith(REFUNDED_ZH)
    assert replies[0]["state"] == "running"
    first_failed = replies[1]
    assert first_failed["state"] == "failed" and first_failed["error_code"] == "provider_unreachable"
    # The first read that says "failed" already carries the refund, so the
    # page has nothing to wait for.
    assert (first_failed["daily_charge"], first_failed["daily_charge_reason"]) == ("refunded", "provider_unreachable")
    assert _used() == 0


def test_the_status_read_says_the_same_as_the_progress_read(root: Path) -> None:
    client = TestClient(app)
    run_id, worker = _run(root)
    replies = _watch(client, run_id, worker, path="status")
    assert replies[0]["state"] == "running"
    assert [(r["state"], r["daily_charge"]) for r in replies[1:]] == [("failed", "refunded")] * 2
    progress = client.get(f"/api/runs/{run_id}/progress").json()
    assert (progress["daily_charge"], progress["daily_charge_reason"]) == ("refunded", "provider_unreachable")


def test_the_fourth_unreachable_failure_of_the_day_says_it_counted(root: Path, page) -> None:
    """Three a day are given back (UNREACHABLE_REFUNDS_PER_DAY); the fourth is a real charge."""
    assert runs.UNREACHABLE_REFUNDS_PER_DAY == 3
    client = TestClient(app)
    earlier = [_run(root) for _ in range(3)]
    for _run_id, worker in earlier:
        worker.exit()
    runs.active_count()   # reaped the way admission and /health reap them
    assert [runs._read_daily_charge(root / run_id) for run_id, _ in earlier] == ["refunded"] * 3
    run_id, worker = _run(root)
    replies = _watch(client, run_id, worker)
    assert [(r["state"], r["daily_charge"]) for r in replies] == [
        ("running", "charged"), ("failed", "charged"), ("failed", "charged")]
    assert replies[1]["daily_charge_reason"] is None
    seen = page(replies)
    assert seen["asked"] == 2 and seen["line"].endswith(" " + CHARGED)
    # Final, not pending: whatever reaps it later changes nothing.
    client.get("/health")
    assert client.get(f"/api/runs/{run_id}").json()["daily_charge"] == "charged"
    assert _used() == 1


def test_any_other_failure_read_the_same_way_stays_charged(root: Path) -> None:
    client = TestClient(app)
    run_id, worker = _run(root, error="Guardrail failed: blocking validation errors")
    replies = _watch(client, run_id, worker)
    assert [(r["state"], r["daily_charge"]) for r in replies[1:]] == [("failed", "charged")] * 2
    assert replies[1]["error_code"] == "quality_checks"
    assert _used() == 1


# ── A write on a read: once, under the lock, for the run's owner ──────────

def test_reads_at_the_same_moment_give_the_day_back_once(root: Path) -> None:
    client = TestClient(app)
    _run(root, error="Guardrail failed: blocking validation errors")   # holds one unit that stays spent
    run_id, worker = _run(root)
    assert _used() == 2
    worker.exit()
    barrier = threading.Barrier(8)
    replies: list[dict] = []

    def read() -> None:
        barrier.wait()
        replies.append(client.get(f"/api/runs/{run_id}/progress").json())

    threads = [threading.Thread(target=read) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert _used() == 1, "one unit back, not one per reader"
    assert {(r["state"], r["daily_charge"]) for r in replies} == {("failed", "refunded")}


def test_a_refund_whose_marker_could_not_be_written_is_not_given_again_by_the_next_read(root: Path) -> None:
    """The ledger is what reopens the day and the marker only tells the page
    (_refund_unreachable_failure_locked). A marker that failed to record the
    refund must not make every later read refund the run again."""
    client = TestClient(app)
    _run(root, error="Guardrail failed: blocking validation errors")
    run_id, worker = _run(root)
    worker.exit()
    original = runs._write_daily_charge

    def no_refund_marker(run_dir, charged_on, *, refunded=False, refund_reason=None):
        if refunded:
            raise OSError("disk full")
        return original(run_dir, charged_on, refunded=refunded, refund_reason=refund_reason)

    with patch.object(runs, "_write_daily_charge", no_refund_marker):
        for _ in range(4):
            client.get(f"/api/runs/{run_id}/progress")
    assert _used() == 1


def test_who_reads_the_run_decides_nothing(root: Path) -> None:
    """A run link is a read capability, and anyone holding it may now be the
    one whose read reaps the worker. The refund still goes to the run's owner
    under the owner's own bound; the reader's day is not touched."""
    alice = access.owner_id("for-alice")
    with patch.object(access, "ACCESS_CODES", "for-alice,for-bob"):
        client = TestClient(app)
        run_id, worker = _run(root, owner=alice)
        with runs._registry_lock:
            runs._admit_paid_operation_locked(owner=access.owner_id("for-bob"), byok=False)
        worker.exit()
        for headers in ({}, {"X-Access-Code": "for-bob"}):
            reply = client.get(f"/api/runs/{run_id}", headers=headers)
            assert reply.status_code == 200 and reply.json()["daily_charge"] == "refunded"
        assert _used(alice) == 0
        assert _used(access.owner_id("for-bob")) == 1
        assert runs._unreachable_refunds == {alice: 1}


def test_a_health_check_that_needs_no_credentials_already_did_the_same(root: Path) -> None:
    """What a read does now is what GET /health did before it, for anyone:
    the read adds no decision, only an earlier moment for it."""
    client = TestClient(app)
    run_id, worker = _run(root)
    worker.exit()
    assert client.get("/health").status_code == 200
    assert runs._read_daily_charge(root / run_id) == "refunded"
    assert _used() == 0


def test_a_run_whose_worker_is_still_going_is_left_alone(root: Path) -> None:
    client = TestClient(app)
    run_id, _worker = _run(root)
    for _ in range(3):
        reply = client.get(f"/api/runs/{run_id}/progress").json()
        assert (reply["state"], reply["daily_charge"]) == ("running", "charged")
    assert run_id in runs._registry and _used() == 1
