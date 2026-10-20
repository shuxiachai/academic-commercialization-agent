"""Auxiliary usage must cross real caller/storage/HTTP/browser boundaries."""
import asyncio
from contextlib import contextmanager
from datetime import UTC, date, datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import httpx
from fastapi.testclient import TestClient

from academic_agent import auxiliary_usage as aux, language, llm_config, pdf_extractor
from academic_agent.checkpoint_runtime import retrieval_identity
from academic_agent.checkpoints import CheckpointStore
from academic_agent.run_spec import RunSpec
from api import access, auxiliary_usage as pdf_usage, main, papers, receipts, runs
from tests.test_server_receipts import contribution, headers, paid_api  # noqa: F401
from tests.scripted_waits import STEP

USAGE = {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}
SDK_USAGE = {**USAGE, "successful_requests": 1}
# paid_api patches the shared subprocess module to prevent worker dispatch.
# Capture this before fixture setup, and use it only for the fixed Node harness.
_NODE_POPEN = subprocess.Popen


def ledger(tmp_path):
    return aux.Collector(tmp_path / aux.FILE_NAME)


def sdk(monkeypatch, *, body=None, counters=None, call=None):
    class FakeLLM:
        model = "qwen3.5-plus"

        def call(self, messages):
            if call is not None:
                return call(messages)
            return body if body is not None else json.dumps(contribution().model_dump())

        def get_token_usage_summary(self):
            return SDK_USAGE if counters is None else counters

    monkeypatch.setattr(llm_config, "create_llm", lambda **_: FakeLLM())
    monkeypatch.setattr(pdf_extractor, "extract_pdf_text", lambda *_, **__: "Offline bounded paper text")


def http(monkeypatch, data, observer=lambda: None):
    monkeypatch.setattr(llm_config, "resolve_provider_config", lambda: llm_config.ProviderConfig(
        "qwen", "qwen3.5-plus", "https://provider.invalid/v1", "offline-key"))

    @contextmanager
    def response(*args, **kwargs):
        observer()
        yield SimpleNamespace(read=lambda: json.dumps(data.pop(0)).encode())

    monkeypatch.setattr(language, "urlopen", response)


@pytest.mark.allow_llm
def test_language_reserves_before_http_and_preserves_usage_before_invalid_body(tmp_path, monkeypatch):
    """Previously valid usage was discarded when choices/content parsing failed."""
    collector = ledger(tmp_path)
    observed = []
    http(monkeypatch, [{"usage": USAGE, "choices": []}],
         lambda: observed.append(aux.read_ledger(collector.path).calls[0].state))
    with aux.bind(collector), pytest.warns(UserWarning, match="IndexError"):
        assert language.translate_to_english("PRIVATE_PROMPT") == "PRIVATE_PROMPT"
    collector.finish()
    result = collector.summary()
    assert observed == ["pending"]
    assert result["observed_tokens"] == 12
    assert result["calls"][0]["outcome"] == "response_invalid"
    assert result["provider_attempt_count"] == 1
    raw = collector.path.read_text()
    assert not any(word in raw for word in ("PRIVATE", "offline-key", "provider.invalid", "choices", "IndexError"))
    assert aux.current() is None


@pytest.mark.allow_llm
def test_planning_and_actual_fallback_translation_are_distinct(tmp_path, monkeypatch):
    """A single blanket planner count hid the actual second fallback request."""
    collector = ledger(tmp_path)
    http(monkeypatch, [{"usage": USAGE, "choices": [{"message": {"content": text}}]}
                       for text in ("malformed plan", "translated battery")])
    with aux.bind(collector):
        assert language.plan_topic_search("电池研究").search_topic == "translated battery"
    collector.finish()
    summary = collector.summary()
    assert [c["stage"] for c in summary["calls"]] == ["search_planning", "translation"]
    assert summary["observed_tokens"] == 24 and summary["provider_attempt_count"] == 2


@pytest.mark.parametrize("bad", [None, {}, {"prompt_tokens": True, "completion_tokens": 2},
    {"prompt_tokens": -1, "completion_tokens": 2}, {"prompt_tokens": float("nan"), "completion_tokens": 2},
    {"prompt_tokens": float("inf"), "completion_tokens": 2}, {**USAGE, "total_tokens": False},
    {**USAGE, "cached_prompt_tokens": 11}])
def test_bad_usage_never_becomes_zero_or_measured(bad, tmp_path):
    """Absent/malformed numeric observations cannot masquerade as a free call."""
    collector = ledger(tmp_path)
    seq = collector.begin("translation", "http_attempt", "qwen3.5-plus")
    collector.settle(seq, aux.parse_usage(bad, "qwen3.5-plus"), "returned")
    collector.finish()
    assert collector.summary()["observed_tokens"] is None
    assert collector.summary()["observed_cost_usd"] is None
    assert collector.summary()["cost_complete"] is False


