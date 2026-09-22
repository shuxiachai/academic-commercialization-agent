"""Fixed fake-HTTP RU rehearsal in its own subprocess, never a native runner.

No key, endpoint, callback or live option is exposed. Temporary owner markers,
copies and journals do not modify originals. Detailed output is PRIVATE. The
trusted-code guards are not a hostile-code sandbox or a provider attestation.
"""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

from academic_agent import saved_source_real_eval as prep
from academic_agent.report_evidence_source_locator_comparison import (
    ComparisonUnavailable, _title_only_row, _validate_state,
)

MAX_RESULT_BYTES = 512 * 1024
_FAKE_KEY = "sk-offline-ru-fixed-fake-only"
_CODE = "offline-ru-synthetic-owner"


def _environment():
    # Do not copy the environment wholesale, discover keys, or load dotenv.
    env = {name: os.environ[name] for name in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
           if name in os.environ}
    return {**env, "PYTHONPATH": os.pathsep.join((str(prep.ROOT / "src"), str(prep.ROOT))),
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}


def _assets():
    return {name: prep._sha((prep.ROOT / name).read_bytes()) for name in prep.OBSERVER_PATHS}


def _run_node(payload, cases):
    """Same existing observer, but no old fixed fixture, grouping or live gates."""
    node = shutil.which("node")
    if node is None:
        raise ComparisonUnavailable("node_unavailable")
    value = {"root": str(prep.ROOT), "payload": payload, "report": "",
             "actions": [action for case in cases for action in
                         ({"search": case["question"]}, {"search": case["keyword_query"]})]}
    result = subprocess.run([node, str(prep.ROOT / prep.OBSERVER_PATHS[0])], input=prep._dump(value),
                            capture_output=True, timeout=30, check=True, env=_environment())
    prep._require(len(result.stdout) <= MAX_RESULT_BYTES and not result.stderr)
    return json.loads(result.stdout)


def _baseline(packet):
    """Observe literal and assisted queries separately; draft overlap is not accuracy."""
    inputs = prep._inputs(packet)
    cases = prep._json(inputs["questions"], "questions")["cases"]
    refs = prep._json(inputs["references"], "references")["cases"]
    before = after = None
    results = []
    try:
        before = _assets()
        observations = {}
        for doc_id in ("D1", "D2"):
            document = packet["prepared"]["documents"][doc_id]
            # Use actual groups, not the old public fixture's fixed 4/8/8 split.
            payload = {f"{group}_sources": [{"source_id": s["source_id"], "title": s["title"]}
                       for s in document["snapshot"]["sources"] if s["group"] == group]
                       for group in prep.GROUPS}
            selected = [case for case in cases if case["doc_id"] == doc_id]
            observed = _run_node(payload, selected)
            expected = {row["source_id"]: _title_only_row(row) for row in document["catalog"]["entries"]}
            prep._require(type(observed) is dict and len(observed.get("states", [])) == 5
                          and observed.get("storage_writes") == [] and observed.get("logs") == []
                          and observed.get("requests") == [{"runId": "fixture", "artifact": "report"},
                                                           {"runId": "fixture", "artifact": "sources"}])
            prep._require(_validate_state(observed["states"][0], "", expected, "initial") == list(expected))
            for index, case in enumerate(selected):
                observations[case["case_id"]] = [
                    _validate_state(observed["states"][1 + 2 * index + lane], case[key], expected, "query")
                    for lane, key in enumerate(("question", "keyword_query"))]
        after = _assets()
        prep._require(after == before)
        for case, ref in zip(cases, refs, strict=True):
            lanes = {}
            for key, hits in zip(("question", "keyword_query"), observations[case["case_id"]], strict=True):
                accepted = ref["acceptable_source_ids"]
                overlap = [source_id for source_id in hits if source_id in accepted]
                lanes[key] = {"query": case[key], "candidate_ids": hits, "candidate_count": len(hits),
                              "ambiguous": len(hits) > 1, "draft_intersection": overlap,
                              "draft_coverage": len(overlap) / len(accepted) if accepted else None,
                              "draft_no_fit_match": not hits if not accepted else None}
            results.append({"case_id": case["case_id"], "state": "available", **lanes})
        state = "available"
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError, ComparisonUnavailable):
        state = "not_available"
        results = [{"case_id": case_id, "state": "not_available", "question": None, "keyword_query": None}
                   for case_id in prep.CASE_IDS]
    return {"state": state, "cases": results, "asset_hashes_before": before, "asset_hashes_after": after,
            "reference_provenance": "AI_authored_draft", "blind_review": "not_run",
            "scope": "grouped_full_id_title_only", "native_efficacy": "not_run",
            "user_benefit": "not_assessed", "model_advantage": "not_assessed"}


class _Guard:
    """Keep failed checks even when the real adapter catches AssertionError."""

    def __init__(self):
        self.failures = []
        self.requests = []
        self.expected_wire = None
        self.choice = None
        self.usage = None

    def check(self, condition, reason):
        if not condition:
            self.failures.append(reason)
            raise AssertionError("Offline rehearsal guard failed.")

    def deny(self, *_args, **_kwargs):
        self.check(False, "network_denied")

    def dispatch(self, request):
        import httpx
        from academic_agent.report_evidence_qwen_canary import ENDPOINT, MODEL
        self.requests.append(bytes(request.content))
        self.check(request.method == "POST" and str(request.url) == ENDPOINT
                   and request.headers.get("authorization") == "Bearer " + _FAKE_KEY, "http_boundary")
        self.check(request.content == self.expected_wire, "wire_mismatch")
        message = {"role": "assistant", "content": '{"action":"decline"}'} if self.choice is None else {
            "role": "assistant", "content": None, "tool_calls": [{"id": "ru-script", "type": "function",
            "function": {"name": "read_source", "arguments": json.dumps({"source_id": self.choice})}}]}
        return httpx.Response(200, stream=httpx.ByteStream(prep._dump({
            "model": MODEL, "usage": self.usage,
            "choices": [{"index": 0, "message": message,
                         "finish_reason": "stop" if self.choice is None else "tool_calls"}]})))