def test_unknown_model_and_legacy_or_corrupt_sidecar_are_not_empty_success(tmp_path):
    """Raw unknown model strings are not whitelisted facts or price identities."""
    path = tmp_path / aux.FILE_NAME
    assert aux.read_summary(path)["record_state"] == "not_recorded"
    assert aux.read_summary(path)["observed_cost_usd"] is None
    collector = ledger(tmp_path)
    seq = collector.begin("translation", "http_attempt", "SECRET/unknown-model")
    collector.settle(seq, aux.parse_usage(USAGE, "SECRET/unknown-model"), "returned")
    collector.finish()
    assert collector.summary()["observed_cost_usd"] is None
    assert "SECRET" not in path.read_text()
    path.write_text('{"schema_version":true}', encoding="utf-8")
    assert aux.read_summary(path)["record_state"] == "unreadable"
    before = path.read_bytes()
    broken = ledger(tmp_path)
    broken.finish()
    assert broken.summary()["record_state"] == "write_failed" and path.read_bytes() == before


@pytest.mark.parametrize("model", ["qwen3.7-plus", "qwen3.8-max", "qwen3.8-27b"])
def test_production_qwen_models_are_known_helper_identities(model, tmp_path):
    """Helper calls on the current production models must not be recorded as
    unknown-model observations with no tokens."""
    collector = ledger(tmp_path)
    seq = collector.begin("translation", "http_attempt", model)
    collector.settle(seq, aux.parse_usage(USAGE, model), "returned")
    collector.finish()
    assert collector.summary()["call_count"] == 1
    assert collector.summary()["observed_tokens"] == 12


def test_same_call_finalization_is_not_cumulative(tmp_path):
    """Duplicate settlement previously could turn one observed charge into two."""
    collector = ledger(tmp_path)
    seq = collector.begin("translation", "http_attempt", "qwen3.5-plus")
    tokens = aux.parse_usage(USAGE, "qwen3.5-plus")
    collector.settle(seq, tokens, "returned")
    collector.settle(seq, tokens, "returned")
    collector.finish()
    before = collector.path.read_bytes()
    collector.finish()
    assert collector.path.read_bytes() == before
    assert collector.summary()["call_count"] == 1 and collector.summary()["observed_tokens"] == 12


@pytest.mark.parametrize("counters", [SDK_USAGE, {k: 0 for k in SDK_USAGE}, {}])
def test_pdf_parse_failure_collects_own_sdk_but_never_claims_complete_attempts(tmp_path, monkeypatch, counters):
    """A finally collector keeps billed parse failures; SDK zeros are not evidence."""
    sdk(monkeypatch, body="PRIVATE INVALID JSON", counters=counters)
    collector = ledger(tmp_path)
    with aux.bind(collector), pytest.raises(ValueError, match="non-JSON"):
        pdf_extractor._call_llm_json("PRIVATE_INPUT")
    collector.finish()
    result = collector.summary()
    assert result["provider_attempt_count"] is None and result["cost_complete"] is False
    assert result["observed_tokens"] == (12 if counters == SDK_USAGE else None)
    assert result["calls"][0]["unit"] == "llm_invocation"
    assert result["calls"][0]["outcome"] == "response_invalid"
    assert "PRIVATE" not in collector.path.read_text()


def test_pdf_http_replay_get_and_run_association_do_not_recharge(paid_api, monkeypatch):
    """The actual HTTP response model and both run endpoints must deliver the sidecar."""
    client, launch, root = paid_api
    sdk(monkeypatch)
    auth = headers()
    files = {"file": ("paper.pdf", b"%PDF-offline")}
    first = client.post("/api/papers", headers=auth, files=files)
    assert first.status_code == 200, first.text
    body = first.json()
    summary = body["auxiliary_usage"]
    assert summary["observed_tokens"] == 12 and not summary["cost_complete"]
    path = pdf_usage.paper_path(body["paper_id"])
    before = path.read_bytes()
    for _ in range(2):
        receipt = client.get("/api/receipts", headers=auth).json()
        assert receipt["auxiliary_usage"] == summary and receipt["response"] == body
        assert client.post("/api/papers", headers=auth, files=files).json() == body
    assert path.read_bytes() == before
    accepted = client.post("/api/runs", headers=headers(), json={"topic": "Offline study", "paper_id": body["paper_id"]})
    assert accepted.status_code == 202, accepted.text
    run_id = accepted.json()["run_id"]
    run_path = root / run_id / aux.FILE_NAME
    run_before = run_path.read_bytes()
    expected = aux.read_summary(run_path)
    assert expected["pdf_reference"]["observation"] == summary
    assert expected["call_count"] == 0 and expected["observed_cost_usd"] is None
    for suffix in ("", "/progress"):
        response = client.get(f"/api/runs/{run_id}{suffix}").json()
        assert response["auxiliary_usage"] == expected
        assert response["usage"] is None and response["terminal"] is None
    assert run_path.read_bytes() == run_before and launch.call_count == 1
    denied = client.post("/api/runs", headers=headers(code="offline-owner-b"),
                         json={"topic": "Offline study", "paper_id": body["paper_id"]})
    assert denied.status_code == 404 and launch.call_count == 1


def test_failed_pdf_keeps_usage_after_paper_discard(paid_api, monkeypatch):
    """Failed model parsing must not erase its expense with the raw upload."""
    client, _, _ = paid_api
    sdk(monkeypatch, body="NOT_JSON_PRIVATE")
    auth = headers()
    initial = client.post("/api/papers", headers=auth, files={"file": ("x.pdf", b"%PDF-offline")})
    assert initial.status_code == 422
    result = client.get("/api/receipts", headers=auth).json()
    assert result["state"] == "failed" and result["auxiliary_usage"]["observed_tokens"] == 12
    assert initial.json()["auxiliary_usage"] == result["auxiliary_usage"]
    assert isinstance(initial.json()["detail"], str) and "PRIVATE" not in initial.text
    assert not papers.paper_dir(result["resource_id"]).exists()
    assert pdf_usage.paper_path(result["resource_id"]).is_file()


def test_failed_pdf_replay_preserves_usage_without_dispatch_or_writes(paid_api, monkeypatch):
    """The failed-receipt early return dropped known charges only on POST replay."""
    client, launch, root = paid_api
    call = MagicMock(return_value="NOT_JSON_PRIVATE")
    sdk(monkeypatch, call=call)
    auth = headers()
    files = {"file": ("x.pdf", b"%PDF-offline")}
    initial = client.post("/api/papers", headers=auth, files=files)
    assert initial.status_code == 422
    summary = initial.json()["auxiliary_usage"]
    assert summary["observed_tokens"] == 12 and summary["call_count"] == 1
    receipt = client.get("/api/receipts", headers=auth).json()
    assert receipt["state"] == "failed" and receipt["auxiliary_usage"] == summary
    paths = [pdf_usage.paper_path(receipt["resource_id"]), root / ".paid-receipts.sqlite3"]
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
    save = MagicMock(side_effect=AssertionError("Replay must not publish usage"))
    finish = MagicMock(side_effect=AssertionError("Replay must not finalize a receipt"))
    monkeypatch.setattr(aux.Collector, "_save", save)
    monkeypatch.setattr(receipts.Ticket, "finish", finish)
    observe = MagicMock(wraps=pdf_usage.paper_summary)
    monkeypatch.setattr(pdf_usage, "paper_summary", observe)
    for _ in range(2):
        replay = client.post("/api/papers", headers=auth, files=files)
        assert replay.status_code == 422
        assert replay.headers["Idempotency-Replayed"] == "true"
        assert replay.headers["Cache-Control"] == "no-store"
        assert "X-Error-Code" not in replay.headers
        assert replay.json()["detail"] == receipt["response"]["detail"]
        assert replay.json()["error_code"] is None
        assert replay.json()["auxiliary_usage"] == summary
        observed = client.get("/api/receipts", headers=auth)
        assert observed.status_code == 200 and observed.headers["Cache-Control"] == "no-store"
        assert observed.json()["response"] == replay.json()
        assert observed.json()["auxiliary_usage"] == summary
        assert "PRIVATE" not in replay.text + observed.text
    observe.reset_mock()
    wrong_owner = headers(auth["Idempotency-Key"], code="offline-owner-b")
    for denied in (client.post("/api/papers", headers=wrong_owner, files=files),
                   client.get("/api/receipts", headers=wrong_owner)):
        assert denied.status_code == 404
        assert "auxiliary_usage" not in denied.json()
    observe.assert_not_called()
    save.assert_not_called()
    finish.assert_not_called()
    call.assert_called_once()
    launch.assert_not_called()
    assert sum(runs._daily_counts.values()) == 1
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths} == before
    assert not papers.paper_dir(receipt["resource_id"]).exists()


@pytest.mark.parametrize("active,ledger_expired,temp_expired,removed", [
    (False, False, False, 0),
    (False, True, True, 2),
    (True, True, True, 0),
    (False, True, False, 1),
    (False, False, True, 1),
])
def test_prune_failed_pdf_publication_respects_age_and_active_owner(
    paid_api, monkeypatch, active, ledger_expired, temp_expired, removed,
):
    """Failed atomic publication left a tmp orphan, or exposed an active writer to cleanup."""
    paper_id = "paper-" + "a" * 32
    path = pdf_usage.paper_path(paper_id)
    temporary = path.with_suffix(".json.tmp")
    previous = aux.Collector(path)
    previous.finish()
    original_bytes = path.read_bytes()
    replace = aux.os.replace

    def fail_publication(source, target):
        if target == path:
            raise OSError("offline atomic publication failure")
        return replace(source, target)

    def check_prune():
        assert pdf_usage.RETENTION_SECONDS == 48 * 3600
        assert path.read_bytes() == original_bytes and temporary.is_file()
        if ledger_expired:
            os.utime(path, (1, 1))
        if temp_expired:
            os.utime(temporary, (1, 1))
        before = {entry: entry.read_bytes() for entry in (path, temporary)}
        assert pdf_usage.prune() == removed
        for entry, expired in ((path, ledger_expired), (temporary, temp_expired)):
            assert entry.exists() is (active or not expired)
            if entry.exists():
                assert entry.read_bytes() == before[entry]
        assert pdf_usage.prune() == 0

    with monkeypatch.context() as fault:
        fault.setattr(aux.os, "replace", fail_publication)
        with pdf_usage.paper_operation(paper_id) as collector:
            seq = collector.begin("pdf_extraction", "llm_invocation", "qwen3.5-plus")
            collector.settle(seq, aux.parse_usage(SDK_USAGE, "qwen3.5-plus", sdk=True), "returned")
            assert collector.summary()["record_state"] == "write_failed"
            assert collector.summary()["observed_tokens"] == 12
            if active:
                assert pdf_usage._ACTIVE[path] is collector
                check_prune()
        assert path not in pdf_usage._ACTIVE
    if not active:
        check_prune()