def _install_guards(stack, guard):
    import httpx
    real_client = httpx.AsyncClient
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def local_only(original):
        def connect(sock, address):
            # Windows asyncio may need a loopback socketpair. No external
            # destination is permitted; TestClient itself is in-process ASGI.
            guard.check(isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"), "network_denied")
            return original(sock, address)
        return connect

    def transport(**kwargs):
        guard.check(kwargs == {"retries": 0, "verify": True, "trust_env": False}, "transport_options")
        return httpx.MockTransport(guard.dispatch)

    def client(**kwargs):
        guard.check(type(kwargs.get("transport")) is httpx.MockTransport
                    and kwargs.get("trust_env") is False and kwargs.get("follow_redirects") is False,
                    "mock_transport_missing")
        return real_client(**kwargs)

    for target, name, value in (
        (socket, "create_connection", guard.deny), (socket, "getaddrinfo", guard.deny),
        (socket.socket, "connect", local_only(real_connect)),
        (socket.socket, "connect_ex", local_only(real_connect_ex)), (socket.socket, "sendto", guard.deny),
        (httpx.HTTPTransport, "handle_request", guard.deny),
        (httpx.AsyncHTTPTransport, "handle_async_request", guard.deny),
        (httpx, "AsyncHTTPTransport", transport), (httpx, "AsyncClient", client),
    ):
        stack.enter_context(patch.object(target, name, value))


def _case(packet, case, script, index, root, guard):
    from fastapi.testclient import TestClient
    from academic_agent.saved_source_accounted_qwen import AccountedQwenSelector
    from academic_agent.saved_source_loader import SavedSourceLoader
    from academic_agent.saved_source_usage import UsageProjectionV1
    from api import access, runs, saved_source_controller
    from api.saved_source_receipt_app import MAX_RESPONSE_BYTES, _REPLY_FIELDS
    from api.saved_source_usage_app import CONTRACT, GET_PATH, POST_PATH, create_saved_source_usage_app

    doc = packet["prepared"]["documents"][case["doc_id"]]
    alias = doc["sandbox_alias"]
    loader = SavedSourceLoader(root)
    snapshot = loader(alias)
    guard.choice = script["source_id"]
    guard.usage = {"prompt_tokens": 100 + index, "completion_tokens": 20, "total_tokens": 120 + index}
    guard.expected_wire = prep._wire(doc, case["question"])
    start = len(guard.requests)
    observations = []
    original = saved_source_controller.SavedSourceController._observe

    def observe(self, *args, **kwargs):
        value = original(self, *args, **kwargs)
        observations.append(deepcopy(value))
        return value

    selector = AccountedQwenSelector(_FAKE_KEY, snapshot=snapshot, question=case["question"],
                                     ledger_dir=root / (case["case_id"] + "-native"))
    app = create_saved_source_usage_app(load_snapshot=loader, journal_root=root,
                                        accounted_selector=selector, selector_identity="offline-ru-fake-http-v1")
    key = f"v1.{int(time.time())}.{index + 1:064x}"
    headers = {"Idempotency-Key": key, "X-Access-Code": _CODE}
    with patch.object(saved_source_controller.SavedSourceController, "_observe", observe), TestClient(app) as client:
        post = client.post(POST_PATH.replace("{run_id}", alias), headers=headers, json={"question": case["question"]})
        guard.check(not guard.failures, "guard_failure_captured")
        guard.check(post.status_code == 200, "post_failed")
        first = post.json()
        guard.check(len(guard.requests) == start + 1 and runs._daily_counts.get(access.owner_id(_CODE)) == index + 1,
                    "post_dispatch_accounting")
        replay = client.get(GET_PATH, headers=headers)
        guard.check(replay.status_code == 200, "get_failed")
        second = replay.json()
        guard.check(len(guard.requests) == start + 1 and runs._daily_counts.get(access.owner_id(_CODE)) == index + 1,
                    "get_redispatch")
    guard.check(len(observations) == 2 and runs.active_paid_operation_count() == 0, "observation_or_drain")
    for response, payload, observed in zip((post, replay), (first, second), observations, strict=True):
        receipt, accounting = payload["receipt"], payload["accounting"]
        guard.check(len(response.content) <= MAX_RESPONSE_BYTES and set(payload) == {"contract", "receipt", "accounting"}
                    and payload["contract"] == CONTRACT and set(receipt) == _REPLY_FIELDS | {"receipt_key_sha256"},
                    "envelope_fields")
        guard.check(receipt == {**{k: v for k, v in observed.items() if k != "accounting"},
                                "receipt_key_sha256": prep._sha(key.encode())}
                    and accounting == observed["accounting"], "full_projection_delivery")
        guard.check(UsageProjectionV1.model_validate(accounting).model_dump(mode="json") == accounting,
                    "accounting_shape")
        guard.check(accounting["usage"] == {"status": "reported_complete", **guard.usage}
                    and accounting["publication_state"] == "sealed" and accounting["native_journal_state"] == "complete"
                    and accounting["fault_codes"] == [], "scripted_usage")
        guard.check(receipt["state"] == "completed" and receipt["delivery"] == "available", "result_unavailable")
    guard.check(first["accounting"] == second["accounting"] and first["receipt"]["result"] == second["receipt"]["result"],
                "immutable_result_accounting")
    guard.check(second["receipt"] == {**first["receipt"], "delivery_snapshot_reads": 1,
                                     "delivery_source_reads": int(guard.choice is not None)}
                and first["receipt"]["delivery_snapshot_reads"] == first["receipt"]["delivery_source_reads"] == 0,
                "delivery_read_facts")
    result = first["receipt"]["result"]
    guard.check(result["callback_entries"] == 1 and result["read_completed"] == int(guard.choice is not None), "execution_facts")
    if guard.choice is None:
        guard.check(result["state"] == "declined" and result["source"] is result["saved_text"] is None, "decline_delivery")
    else:
        saved = next(source for source in snapshot.sources if source.source_id == guard.choice)
        guard.check(result["state"] == "excerpt" and result["source"]["source_id"] == guard.choice
                    and result["saved_text"]["text"] == saved.summary
                    and result["saved_text"]["end"] == saved.stored_length, "full_text_delivery")
    # GET and TestClient shutdown can catch a guard's AssertionError too. Check
    # its durable in-memory failure record only after both paths have exited.
    guard.check(not guard.failures, "late_guard_failure_captured")
    return {"case_id": case["case_id"], "state": "passed", "post": first, "get": second,
            "wire_sha256": prep._sha(guard.requests[-1]), "wire_bytes": len(guard.requests[-1]),
            "scripted_usage": guard.usage, "intercepted_http_entries": 1, "temporary_admissions": 1}


def _child(packet):
    from contextlib import ExitStack
    prep.validate_packet(packet)
    inputs = prep._inputs(packet)
    baseline = _baseline(packet)
    scripts = prep._json(inputs["scripts"], "scripts")["cases"]
    guard = _Guard()
    rows = [{"case_id": case_id, "state": "not_run"} for case_id in prep.CASE_IDS]
    # The network guards and all global test authority live only in this child.
    with ExitStack() as stack, tempfile.TemporaryDirectory(prefix="ru-rehearsal-", dir=Path.cwd()) as directory:
        _install_guards(stack, guard)
        from api import access, runs
        root = Path(directory)
        for name in ("_registry", "_stop_claims", "_inline_paid_operations", "_daily_counts"):
            stack.enter_context(patch.object(runs, name, {}))
        for target, name, value in ((runs, "_daily_date", None), (runs, "DEFAULT_OUTPUT_ROOT", root),
                (runs, "MAX_CONCURRENT", 1), (runs, "DAILY_CAP", 4), (access, "ACCESS_CODE", _CODE),
                (access, "ACCESS_CODES", None), (access, "ADMIN_CODE", None)):
            stack.enter_context(patch.object(target, name, value))
        for doc_id, doc in packet["prepared"]["documents"].items():
            folder = root / doc["sandbox_alias"]
            folder.mkdir()
            (folder / ".owner").write_text(access.owner_id(_CODE), encoding="utf-8")
            (folder / "validated_sources.json").write_bytes(inputs["documents"][doc_id]["sources"])
        for index, (case, script) in enumerate(zip(packet["prepared"]["cases"], scripts, strict=True)):
            try:
                rows[index] = _case(packet, case, script, index, root, guard)
                guard.check(not guard.failures, "case_guard_failure_captured")
            except Exception:  # noqa: BLE001 -- private bodies/paths/foreign errors never enter the result.
                rows[index] = {"case_id": case["case_id"], "state": "failed", "reason": "rehearsal_check_failed"}
                break
        for doc_id, doc in packet["prepared"]["documents"].items():
            prep._require((root / doc["sandbox_alias"] / "validated_sources.json").read_bytes()
                          == inputs["documents"][doc_id]["sources"])
    prep.validate_packet(packet)
    return {"method": prep.METHOD, "packet_sha256": packet["packet_sha256"],
            "state": "passed" if (not guard.failures and len(guard.requests) == 4
                                   and all(row["state"] == "passed" for row in rows)
                                   and baseline["state"] == "available") else "failed",
            "cases": rows, "baseline": baseline, "guard_failures": guard.failures,
            "intercepted_http_entries": len(guard.requests), "live_authorization": False,
            "native_efficacy": "not_run", "reference_review": "not_run",
            "accounting_scope": "scripted_tokens_and_estimates_not_real_use", "external_provider_calls": 0}


def rehearse(packet: dict) -> dict:
    """Run the only fixed subprocess recipe; accept no caller execution options."""
    raw = prep.serialize_packet(packet)
    try:
        with tempfile.TemporaryDirectory(prefix="ru-child-", dir=prep.PRIVATE_ROOT) as directory:
            # Match the project's one known TestClient deprecation filter;
            # independent children do not inherit pytest.ini warning filters.
            result = subprocess.run([sys.executable, "-X", "utf8", "-W", "error::UserWarning",
                                     "-W", "ignore:Using `httpx` with `starlette.testclient` is deprecated", "-m",
                                     "academic_agent.saved_source_real_rehearsal", "--child"],
                                    input=raw, capture_output=True, cwd=directory,
                                    env=_environment(), timeout=150, check=True)
        prep._require(len(result.stdout) <= MAX_RESULT_BYTES and not result.stderr)
        report = json.loads(result.stdout)
        prep._require(report["packet_sha256"] == packet["packet_sha256"]
                      and report["live_authorization"] is False and report["native_efficacy"] == "not_run"
                      and [row["case_id"] for row in report["cases"]] == list(prep.CASE_IDS))
        # Child success is not authority to contradict its own failure record.
        # Preserve honest failed/unrun rows; reject an inconsistent aggregate.
        passed = (report["guard_failures"] == [] and report["intercepted_http_entries"] == 4
                  and all(row["state"] == "passed" for row in report["cases"])
                  and report["baseline"]["state"] == "available")
        prep._require(report["state"] == ("passed" if passed else "failed"))
        prep.validate_packet(packet)
        return report
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        raise prep.PreparationError() from None


def _main():
    # Internal stdin protocol only: no arbitrary file, key, endpoint or live flag.
    if sys.argv[1:] != ["--child"]:
        raise SystemExit(2)
    try:
        raw = sys.stdin.buffer.read(prep.MAX_PACKET_BYTES + 1)
        prep._require(len(raw) <= prep.MAX_PACKET_BYTES)
        packet = json.loads(raw)
        result = _child(packet)
        sys.stdout.buffer.write(prep._dump(result, MAX_RESULT_BYTES))
    except Exception:  # noqa: BLE001 -- internal CLI must never print private exception diagnostics.
        raise SystemExit(2) from None


if __name__ == "__main__":
    _main()