def test_prune_preserves_foreign_names_and_symlink_entries(paid_api, monkeypatch):
    """Only exact ledger/tmp names are removable, and symlink metadata must veto deletion."""
    root = pdf_usage.paper_path("paper-" + "a" * 32).parent
    root.mkdir()
    names = ["foreign.json.tmp", "paper-" + "a" * 31 + ".json.tmp",
             "paper-" + "A" * 32 + ".json.tmp", "paper-" + "b" * 32 + ".json.tmp.bak",
             "paper-" + "c" * 32 + ".json.tmp.tmp", "paper-" + "d" * 32 + ".tmp"]
    links = {root / ("paper-" + "e" * 32 + suffix) for suffix in (".json", ".json.tmp")}
    protected = {root / name for name in names} | links
    for path in protected:
        path.write_bytes(b"untouched")
        os.utime(path, (1, 1))
    directory = root / ("paper-" + "f" * 32 + ".json.tmp")
    directory.mkdir()
    os.utime(directory, (1, 1))
    # Model the symlink metadata boundary on Windows without requiring an OS
    # symlink-creation privilege; the real file entries must remain unchanged.
    is_symlink = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path in links or is_symlink(path))
    assert pdf_usage.prune() == 0
    assert all(path.read_bytes() == b"untouched" for path in protected)
    assert directory.is_dir()


@pytest.mark.parametrize("queued", [False, True])
def test_cancelled_pdf_waiter_settles_once_in_actual_thread(paid_api, monkeypatch, queued):
    """Waiter cancellation cannot skip accounting; queued abandonment cannot spend."""
    client, _, root = paid_api
    auth = headers()
    ticket, _ = receipts.claim(root, auth["Idempotency-Key"], access.owner_id("offline-owner-a"), "paper", {})
    paper_id, path = papers.save_upload(b"%PDF-offline")
    release = threading.Event()

    async def exercise():
        loop = asyncio.get_running_loop()
        entered, gate = asyncio.Event(), asyncio.Event()
        original = asyncio.to_thread

        def call(_messages):
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(STEP)
            return json.dumps(contribution().model_dump())

        sdk(monkeypatch, call=call)

        async def controlled(fn, *args, **kwargs):
            if queued:
                await gate.wait()
            return await original(fn, *args, **kwargs)

        monkeypatch.setattr(asyncio, "to_thread", controlled)
        with receipts.activate(ticket):
            waiter = asyncio.create_task(main._process_uploaded_paper(paper_id, str(path),
                owner=None, byok=False, llm_provider=None, llm_api_key=None))
        try:
            if queued:
                while not main._paper_jobs:
                    await asyncio.sleep(0)
            else:
                assert await asyncio.wait_for(entered.wait(), STEP)
            assert not waiter.done()
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiter
        finally:
            gate.set()
            release.set()
        await asyncio.gather(*list(main._paper_jobs), return_exceptions=True)
        assert not main._paper_jobs

    asyncio.run(exercise())
    result = client.get("/api/receipts", headers=auth).json()
    observed = pdf_usage.paper_summary(paper_id)
    assert observed["call_count"] == (0 if queued else 1)
    assert observed["observed_tokens"] == (0 if queued else 12)
    assert observed["coverage"] == ("complete" if queued else "partial")
    assert result["state"] == ("failed" if queued else "accepted")
    assert sum(runs._daily_counts.values()) == (0 if queued else 1)
    assert not path.exists()


def test_two_pdf_threads_do_not_mix_accounts_or_prune_active_records(paid_api, monkeypatch):
    """Each actual thread owns a ContextVar and its SDK, not a shared listener."""
    sdk(monkeypatch)
    barrier = threading.Barrier(2)
    original = main.extract_paper_contribution

    def extract(*args, **kwargs):
        barrier.wait(STEP)
        collector = aux.current()
        os.utime(collector.path, (1, 1))
        assert pdf_usage.prune() == 0
        return original(*args, **kwargs)

    monkeypatch.setattr(main, "extract_paper_contribution", extract)
    ids = [papers.save_upload(b"%PDF-offline") for _ in range(2)]

    async def exercise():
        await asyncio.gather(*(main._process_uploaded_paper(pid, str(path), owner=None, byok=False,
            llm_provider=None, llm_api_key=None) for pid, path in ids))

    asyncio.run(exercise())
    for pid, _ in ids:
        summary = pdf_usage.paper_summary(pid)
        assert summary["call_count"] == 1 and summary["observed_tokens"] == 12
    assert aux.current() is None


def test_project_sdk_retries_still_form_one_incomplete_invocation(tmp_path, monkeypatch):
    """Successful SDK counters cannot prove all underlying retries were measured."""
    attempts = []

    def call(_messages):
        attempts.append(1)
        if len(attempts) < 3:
            raise ConnectionError("offline transient")
        return "{}"

    sdk(monkeypatch, call=call)
    factory = llm_config.create_llm
    monkeypatch.setattr(llm_config, "create_llm", lambda **kw: llm_config._wrap_with_retry(factory(**kw)))
    monkeypatch.setattr(llm_config.time, "sleep", lambda _: None)
    collector = ledger(tmp_path)
    with aux.bind(collector):
        assert pdf_extractor._call_llm_json("offline") == {}
    collector.finish()
    summary = collector.summary()
    assert len(attempts) == 3 and summary["call_count"] == 1
    assert summary["provider_attempt_count"] is None and summary["coverage"] == "partial"
    assert summary["observed_tokens"] == 12 and not summary["cost_complete"]


def test_write_failure_retains_paid_result_and_is_visible(paid_api, monkeypatch):
    """An accounting failure is not permission to discard/retry the PDF result."""
    client, _, _ = paid_api
    sdk(monkeypatch)
    original = aux.os.replace

    def fail_aux(source, target):
        if "_auxiliary_usage" in str(target):
            raise OSError("SECRET_PATH")
        return original(source, target)

    monkeypatch.setattr(aux.os, "replace", fail_aux)
    auth = headers()
    first = client.post("/api/papers", headers=auth, files={"file": ("x.pdf", b"%PDF-offline")})
    assert first.status_code == 200, first.text
    summary = first.json()["auxiliary_usage"]
    assert summary["record_state"] == "write_failed" and summary["observed_tokens"] == 12
    assert not summary["cost_complete"] and "SECRET" not in first.text
    assert client.get("/api/receipts", headers=auth).json()["auxiliary_usage"] == summary
    paper_id = first.json()["paper_id"]
    reference = pdf_usage.paper_reference(paper_id)
    assert aux.project(aux.Ledger.model_validate(reference["observation"])) == summary
    reference["observation"]["calls"][0]["tokens"]["prompt_tokens"] = 999
    assert pdf_usage.paper_summary(paper_id) == summary, "Reference must not alias the fault cache"
    reference = pdf_usage.paper_reference(paper_id)
    child = aux.Collector(papers.PAPERS_ROOT.parent / "child" / aux.FILE_NAME, pdf_reference=reference)
    observed = child.summary()
    assert observed["call_count"] == 0 and observed["observed_cost_usd"] is None
    assert observed["pdf_reference"]["observation"] == summary


def test_initial_publish_failure_survives_fresh_worker_handoff(paid_api, monkeypatch):
    """Discarding the API collector lost both its sticky fault and the PDF association."""
    client, launch, root = paid_api
    from academic_agent import pipeline_worker, run_output, source_pipeline
    pc = pdf_extractor.PaperContribution.model_validate({**contribution().model_dump(),
        "core_contribution": "An offline extraction with enough technical detail for the existing source contract.",
        "delta_from_prior": "A bounded comparison against the previous offline fixture."})
    sdk(monkeypatch, body=json.dumps(pc.model_dump()))
    paper = client.post("/api/papers", headers=headers(), files={"file": ("x.pdf", b"%PDF-offline")}).json()
    original = aux.os.replace

    def fail_initial(source, target):
        if Path(target).name == aux.FILE_NAME:
            raise OSError("offline first publication")
        return original(source, target)

    with monkeypatch.context() as fault:
        fault.setattr(aux.os, "replace", fail_initial)
        accepted = client.post("/api/runs", headers=headers(), json={"topic": "Offline topic", "paper_id": paper["paper_id"]})
    assert accepted.status_code == 202, accepted.text
    args = launch.call_args.args[0]
    handoff = aux.decode_handoff(args[args.index("--auxiliary-handoff") + 1])
    assert handoff["storage_failed"] is True and handoff["calls"] == []
    path = root / accepted.json()["run_id"] / aux.FILE_NAME
    assert not path.exists()
    monkeypatch.setattr(run_output, "DEFAULT_OUTPUT_ROOT", root)
    stop = MagicMock(side_effect=RuntimeError("offline stop after the actual worker handoff"))
    monkeypatch.setattr(source_pipeline, "collect_source_collection", stop)
    monkeypatch.setattr(sys, "argv", ["worker", *args[3:]])
    with pytest.raises(SystemExit):
        pipeline_worker.main()
    stop.assert_called_once()
    result = aux.read_summary(path)
    assert result["record_state"] == "write_failed" and not result["cost_complete"]
    assert result["pdf_reference"]["observation"] == paper["auxiliary_usage"]
    assert result["call_count"] == 0 and result["observed_cost_usd"] is None


@pytest.mark.parametrize("mode", ["snapshot", "fallback", "error"])
def test_pdf_response_does_not_block_loop_on_actual_prune_lock(paid_api, monkeypatch, mode):
    """An eager getattr default blocked health behind the real private-store lock."""
    _, _, root = paid_api
    sdk(monkeypatch, body="invalid" if mode == "error" else None)
    process = main._process_uploaded_paper
    iterate = Path.iterdir
    release, probe_go = threading.Event(), threading.Event()
    errors, threads = [], []

    async def exercise():
        loop = asyncio.get_running_loop()
        entered = asyncio.Event()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
            def held_iteration(path):
                if path == root / "_auxiliary_usage":
                    loop.call_soon_threadsafe(entered.set)
                    assert release.wait(STEP), "prune observer did not release the real lock"
                return iterate(path)

            monkeypatch.setattr(Path, "iterdir", held_iteration)

            def observer():
                try:
                    assert probe_go.wait(STEP)
                    response = asyncio.run_coroutine_threadsafe(client.get("/health"), loop).result(timeout=STEP)
                    assert response.status_code == 200
                except Exception as exc:  # noqa: BLE001 - transfer observer failures to pytest's thread
                    errors.append(exc)
                finally:
                    release.set()

            async def hold_before_delivery():
                pruner = threading.Thread(target=pdf_usage.prune)
                observer_thread = threading.Thread(target=observer)
                threads.extend((pruner, observer_thread))
                pruner.start()
                observer_thread.start()
                assert await asyncio.wait_for(entered.wait(), STEP)
                probe_go.set()  # Current task reaches delivery before the queued health probe.

            async def wrapped(*args, **kwargs):
                try:
                    result = await process(*args, **kwargs)
                except ValueError:
                    await hold_before_delivery()
                    raise
                if mode == "fallback":
                    del result._auxiliary_usage
                await hold_before_delivery()
                return result

            monkeypatch.setattr(main, "_process_uploaded_paper", wrapped)
            try:
                response = await client.post("/api/papers", headers=headers(), files={"file": ("x.pdf", b"%PDF-offline")})
                assert response.status_code == (422 if mode == "error" else 200), response.text
                assert response.json()["auxiliary_usage"]["observed_tokens"] == 12
            finally:
                release.set()
                for thread in threads:
                    await asyncio.to_thread(thread.join, STEP)
            assert not errors, f"Health was blocked by PDF delivery: {errors!r}"

    asyncio.run(exercise())


def test_recovery_copies_only_pdf_reference_before_parent_deletion(paid_api):
    """A child must not import old planning charges or dereference a deleted parent."""
    client, _, root = paid_api
    parent = runs.create_run_id()
    directory = root / parent
    directory.mkdir()
    spec = RunSpec(topic="Offline recovery topic")
    spec.save(directory)
    (directory / "status.json").write_text(json.dumps({"done": True, "error": "offline failure"}))
    (directory / ".owner").write_text(access.owner_id("offline-owner-a"))
    CheckpointStore(directory).commit(retrieval_identity(spec, revision="offline", as_of_date=date(2026, 9, 10)),
                                      json.dumps({"topic": spec.topic}), output_format="json")
    pdf = aux.Collector(root / "pdf-ledger.json")
    p = pdf.begin("pdf_extraction", "llm_invocation", "qwen3.5-plus")
    pdf.settle(p, aux.parse_usage(SDK_USAGE, "qwen3.5-plus", sdk=True), "returned")
    pdf.finish()
    reference = aux.pdf_reference(pdf.path)
    source = aux.Collector(directory / aux.FILE_NAME, pdf_reference=reference)
    s = source.begin("search_planning", "http_attempt", "qwen3.5-plus")
    source.settle(s, aux.parse_usage(USAGE, "qwen3.5-plus"), "returned")
    source.finish()
    response = client.post(f"/api/runs/{parent}/resume", headers=headers(), json={})
    assert response.status_code == 202, response.text
    child = root / response.json()["run_id"] / aux.FILE_NAME
    assert aux.read_ledger(child).pdf_reference == reference
    assert aux.read_summary(child)["call_count"] == 0
    # Use the production deletion path rather than leaving an accidental live
    # dependency on a parent file in the test fixture.
    runs.delete_run(parent)
    assert aux.read_ledger(child).pdf_reference == reference


def test_shipped_js_preserves_unknown_and_observed_numbers(tmp_path):
    """Unknown -> 0 must fail at the shipped renderer, not a Python imitation."""
    node = shutil.which("node")
    assert node, "Node required for the auxiliary usage seam"
    root = Path(__file__).resolve().parents[1]
    source = (root / "web/static/js/run.js").read_text(encoding="utf-8")
    source = source.replace('import * as api from "./api.js";', 'const api = {};')
    (tmp_path / "run.mjs").write_text(source, encoding="utf-8")
    shutil.copyfile(root / "web/static/js/i18n.js", tmp_path / "i18n.js")
    script = '''globalThis.localStorage = {getItem: () => null};
const {auxiliarySummary} = await import('./run.mjs');
const result = JSON.parse(process.argv[1]).map(auxiliarySummary);
console.log(JSON.stringify(result));'''
    collector = ledger(tmp_path)
    seq = collector.begin("translation", "http_attempt", "qwen3.5-plus")
    collector.settle(seq, None, "call_failed")
    collector.finish()
    values = [None, aux.unavailable("unreadable"), collector.summary(),
              {**collector.summary(), "observed_cost_usd": True}]
    result = subprocess.run([node, "--input-type=module", "-e", script, json.dumps(values)],
                            cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    rendered = json.loads(result.stdout)
    assert "not recorded" in rendered[0] and "unreadable" in rendered[1]
    assert "Incomplete" in rendered[2] and "$" not in rendered[2]
    assert "unreadable" in rendered[3]


def test_actual_run_header_keeps_auxiliary_scope_separate_and_clears_stale_dom(paid_api, monkeypatch):
    """Both run HTTP projections must reach the shipped header without inventing a combined bill."""
    node = shutil.which("node")
    assert node, "Node required for the run-header seam"
    client, launch, root = paid_api
    # Build the reference through the real PDF admission path.  Starting a
    # paper-less run creates its empty ledger before this fixture can bind a
    # reference, which is deliberately not retrofitted by Collector.
    sdk(monkeypatch)
    paper = client.post("/api/papers", headers=headers(), files={"file": ("header.pdf", b"%PDF-offline")})
    assert paper.status_code == 200, paper.text
    accepted = client.post("/api/runs", headers=headers(),
                           json={"topic": "Synthetic header run", "paper_id": paper.json()["paper_id"]})
    assert accepted.status_code == 202, accepted.text
    run_id = accepted.json()["run_id"]
    directory = root / run_id

    collector = aux.Collector(directory / aux.FILE_NAME)
    sequence = collector.begin("translation", "http_attempt", "qwen3.5-plus")
    collector.settle(sequence, aux.parse_usage(USAGE, "qwen3.5-plus"), "returned")
    collector.finish()
    (directory / "status.json").write_text(json.dumps({
        "topic": "Synthetic header run", "stage": "review",
        "usage": {"total_tokens": 999, "cost_usd": 0.1234, "cost_complete": True,
                  "accounting_scope": "crew_nodes", "agents": []},
        "usage_accounting": {"state": "unavailable", "run_complete": False,
                             "in_flight_request_may_have_spent": True},
    }), encoding="utf-8")

    current = client.get(f"/api/runs/{run_id}")
    assert current.status_code == 200, current.text
    known = current.json()
    assert known["auxiliary_usage"]["observed_tokens"] == 12
    assert known["auxiliary_usage"]["observed_cost_usd"] > 0
    assert known["auxiliary_usage"]["pdf_reference"]["relation"] == "reference_only"
    reference = known["auxiliary_usage"]["pdf_reference"]["observation"]
    assert reference == paper.json()["auxiliary_usage"]
    assert reference["observed_tokens"] == 12 and reference["observed_cost_usd"] > 0
    assert known["auxiliary_usage"]["call_count"] == 1
    assert known["auxiliary_usage"]["observed_cost_usd"] == known["auxiliary_usage"]["calls"][0]["observed_cost_usd"]
    assert known["usage_accounting"]["state"] == "unavailable"

    (directory / aux.FILE_NAME).unlink()
    progress = client.get(f"/api/runs/{run_id}/progress")
    assert progress.status_code == 200, progress.text
    missing = progress.json()
    assert missing["auxiliary_usage"]["record_state"] == "not_recorded"

    broken_bytes = b'{"schema_version":'
    (directory / aux.FILE_NAME).write_bytes(broken_bytes)
    corrupt = client.get(f"/api/runs/{run_id}")
    assert corrupt.status_code == 200, corrupt.text
    unreadable = corrupt.json()
    assert unreadable["auxiliary_usage"]["record_state"] == "unreadable"
    assert (directory / aux.FILE_NAME).read_bytes() == broken_bytes

    script = Path(__file__).with_name("js") / "run_auxiliary_header_contract.mjs"
    # Do not unpatch subprocess.Popen globally: even while Node runs, a backend
    # worker must still hit paid_api's mock. This direct handle cannot run it.
    assert runs.subprocess.Popen is launch

    def run_header(fault):
        command = [node, str(script), json.dumps(known), json.dumps(missing), json.dumps(unreadable), fault]
        # Popen.__exit__ waits without a deadline. Keep both ordinary execution
        # and timeout cleanup bounded instead of using its context manager.
        process = _NODE_POPEN(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, encoding="utf-8")
        try:
            stdout, stderr = process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                pytest.fail("Run-header Node harness did not finish draining within five seconds after kill")
            pytest.fail("Run-header Node harness timed out:\n" + stdout + stderr)
        return process.returncode, stdout, stderr

    returncode, stdout, stderr = run_header("none")
    assert returncode == 0, stdout + stderr
    assert "PASS run_auxiliary_header" in stdout
    # The same CLI must fail for the intended lost-DOM assertion, not a missing
    # browser stub, a ReferenceError, or an unrelated startup failure.
    returncode, stdout, stderr = run_header("drop_auxiliary")
    assert returncode != 0
    assert "AssertionError [ERR_ASSERTION]: run header lost auxiliary observation" in stderr, stderr
    assert "PASS run_auxiliary_header" not in stdout
    assert runs.subprocess.Popen is launch
    launch.assert_called_once()


@pytest.mark.parametrize("mode", ["known", "missing", "corrupt", "failed"])
def test_actual_attachment_and_receipt_dom_paths(mode):
    """The real app/fetch paths must paint usage, including failed initial PDFs."""
    node = shutil.which("node")
    assert node, "Node required for the DOM seam"
    script = Path(__file__).with_name("js") / "composer_contract.mjs"
    result = subprocess.run([node, str(script), "auxiliary_attachment_and_receipt", mode],
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS auxiliary_attachment_and_receipt" in result.stdout


@pytest.mark.allow_llm
@pytest.mark.parametrize("sidecar_failure", [False, True])
def test_actual_resumed_worker_records_new_pdf_domain_translation(tmp_path, monkeypatch, sidecar_failure):
    """Retrieval reuse does not skip the worker's real pre-retrieval PDF translation."""
    from academic_agent import checkpoint_runtime, crew, pipeline_worker, run_output, source_pipeline
    from academic_agent.source_pipeline import SourceCollection

    monkeypatch.setattr(run_output, "DEFAULT_OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(checkpoint_runtime, "pipeline_revision", lambda: "offline-revision")
    parent, child = "20260927T000000Z-aaaaaaaa", "20260927T000000Z-bbbbbbbb"
    pc = pdf_extractor.PaperContribution.model_validate({**contribution().model_dump(), "application_domain": "电池储能",
        "core_contribution": "An offline battery contribution with a sufficiently detailed technical summary.",
        "delta_from_prior": "The fixture compares a bounded material change with earlier cells."})
    spec = RunSpec(topic="offline topic", paper_contribution=pc.model_dump())
    directory = tmp_path / child
    directory.mkdir()
    spec_path = spec.save(directory)
    source = SourceCollection(topic="offline topic", collected_at=datetime.now(UTC),
        academic_sources=[pdf_extractor.paper_to_evidence_source(pc)],
        academic_queries=["offline"], patent_queries=["offline"], market_queries=["offline"])
    snapshot = directory / ".resume-source"
    CheckpointStore(snapshot).commit(retrieval_identity(spec, revision="offline-revision", as_of_date=datetime.now(UTC).date()),
                                      source.model_dump_json(), output_format="json")
    no_retrieval = MagicMock(side_effect=AssertionError("restored retrieval repeated"))
    monkeypatch.setattr(source_pipeline, "collect_source_collection", no_retrieval)
    # Stop at Crew construction, after reused source delivery and translation.
    monkeypatch.setattr(crew, "AcademicAgent", MagicMock(side_effect=RuntimeError("offline stop before Crew")))
    http(monkeypatch, [{"usage": USAGE, "choices": [{"message": {"content": "batteries"}}]}])
    if sidecar_failure:
        replace = aux.os.replace

        def fail_settlement(source, target):
            if Path(target).name == aux.FILE_NAME:
                candidate = json.loads(Path(source).read_text(encoding="utf-8"))
                if any(call["state"] == "settled" for call in candidate["calls"]):
                    raise OSError("offline sidecar settlement failure")
            return replace(source, target)

        monkeypatch.setattr(aux.os, "replace", fail_settlement)
    monkeypatch.setattr(sys, "argv", ["worker", child, spec.topic, "--run-spec", str(spec_path), "--resume-from", parent])
    with pytest.raises(SystemExit):
        pipeline_worker.main()
    no_retrieval.assert_not_called()
    status = json.loads((directory / "status.json").read_text(encoding="utf-8"))
    summary = aux.read_summary(directory / aux.FILE_NAME, fallback=status["auxiliary_usage_snapshot"])
    assert summary["observed_tokens"] == 12 and [c["stage"] for c in summary["calls"]] == ["translation"]
    if sidecar_failure:
        assert summary["record_state"] == "write_failed" and not summary["cost_complete"]
        assert aux.read_ledger(directory / aux.FILE_NAME).calls[0].state == "pending"
    before = (directory / aux.FILE_NAME).read_bytes()
    with TestClient(main.app) as client:
        for suffix in ("", "/progress", "", "/progress"):
            observed = client.get(f"/api/runs/{child}{suffix}").json()
            assert observed["auxiliary_usage"] == summary
    assert (directory / aux.FILE_NAME).read_bytes() == before
    assert aux.current() is None
    terminal = json.loads((directory / "terminal.json").read_text(encoding="utf-8"))
    assert terminal["schema_version"] == 1 and "auxiliary_usage" not in terminal and terminal["usage"] is None
    from academic_agent.run_terminal import TerminalRecord
    TerminalRecord.model_validate(terminal)  # Old strict extra-forbid reader remains usable.
