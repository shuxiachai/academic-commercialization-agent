"""RUQ synthetic-only gates; no historical packet, title, hash or real key reads."""

from contextlib import ExitStack
from copy import deepcopy
from decimal import Decimal
import ast
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit

import httpx
import pytest

from academic_agent import saved_source_real_eval as prep
from academic_agent import saved_source_real_qwen_canary as pilot
from academic_agent import saved_source_real_rehearsal as rehearsal
from test_saved_source_real_eval import synthetic_inputs


HEAD = "b" * 40
OLD_HEAD = "a" * 40
FAKE_KEY = "synthetic-ruq-not-a-provider-key"


def dump(value):
    return prep._dump(value)


def rehash(packet):
    packet.pop("packet_sha256", None)
    packet["packet_sha256"] = prep._sha(dump(packet))
    return packet


def make_bundle(origin, current):
    view = prep.review_view(current)
    raw_view = json.dumps(view, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    prompt = b"SYNTHETIC RUBRIC ONLY\nDATA:\n" + raw_view
    labels = (["A3"], ["A1", "A2"], ["A3"], [])
    rows = []
    for case, ids in zip(view["cases"], labels, strict=True):
        titles = {row["source_id"]: row["title"] for row in case["catalog"]}
        rows.append({"case_id": case["case_id"], "doc_id": case["doc_id"],
            "disposition": "candidate_set" if ids else "no_catalog_fit", "acceptable_source_ids": ids,
            "support_status": "supported", "rationale": "Synthetic title-only rationale, not source truth.",
            "title_quotes": [{"source_id": item, "quote": titles[item]} for item in ids],
            "near_misses": [{"source_id": "M1", "reason": "Synthetic alternative."}],
            "limitations": ["Synthetic engineering control, not an actual judge."]})
    review = {"review_kind": "LLM_title_location_reference_review", "external_sources_checked": False,
              "cases": rows, "overall_limitations": ["Synthetic only; not an actual LLM judgment."]}
    files = {"blind-review-view.json": raw_view, "review-instructions.txt": prompt,
             "reviewer-output.json": dump(review)}
    sidecar = {
        "schema_version": "ru_reference_review_sidecar_v1", "status": "completed_with_limits",
        "completed_at_utc": "2026-09-22T08:56:11Z", "origin_git_head": origin["code_identity"]["git_head"],
        "origin_packet_file_sha256": prep._sha(dump(origin)), "blind_view_sha256": prep._sha(raw_view),
        "prompt_file_sha256": prep._sha(prompt), "submitted_prompt_utf8_sha256": prep._sha(prompt.rstrip()),
        "review_output_sha256": prep._sha(files["reviewer-output.json"]),
        "provenance": {"kind": "LLM_generated_reference_review", "channel": "Codex_subagent",
            "requested_role": "route_reviewer", "configured_model": "gpt-6-astra", "configured_reasoning_effort": "high",
            "effective_backend_metadata": None, "effective_backend_metadata_status": "unavailable",
            "agent_id": "synthetic-reviewer", "history_forked": False, "shared_project_instructions_may_be_present": True,
            "external_sources_checked": False, "tools_requested": False, "not_human_gold": True},
        "blinding": {"provided": ["frozen_rubric", "case_id", "document_alias", "question", "complete_visible_source_id_title_catalog"],
            "hidden": ["draft_references", "scripted_selections", "assisted_keywords", "keyword_baseline_outcomes",
                       "saved_text", "full_reports", "run_metadata", "previous_reviews"],
            "comparison_performed": "after_judgment_returned"},
        "mechanical_validation": {"case_order_and_document_match": True, "candidate_ids_exist": True,
            "duplicate_candidate_ids": False, "title_quotes_checked": 4, "title_quotes_exact_matches": 4, "near_miss_ids_exist": True},
        "draft_comparison": {"exact_set_agreement": 4, "cases": 4, "candidate_counts": [1, 2, 1, 0], "is_accuracy_estimate": False},
        "state_boundaries": {"original_packet_modified": False, "original_reference_review_field": "not_run",
            "native_efficacy": "not_run", "production_activation": False, "project_qwen_api_calls": 0,
            "project_model_key_reads": 0, "codex_review_usage": "not_observed_as_project_API_spend"},
        "limitations": ["Synthetic shape only; not actual model provenance or reference truth."],
    }
    files["review-provenance.json"] = dump(sidecar)
    return files


@pytest.fixture
def context(tmp_path, monkeypatch):
    identity = {"git_head": HEAD, "working_file_sha256": {"synthetic.py": "c" * 64}}
    monkeypatch.setattr(prep, "code_identity", lambda: deepcopy(identity))
    packet = prep.build_packet(**synthetic_inputs())
    origin = deepcopy(packet)
    origin["code_identity"]["git_head"] = OLD_HEAD
    rehash(origin)
    files = make_bundle(origin, packet)
    old_sha = prep._sha(dump(origin))
    source_identity = {"commit": HEAD, "working_file_sha256": identity["working_file_sha256"], "configuration": pilot.configuration()}
    prepared = {"identity": source_identity, "origin_packet_file_sha256": old_sha,
        "review_bundle_sha256": pilot.review_bundle_sha256(old_sha, files), "packet": packet,
        "labels": {case: ids for case, ids in zip(prep.CASE_IDS, (["A3"], ["A1", "A2"], ["A3"], []), strict=True)}}
    monkeypatch.setattr(pilot, "ROOT", tmp_path)
    monkeypatch.setattr(pilot, "verify_identity", lambda expected: deepcopy(source_identity) if expected == HEAD else None)
    for path, raw in {pilot.PACKET: dump(origin), **{name: files[Path(name).name] for name in pilot.REVIEW_FILES}}.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return {"origin": origin, "packet": packet, "files": files, "prepared": prepared, "root": tmp_path, "identity": identity}


def test_head_only_bridge_and_unchanged_old_validator(context):
    """The new bridge admits only HEAD context; old validation still rejects it."""
    before = dump(context["origin"])
    with pytest.raises(prep.PreparationError):
        prep.validate_packet(context["origin"])
    old, new = pilot.bridge_packet(before, prep._sha(before))
    assert old == context["origin"] and new == context["packet"]
    prep.validate_packet(new)
    assert dump(old) == before
    assert old["reference_review"] == old["native_efficacy"] == "not_run"
    assert pilot.preflight(HEAD, prep._sha(before), context["prepared"]["review_bundle_sha256"]) == context["prepared"]


@pytest.mark.parametrize("fault", ["raw", "prepared", "internal_sha", "config", "provenance", "dependency", "extra_identity", "newline", "wrong_file_sha", "duplicate", "oversize"])
def test_bridge_never_admits_other_drift(context, fault):
    """Canonical/raw/dependency drift cannot hide behind a newly calculated file hash."""
    old = deepcopy(context["origin"])
    if fault == "raw":
        old["raw"]["documents"]["D1"]["report"] = "c3ludGhldGlj"
    elif fault == "prepared":
        old["prepared"]["cases"][0]["question"] += " altered"
    elif fault == "internal_sha":
        old["packet_sha256"] = "f" * 64
    elif fault == "config":
        old["configuration"]["max_http_entries"] = 5
    elif fault == "provenance":
        old["reference_review"] = "completed"
    elif fault == "dependency":
        old["code_identity"]["working_file_sha256"]["synthetic.py"] = "d" * 64
        # Keep the old packet internally self-consistent: this must fail ONLY
        # because its dependency map differs from the actual current builder.
        rehash(old)
    elif fault == "extra_identity":
        old["code_identity"]["attested"] = True
    raw = dump(old)
    if fault == "newline":
        raw += b"\n"
    elif fault == "duplicate":
        raw = b'{"raw":{},"raw":{}}'
    elif fault == "oversize":
        raw = b" " * (prep.MAX_PACKET_BYTES + 1)
    with pytest.raises((pilot.PilotStopped, prep.PreparationError, ValueError)):
        pilot.bridge_packet(raw, "e" * 64 if fault == "wrong_file_sha" else prep._sha(raw))


def validate_files(context, files):
    return pilot.validate_review(context["origin"], context["packet"], context["prepared"]["origin_packet_file_sha256"],
        files, pilot.review_bundle_sha256(context["prepared"]["origin_packet_file_sha256"], files))


def test_review_sets_raw_view_prompt_and_provenance_bound(context):
    """Positive references stay set-valued; original not_run never changes."""
    assert validate_files(context, context["files"]) == context["prepared"]["labels"]
    assert len(context["prepared"]["labels"]["RU02"]) == 2
    assert context["origin"]["reference_review"] == "not_run"
    assert set(json.loads(context["files"]["blind-review-view.json"])["cases"][0]) == {"case_id", "doc_id", "question", "catalog"}


@pytest.mark.parametrize("fault", ["view", "prompt_view", "prompt_hash", "submitted_hash", "output_hash", "origin_hash", "origin_head", "status", "human", "metadata", "fork", "blinding", "boundaries", "mechanical", "comparison", "uncertain", "partial_support", "no_fit_ids", "empty_positive", "bad_id", "duplicate_id", "quote", "near_miss", "case_order", "extra_key"])
def test_review_drift_rejected_even_with_rebound_bundle(context, fault):
    """An external bundle hash never overrides content/provenance checks."""
    files = deepcopy(context["files"])
    sidecar = json.loads(files["review-provenance.json"])
    review = json.loads(files["reviewer-output.json"])
    if fault == "view":
        view = json.loads(files["blind-review-view.json"])
        view["cases"][0]["question"] += " altered"
        files["blind-review-view.json"] = dump(view)
        sidecar["blind_view_sha256"] = prep._sha(files["blind-review-view.json"])
    elif fault == "prompt_view":
        files["review-instructions.txt"] = b'SYNTHETIC\nDATA:\n{"cases":[]}\n'
        sidecar["prompt_file_sha256"] = prep._sha(files["review-instructions.txt"])
        sidecar["submitted_prompt_utf8_sha256"] = prep._sha(files["review-instructions.txt"].rstrip())
    elif fault in {"prompt_hash", "submitted_hash", "output_hash", "origin_hash", "origin_head"}:
        field = {"prompt_hash": "prompt_file_sha256", "submitted_hash": "submitted_prompt_utf8_sha256",
                 "output_hash": "review_output_sha256", "origin_hash": "origin_packet_file_sha256", "origin_head": "origin_git_head"}[fault]
        sidecar[field] = "e" * (40 if fault == "origin_head" else 64)
    elif fault == "status":
        sidecar["status"] = "not_run"
    elif fault == "human":
        sidecar["provenance"]["not_human_gold"] = False
    elif fault == "metadata":
        sidecar["provenance"]["effective_backend_metadata"] = {"self_identified": "strong"}
    elif fault == "fork":
        sidecar["provenance"]["history_forked"] = True
    elif fault == "blinding":
        sidecar["blinding"]["hidden"].remove("draft_references")
    elif fault == "boundaries":
        sidecar["state_boundaries"]["native_efficacy"] = "passed"
    elif fault == "mechanical":
        sidecar["mechanical_validation"]["title_quotes_exact_matches"] = 0
    elif fault == "comparison":
        sidecar["draft_comparison"]["is_accuracy_estimate"] = True
    else:
        row = review["cases"][0]
        if fault == "uncertain":
            row["disposition"] = "uncertain"
        elif fault == "partial_support":
            row["support_status"] = "mixed"
        elif fault == "no_fit_ids":
            row["disposition"] = "no_catalog_fit"
        elif fault == "empty_positive":
            row["acceptable_source_ids"] = []
        elif fault == "bad_id":
            row["acceptable_source_ids"] = ["A99"]
        elif fault == "duplicate_id":
            row["acceptable_source_ids"] = ["A3", "A3"]
        elif fault == "quote":
            row["title_quotes"][0]["quote"] = "not actually in synthetic title"
        elif fault == "near_miss":
            row["near_misses"][0]["source_id"] = "A99"
        elif fault == "case_order":
            review["cases"].reverse()
        elif fault == "extra_key":
            row["verified_semantic_truth"] = True
        files["reviewer-output.json"] = dump(review)
        sidecar["review_output_sha256"] = prep._sha(files["reviewer-output.json"])
    files["review-provenance.json"] = dump(sidecar)
    with pytest.raises((pilot.PilotStopped, ValueError)):
        validate_files(context, files)


def cli_args(context):
    return ["--expected-commit", HEAD, "--expected-packet-sha256", context["prepared"]["origin_packet_file_sha256"],
            "--expected-review-bundle-sha256", context["prepared"]["review_bundle_sha256"],
            "--native", "--authorization-confirmed"]


@pytest.mark.parametrize("fault", ["packet", "review", "dependency", "authorization", "occupied", "partial", "corrupt", "budget", "claim_fsync"])
def test_prechecks_stop_before_key_and_dispatch(context, monkeypatch, fault):
    """Rejected identities, authorization, output and reservation precede key lookup."""
    args = cli_args(context)
    root = context["root"]
    output = root / pilot.FIXED_OUTPUT
    if fault == "packet":
        (root / pilot.PACKET).write_bytes(b"{}")
    elif fault == "review":
        (root / pilot.REVIEW_FILES[-1]).write_bytes(b"{}")
    elif fault == "dependency":
        context["identity"]["working_file_sha256"]["synthetic.py"] = "f" * 64
    elif fault == "authorization":
        args.remove("--authorization-confirmed")
    elif fault in {"occupied", "partial", "corrupt"}:
        output.mkdir()
        if fault != "occupied":
            (output / "manifest.json").write_bytes(b"{" if fault == "corrupt" else b"{}")
    elif fault == "budget":
        monkeypatch.setattr(pilot, "RESERVATION_USD", Decimal("0.02"))
    elif fault == "claim_fsync":
        monkeypatch.setattr(os, "fsync", lambda _: (_ for _ in ()).throw(OSError("synthetic failure")))
    calls = []
    original = os.environ.get

    def env(name, *default):
        if name == "DASHSCOPE_API_KEY":
            calls.append(name)
            raise AssertionError("key accessed")
        return original(name, *default)

    monkeypatch.setattr(os.environ, "get", env)
    monkeypatch.setattr(pilot, "_execute", lambda *_: pytest.fail("dispatch reached"))
    assert pilot.main(args) == 2
    assert calls == []
    if fault not in {"occupied", "partial", "corrupt", "claim_fsync"}:
        assert not output.exists()


class NativeGuard(rehearsal._Guard):
    def __init__(self, context, *, fault=None, fail_index=1):
        super().__init__()
        self.context = context
        self.fault = fault
        self.fail_index = fail_index

    def dispatch(self, request):
        index = len(self.requests)
        self.check(index < 4, "extra_native_call")
        case = self.context["packet"]["prepared"]["cases"][index]
        doc = self.context["packet"]["prepared"]["documents"][case["doc_id"]]
        wire = prep._wire(doc, case["question"])
        self.requests.append(bytes(request.content))
        self.check(request.content == wire, "wire_mismatch")
        self.check(request.headers["authorization"] == "Bearer " + FAKE_KEY, "key_mismatch")
        from academic_agent.report_evidence_qwen_canary import ENDPOINT
        self.check(str(request.url) == ENDPOINT and request.method == "POST", "endpoint_mismatch")
        root = self.context["root"] / pilot.FIXED_OUTPUT
        manifest = json.loads((root / "manifest.json").read_bytes())
        self.check(manifest["batch_reservation_usd"] == str(4 * pilot.RESERVATION_USD), "batch_unreserved")
        self.check((root / (case["case_id"] + "-intent.json")).is_file(), "unpersisted_intent")
        events = [json.loads(line) for line in (root / "batch-events.jsonl").read_bytes().splitlines()]
        self.check(events[-1]["event"] == "native_entry" and events[-1]["wire_sha256"] == prep._sha(wire), "unpersisted_entry")
        choice = ("A3", "A2", "A3", None)[index]
        fault = self.fault if index == self.fail_index else None
        if fault == "reference":
            choice = "M1"
        message = {"role": "assistant", "content": '{"action":"decline"}'} if choice is None else {
            "role": "assistant", "content": None, "tool_calls": [{"id": "synthetic-ruq", "type": "function",
            "function": {"name": "read_source", "arguments": json.dumps({"source_id": choice})}}]}
        if fault == "refusal":
            message = {"role": "assistant", "content": None, "refusal": "Synthetic refusal"}
        payload = {"model": "different-model" if fault == "model" else pilot.MODEL,
            "usage": None if fault == "unknown" else {"prompt_tokens": 100 + index, "completion_tokens": 20, "total_tokens": 120 + index},
            "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}]}
        return httpx.Response(200, stream=httpx.ByteStream(dump(payload)))


def execute(context, guard):
    with ExitStack() as stack:
        rehearsal._install_guards(stack, guard)
        batch = pilot._Batch(context["prepared"])
        result = pilot._execute(context["prepared"], batch, FAKE_KEY)
    assert guard.failures == []
    return result, batch


def test_four_full_native_post_get_paths_and_set_valued_reference(context):
    """All four real adapter paths preserve wire, text and accounting with one shared cap."""
    guard = NativeGuard(context)
    result, batch = execute(context, guard)
    assert result["state"] == "passed"
    assert result["native_entries"] == result["selector_entries"] == len(guard.requests) == 4
    assert result["batch_reservation_usd"] == "0.044597248"
    assert result["invoice_status"] == "not_observed"
    for row in result["cases"]:
        assert row["post"]["accounting"] == row["get"]["accounting"]
        assert row["post"]["receipt"]["result"] == row["get"]["receipt"]["result"]
        assert row["get"]["accounting"]["usage"]["status"] == "reported_complete"
        assert row["get"]["accounting"]["cost"]["status"] == "estimated"
        assert row["get"]["receipt"]["delivery_snapshot_reads"] == 1
        assert row["post"]["receipt"]["delivery_snapshot_reads"] == 0
    assert result["cases"][1]["get"]["receipt"]["result"]["source"]["source_id"] == "A2"
    assert result["cases"][3]["get"]["receipt"]["result"]["reason"] == "selector_declined"
    assert json.loads((batch.root / "summary.json").read_bytes()) == result
    with pytest.raises(pilot.PilotStopped):
        batch.before_http(4, guard.requests[-1], guard.requests[-1])
    with pytest.raises(FileExistsError):
        pilot._Batch(context["prepared"])
    for wire in guard.requests:
        assert not any(marker in wire for marker in (b"SYNTHETIC SAVED", b"SYNTHETIC REPORT", b"acceptable_source_ids",
            b"keyword_query", b"blind_review", b"sandbox_alias", FAKE_KEY.encode()))


@pytest.mark.parametrize("fault", ["unknown", "model", "refusal", "reference"])
def test_first_native_failure_leaves_rest_not_run(context, fault):
    """A failed second case consumes its reservation and cannot dispatch remaining cases."""
    guard = NativeGuard(context, fault=fault)
    result, _ = execute(context, guard)
    assert result["state"] == "failed" and len(guard.requests) == 2
    assert [row["state"] for row in result["cases"]] == ["passed", "failed", "not_run", "not_run"]
    assert result["batch_reservation_usd"] == "0.044597248"


def test_lost_ack_only_get_no_redispatch(context, monkeypatch):
    """A lost POST reply is not a reason to repeat POST or select a new receipt."""
    from fastapi.testclient import TestClient
    original_post, original_get = TestClient.post, TestClient.get
    calls = []

    def post(self, *args, **kwargs):
        calls.append(("POST", kwargs["headers"]["Idempotency-Key"]))
        value = original_post(self, *args, **kwargs)
        if len(calls) == 1:
            raise httpx.ReadError("synthetic lost acknowledgement")
        return value

    def get(self, *args, **kwargs):
        calls.append(("GET", kwargs["headers"]["Idempotency-Key"]))
        return original_get(self, *args, **kwargs)

    monkeypatch.setattr(TestClient, "post", post)
    monkeypatch.setattr(TestClient, "get", get)
    result, _ = execute(context, NativeGuard(context))
    assert result["state"] == "passed" and result["native_entries"] == 4
    assert [name for name, _ in calls] == ["POST", "GET"] * 4
    assert all(calls[i][1] == calls[i + 1][1] for i in range(0, 8, 2))
    assert result["cases"][0]["lost_ack"] is True and result["cases"][0]["post"] is None


@pytest.mark.parametrize("fault", ["partial", "unavailable", "changed_cost", "drop_field", "pending_get", "extra_get_admission", "native_finish", "wire", "boolean_read_count", "boolean_schema"])
def test_accounting_and_delivery_faults_stop_batch(context, monkeypatch, fault):
    """Partial/unavailable usage and broken wire/GET seams fail even if text survives."""
    from api.saved_source_accounting import AccountingStore
    from api import access, runs, saved_source_controller
    from academic_agent.report_evidence_source_locator_qwen_transport import LocatorQwenLedger
    if fault in {"partial", "unavailable", "changed_cost"}:
        original = AccountingStore.observe

        def observe(self, *args):
            value = original(self, *args)
            if value["publication_state"] == "sealed":
                if fault == "partial":
                    value["usage"]["status"] = "reported_partial"
                    value["native_journal_state"] = "unresolved"
                    value["cost"]["status"] = "partial_estimate"
                    value["fault_codes"] = ["native_journal_unresolved"]
                elif fault == "changed_cost":
                    value["cost"]["estimated_usd"] = "0.000000001"
                else:
                    value["publication_state"] = "unavailable"
            return value

        monkeypatch.setattr(AccountingStore, "observe", observe)
    elif fault in {"drop_field", "pending_get", "extra_get_admission", "boolean_read_count", "boolean_schema"}:
        from fastapi.testclient import TestClient
        original_get = TestClient.get

        def get(self, *args, **kwargs):
            response = original_get(self, *args, **kwargs)
            value = response.json()
            if fault == "drop_field":
                del value["accounting"]["cost"]
            elif fault == "pending_get":
                value["receipt"]["state"] = "pending"
            elif fault == "boolean_read_count":
                value["receipt"]["delivery_snapshot_reads"] = True
            elif fault == "boolean_schema":
                value["receipt"]["schema_version"] = True
            else:
                runs._daily_counts[access.owner_id(pilot.CODE)] += 1
            return httpx.Response(200, content=dump(value))

        monkeypatch.setattr(TestClient, "get", get)
    elif fault == "native_finish":
        original_append = LocatorQwenLedger._append

        def append(self, event):
            if event["event"] == "request_finished":
                raise OSError("synthetic finish persistence failure")
            return original_append(self, event)

        monkeypatch.setattr(LocatorQwenLedger, "_append", append)
    elif fault == "wire":
        original_request = saved_source_controller.locate_saved_source

        def changed(snapshot, question, **kwargs):
            return original_request(snapshot, question + " tampered", **kwargs)

        monkeypatch.setattr(saved_source_controller, "locate_saved_source", changed)
    guard = NativeGuard(context)
    result, batch = execute(context, guard)
    assert result["state"] == "failed"
    assert [row["state"] for row in result["cases"]] == ["failed", "not_run", "not_run", "not_run"]
    assert len(guard.requests) == (0 if fault == "wire" else 1)
    failed = result["cases"][0]
    assert json.loads((batch.root / "RU01-failure.json").read_bytes()) == failed
    assert failed["failed_gate"] in {"http_envelope", "accounting_gate"}
    evidence = failed["observations"]
    assert evidence["post"]["state"] == "received"
    if fault == "wire":
        assert evidence["get"]["state"] == "not_received"
    elif fault in {"drop_field", "pending_get", "boolean_read_count", "boolean_schema"}:
        assert evidence["get"]["state"] == "received_invalid"
        assert "payload" not in evidence["get"]
        assert evidence["get"]["http_status"] == 200
    else:
        assert evidence["get"]["state"] == "received"
    assert FAKE_KEY.encode() not in (batch.root / "RU01-failure.json").read_bytes()


def test_batch_persistence_failure_before_native_entry(context, monkeypatch):
    """Missing aggregate journal persistence cannot be replaced with in-memory permission."""
    original = pilot._Batch.append

    def append(self, event):
        if event["event"] == "native_entry":
            raise OSError("synthetic aggregate fsync failure")
        return original(self, event)

    monkeypatch.setattr(pilot._Batch, "append", append)
    guard = NativeGuard(context)
    result, batch = execute(context, guard)
    assert not guard.requests and result["state"] == "failed"
    assert batch.root.is_dir() and result["batch_reservation_usd"] == "0.044597248"
    assert [row["state"] for row in result["cases"]] == ["failed", "not_run", "not_run", "not_run"]


def test_failed_reference_preserves_actual_http_observations(context):
    """A failed reference gate must not erase completed HTTP delivery/accounting."""
    guard = NativeGuard(context, fault="reference")
    result, batch = execute(context, guard)
    assert [row["state"] for row in result["cases"]] == ["passed", "failed", "not_run", "not_run"]
    failed = result["cases"][1]
    assert failed["failed_gate"] == "reference_gate"
    artifact = json.loads((batch.root / "RU02-failure.json").read_bytes())
    assert artifact == failed
    evidence = failed["observations"]
    assert evidence["lost_ack"] is False
    assert evidence["post"]["payload"]["receipt"]["result"]["source"]["source_id"] == "M1"
    assert evidence["post"]["payload"]["accounting"] == evidence["get"]["payload"]["accounting"]
    assert evidence["get"]["payload"]["receipt"]["delivery_source_reads"] == 1
    assert evidence["post"]["payload"]["receipt"]["delivery_source_reads"] == 0
    assert evidence["post"]["counts"] == evidence["get"]["counts"] == {
        "native_entries": 2, "selector_entries": 2, "paid_admissions": 2}
    assert evidence["publication"] == "complete_for_captured_observations"
    assert FAKE_KEY.encode() not in (batch.root / "RU02-failure.json").read_bytes()


@pytest.mark.parametrize("lane", ["post", "get"])
def test_observation_publication_fault_keeps_occupied_and_stops(context, monkeypatch, lane):
    """A partially written observation cannot become a durable failure/success claim."""
    original = pilot._new_bytes

    def write(path, raw):
        if path.name == "RU01-http-" + lane + ".json":
            original(path, b"{")
            raise OSError("synthetic observation fsync failure")
        return original(path, raw)

    monkeypatch.setattr(pilot, "_new_bytes", write)
    guard = NativeGuard(context)
    with ExitStack() as stack:
        rehearsal._install_guards(stack, guard)
        batch = pilot._Batch(context["prepared"])
        with pytest.raises(pilot._ObservationWriteFailed):
            pilot._execute(context["prepared"], batch, FAKE_KEY)
    assert guard.failures == [] and len(guard.requests) == 1
    assert (batch.root / ("RU01-http-" + lane + ".json")).read_bytes() == b"{"
    assert not (batch.root / "summary.json").exists()
    assert not (batch.root / "RU01-failure.json").exists()
    assert not (batch.root / "RU02-intent.json").exists()
    assert batch.rows[1:] == [{"case_id": case, "state": "not_run"} for case in prep.CASE_IDS[1:]]
    with pytest.raises(FileExistsError):
        pilot._Batch(context["prepared"])


def test_lost_ack_then_invalid_get_never_invents_post(context, monkeypatch):
    """Receipt recovery is new observation, never reconstructed POST evidence."""
    from fastapi.testclient import TestClient
    original_post, original_get = TestClient.post, TestClient.get
    calls = []

    def post(self, *args, **kwargs):
        calls.append("POST")
        original_post(self, *args, **kwargs)
        raise httpx.ReadError("synthetic lost acknowledgement")

    def get(self, *args, **kwargs):
        calls.append("GET")
        value = original_get(self, *args, **kwargs).json()
        del value["accounting"]["cost"]
        return httpx.Response(200, content=dump(value))

    monkeypatch.setattr(TestClient, "post", post)
    monkeypatch.setattr(TestClient, "get", get)
    guard = NativeGuard(context)
    result, batch = execute(context, guard)
    assert calls == ["POST", "GET"] and len(guard.requests) == 1
    assert [row["state"] for row in result["cases"]] == ["failed", "not_run", "not_run", "not_run"]
    saved = json.loads((batch.root / "RU01-failure.json").read_bytes())["observations"]
    assert saved["lost_ack"] is True and saved["post"]["state"] == "lost_ack"
    assert saved["get"]["state"] == "received_invalid"
    assert "payload" not in saved["get"] and "payload" not in saved["post"]


def test_label_blind_preview_despite_rebound_drafts(context):
    """Reference rebinding never changes dynamic provider prompt or chooses scripts."""
    before = prep.preview_wire(context["packet"])
    inputs = prep._inputs(context["packet"])
    refs = json.loads(inputs["references"])
    refs["cases"][0]["acceptable_source_ids"] = ["M1"]
    inputs["references"] = dump(refs)
    scripts = json.loads(inputs["scripts"])
    scripts["cases"][0]["source_id"] = "P1"
    inputs["scripts"] = dump(scripts)
    changed = prep.build_packet(**inputs)
    assert changed["packet_sha256"] != context["packet"]["packet_sha256"]
    assert prep.preview_wire(changed) == before
    assert prep.review_view(changed) == prep.review_view(context["packet"])


def test_identity_closure_has_new_native_usage_assets_and_no_production_mount():
    """The old preparation list omits the direct native transport and is insufficient."""
    paths = pilot.identity_paths()
    for name in (pilot.PROTOCOL, "src/academic_agent/saved_source_real_qwen_canary.py",
            "src/academic_agent/report_evidence_source_locator_qwen_transport.py",
            "src/academic_agent/report_evidence_qwen_transport.py", "src/academic_agent/report_evidence_qwen_canary.py",
            "api/saved_source_usage_app.py", "api/saved_source_controller.py", "api/saved_source_receipts.py",
            "api/saved_source_accounting.py", "tests/test_saved_source_real_qwen_canary.py",
            "web/saved-source-usage/accounting.js", "web/saved-source-usage/app.js", "uv.lock"):
        assert name in paths
    assert all(not name.startswith("outputs/") for name in paths)
    production = (pilot.ROOT / "api/main.py").read_text(encoding="utf-8")
    assert "saved_source_real_qwen_canary" not in production and "create_saved_source_usage_app" not in production


@pytest.mark.parametrize("fault", [None, "head", "dirty", "blob", "version"])
def test_current_committed_closure_and_installed_lock_versions(tmp_path, monkeypatch, fault):
    """Clean status alone cannot substitute for committed bytes or installed versions."""
    files = {".gitattributes": b"* text=auto eol=lf\n", "synthetic.py": b"# synthetic only\n",
             "uv.lock": b'[[package]]\nname = "httpx"\nversion = "0.28.1"\n'}
    for name, raw in files.items():
        (tmp_path / name).write_bytes(raw)
    monkeypatch.setattr(pilot, "ROOT", tmp_path)
    monkeypatch.setattr(pilot, "identity_paths", lambda: tuple(files))
    monkeypatch.setattr(pilot, "DEPENDENCIES", ("httpx",))
    monkeypatch.setattr(pilot, "version", lambda _: "wrong" if fault == "version" else "0.28.1")

    def git(*args):
        if args[0] == "rev-parse":
            return (OLD_HEAD if fault == "head" else HEAD).encode()
        if args[0] == "status":
            return b" M synthetic.py" if fault == "dirty" else b""
        name = args[1].split(":", 1)[1]
        return b"changed" if fault == "blob" and name == "synthetic.py" else files[name]

    monkeypatch.setattr(pilot, "_git", git)
    if fault is None:
        value = pilot.verify_identity(HEAD)
        assert value["runtime"]["httpx"] == "0.28.1"
        assert value["working_file_sha256"] == {name: prep._sha(raw) for name, raw in files.items()}
    else:
        with pytest.raises(pilot.PilotStopped):
            pilot.verify_identity(HEAD)


def test_aggregate_fence_rejects_wire_change_and_reentry(context):
    """A complete-body mismatch cannot enter HTTP even with a matching selected ID."""
    batch = pilot._Batch(context["prepared"])
    case = context["packet"]["prepared"]["cases"][0]
    document = context["packet"]["prepared"]["documents"][case["doc_id"]]
    wire = prep._wire(document, case["question"])
    batch.start(0, case, wire)
    with pytest.raises(pilot.PilotStopped):
        batch.before_http(0, wire + b" ", wire)
    assert batch.entries == 0
    batch.before_http(0, wire, wire)
    with pytest.raises(pilot.PilotStopped):
        batch.before_http(0, wire, wire)
    assert batch.entries == 1


def test_default_fresh_subprocess_no_secret_private_network_or_output(tmp_path):
    """Import/default CLI stays inert in a fresh interpreter, not just cached pytest imports."""
    root = pilot.ROOT
    script = r'''
import builtins, os, pathlib, socket, sys
sys.dont_write_bytecode = True
violations = []
def deny(reason):
    violations.append(reason)
    raise AssertionError(reason)
original_getitem = os._Environ.__getitem__
def getenv(self, key):
    if any(token in key.upper() for token in ('KEY', 'TOKEN', 'SECRET', 'ACCESS_CODE')):
        deny('secret environment access')
    return original_getitem(self, key)
os._Environ.__getitem__ = getenv
def audit(event, args):
    if event == 'open':
        path, mode, flags = args
        if isinstance(path, (str, bytes, pathlib.Path)):
            text = str(path).replace('\\', '/').lower()
            if '/outputs/' in text or text.endswith('/.env'):
                deny('private read')
        if isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
            deny('write')
    if event.startswith('socket.'):
        deny('network')
sys.addaudithook(audit)
from academic_agent import saved_source_real_qwen_canary as pilot
assert 'api.saved_source_usage_app' not in sys.modules
assert 'api.main' not in sys.modules
result = pilot.main([])
assert result in (0, 2)  # Uncommitted runner must refuse; committed closure may pass.
assert violations == []
assert 'api.saved_source_usage_app' not in sys.modules
assert 'api.main' not in sys.modules
'''
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP") if key in os.environ}
    env.update(PYTHONPATH=os.pathsep.join((str(root / "src"), str(root))), PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    result = subprocess.run([sys.executable, "-X", "utf8", "-W", "error::UserWarning", "-c", script],
                            env=env, cwd=tmp_path, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr.decode("utf-8")
    assert not result.stderr
    data = json.loads(result.stdout)
    assert set(data) in ({"state"}, {"state", "identity_sha256"})
    assert data["state"] in {"unavailable", "identity_only"}
    assert list(tmp_path.iterdir()) == []


_NATIVE_COMPOSITION_CHILD = r'''
import json, os, pathlib, socket, sys
from contextlib import ExitStack
from copy import deepcopy
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

sys.dont_write_bytecode = True
workspace = pathlib.Path.cwd().resolve()
repository = pathlib.Path(sys.argv[1]).resolve()
fault = sys.argv[2]
assert fault in ('none', 'dotenv', 'credential', 'network')
violations = []
network_events = []
file_events = []
public_roots = [repository / name for name in ('src', 'api', 'web', 'tests', '.venv')]
public_roots += [pathlib.Path(sys.base_prefix), pathlib.Path(sys.prefix)]
public_roots = [path.resolve() for path in public_roots]

def deny(category):
    violations.append(category)
    raise AssertionError(category)

def check_sensitive_path(path):
    parts = {part.lower() for part in path.parts}
    if path.name.lower() == '.env' or path.name.lower().startswith('.env.'):
        deny('dotenv_access')
    if parts & {'.aws', '.azure', '.ssh', '.codex', '.credentials', 'synthetic-credential-store'}:
        deny('credential_store_access')

def check_path(value, writing=False, directory=False):
    if isinstance(value, int):
        return
    original = pathlib.Path(os.fsdecode(value)).absolute()
    check_sensitive_path(original)
    if original.is_relative_to(repository / 'outputs') and not original.is_relative_to(workspace):
        deny('shared_private_output_access')
    try:
        # Compare the same canonical representation on BOTH sides. absolute()
        # neither resolves a runtime alias nor prevents a public-looking '..'
        # or symlink from escaping. Never admit raw sys.path as trusted roots.
        path = original.resolve()
    except (OSError, RuntimeError):
        deny('path_resolution_failed')
    check_sensitive_path(path)
    if path.is_relative_to(workspace):
        return
    # Deny real outputs, including siblings of pytest's new synthetic workspace.
    if path.is_relative_to(repository / 'outputs'):
        deny('shared_private_output_access')
    if directory and path == repository:
        return
    if writing or not any(path.is_relative_to(root) for root in public_roots):
        file_events.append({'basename': path.name, 'repository_root': path == repository,
                            'writing': writing, 'caller': sys._getframe(2).f_code.co_name})
        deny('nonpublic_file_access')

def check_sqlite_uri(value):
    # The unchanged stores pass Path.as_uri() plus mode=ro/rw. The URI itself
    # is not a filesystem pathname (especially on Windows); guard the decoded
    # local target, with the SAME canonical/sensitive/private-output rules.
    if not isinstance(value, str) or not value.startswith('file:'):
        deny('invalid_sqlite_uri')
    uri = urlsplit(value)
    if uri.netloc or uri.fragment or uri.query not in ('mode=ro', 'mode=rw'):
        deny('invalid_sqlite_uri')
    try:
        path = unquote(uri.path, encoding='utf-8', errors='strict')
    except UnicodeError:
        deny('invalid_sqlite_uri')
    if not path.startswith('/') or '\x00' in path:
        deny('invalid_sqlite_uri')
    if os.name == 'nt' and len(path) >= 3 and path[1].isalpha() and path[2] == ':':
        path = path[1:]
    check_path(path, writing=True)

def audit(event, args):
    if event == 'open':
        path, mode, flags = args
        writing = isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
        check_path(path, writing)
    elif event == 'sqlite3.connect':
        check_sqlite_uri(args[0])
    elif event in ('os.listdir', 'os.scandir') and args[0] is not None:
        # Normal import/distribution discovery lists sys.path's repository
        # root. Admit that exact directory enumeration, never open its private
        # files or descend into shared outputs; the open guard is unchanged.
        check_path(args[0], directory=True)
    elif event in ('socket.getaddrinfo', 'socket.gethostbyname', 'socket.gethostbyaddr', 'socket.sendto'):
        network_events.append(event)
        deny('other_network_access')
    elif event in ('socket.connect', 'socket.bind'):
        address = args[1]
        # Windows asyncio needs a loopback socketpair, not HTTP/provider traffic.
        if not (isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1')):
            network_events.append(event)
            deny('other_network_access')
        network_events.append('loopback_socketpair')

sys.addaudithook(audit)

if fault != 'none':
    try:
        if fault == 'dotenv':
            (workspace / '.env').read_bytes()
        elif fault == 'credential':
            (workspace / 'synthetic-credential-store' / 'token').read_bytes()
        else:
            socket.getaddrinfo('example.invalid', 443)
    except AssertionError:
        print(json.dumps({'probe': fault, 'violations': violations, 'composition_started': False}))
        raise SystemExit(17)
    raise AssertionError('guard did not reject the access')

# Importing helpers does NOT load conftest/run pytest fixtures. CrewAI and its
# auth/token functions are neither imported nor patched in this fresh process.
from test_saved_source_real_qwen_canary import NativeGuard, FAKE_KEY, HEAD, synthetic_inputs
from academic_agent import saved_source_real_eval as prep
from academic_agent import saved_source_real_qwen_canary as pilot
import httpx
from fastapi.testclient import TestClient

def forbidden_modules():
    return sorted(name for name in sys.modules if name == 'api.main'
                  or name.split('.')[0] in ('crewai', 'crewai_core'))

assert forbidden_modules() == []
# Execution/import seam only: committed-tree acceptance has separate tests.
# Both identity boundaries are synthetic, never historical packet identities.
identity = {'git_head': HEAD, 'working_file_sha256': {'synthetic.py': 'c' * 64}}
prep.ROOT = pilot.ROOT = workspace
prep.code_identity = lambda: deepcopy(identity)
packet = prep.build_packet(**synthetic_inputs())
source_identity = {'commit': HEAD, 'working_file_sha256': identity['working_file_sha256'],
                   'configuration': pilot.configuration()}
pilot.verify_identity = lambda expected: deepcopy(source_identity) if expected == HEAD else None
prepared = {'identity': source_identity, 'origin_packet_file_sha256': 'd' * 64,
            'review_bundle_sha256': 'e' * 64, 'packet': packet,
            'labels': dict(zip(prep.CASE_IDS, (['A3'], ['A1', 'A2'], ['A3'], []), strict=True))}
(workspace / 'outputs').mkdir()
guard = NativeGuard({'packet': packet, 'prepared': prepared, 'root': workspace})
http_methods = []
original_post, original_get = TestClient.post, TestClient.get

async def qwen_only(self, request):
    from academic_agent.report_evidence_qwen_canary import ENDPOINT
    if request.method != 'POST' or str(request.url) != ENDPOINT:
        deny('other_http_access')
    return guard.dispatch(request)

def no_other_http(*args, **kwargs):
    deny('other_http_access')

def post(self, *args, **kwargs):
    http_methods.append('POST')
    return original_post(self, *args, **kwargs)

def get(self, *args, **kwargs):
    http_methods.append('GET')
    return original_get(self, *args, **kwargs)

with ExitStack() as stack:
    # Keep actual AsyncClient/AsyncHTTPTransport construction. Intercept only
    # the exact Qwen entry, not a selector, controller, loader or app factory.
    stack.enter_context(patch.object(httpx.AsyncHTTPTransport, 'handle_async_request', qwen_only))
    stack.enter_context(patch.object(httpx.HTTPTransport, 'handle_request', no_other_http))
    stack.enter_context(patch.object(TestClient, 'post', post))
    stack.enter_context(patch.object(TestClient, 'get', get))
    batch = pilot._Batch(prepared)
    result = pilot._execute(prepared, batch, FAKE_KEY)

assert result['state'] == 'passed', {
    'failed_gates': [row.get('failed_gate') for row in result['cases']],
    'guard_failures': guard.failures, 'violations': violations,
    'native_interceptions': len(guard.requests), 'forbidden_modules': forbidden_modules(),
    'file_events': file_events,
}
assert result['native_entries'] == result['selector_entries'] == len(guard.requests) == 4
assert http_methods == ['POST', 'GET'] * 4
assert all(row['get']['accounting']['usage']['status'] == 'reported_complete' for row in result['cases'])
assert guard.failures == [] and violations == [] and forbidden_modules() == [], {
    'guard_failures': guard.failures, 'violations': violations, 'forbidden_modules': forbidden_modules(),
    'network_events': network_events,
    'file_events': file_events,
}
assert all(event == 'loopback_socketpair' for event in network_events), network_events
assert 'api.saved_source_usage_app' in sys.modules
assert 'academic_agent.saved_source_accounted_qwen' in sys.modules
print(json.dumps({'state': 'passed', 'native_http_interceptions': len(guard.requests),
                  'external_provider_calls': 0, 'http_methods': http_methods,
                  'forbidden_modules': forbidden_modules(), 'violations': violations,
                  'other_network_events': [e for e in network_events if e != 'loopback_socketpair'],
                  'workspace_scope': 'new_synthetic_only'}))
'''


def _run_native_composition_child(tmp_path, fault):
    # Retain HOME/AppData so absent variables cannot masquerade as safe imports.
    # Flags document conditions; access guards and probes provide the evidence.
    root = pilot.ROOT
    names = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "HOMEDRIVE",
             "HOMEPATH", "HOME", "APPDATA", "LOCALAPPDATA")
    env = {name: os.environ[name] for name in names if name in os.environ}
    env.update(PYTHONPATH=os.pathsep.join((str(root / "src"), str(root), str(root / "tests"))),
               PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", PYTHON_DOTENV_DISABLED="1",
               OTEL_SDK_DISABLED="true", CREWAI_TRACING_ENABLED="false", CREWAI_TELEMETRY_ENABLED="false")
    return subprocess.run([
        sys.executable, "-B", "-X", "utf8", "-W", "error::UserWarning",
        # Preserve the project's exact known TestClient filter, no broad ignore.
        "-W", "ignore:Using " + chr(96) + "httpx" + chr(96) + " with "
        + chr(96) + "starlette.testclient" + chr(96) + " is deprecated",
        "-c", _NATIVE_COMPOSITION_CHILD, str(root), fault,
    ], env=env, cwd=tmp_path, capture_output=True, timeout=90)


def test_fresh_native_composition_has_no_production_or_crewai_import(tmp_path):
    """Real native-to-ASGI composition cannot borrow pytest's warm imports/auth patch."""
    result = _run_native_composition_child(tmp_path, "none")
    assert result.returncode == 0, result.stderr.decode("utf-8")
    assert not result.stderr
    assert json.loads(result.stdout) == {
        "state": "passed", "native_http_interceptions": 4, "external_provider_calls": 0,
        "http_methods": ["POST", "GET"] * 4, "forbidden_modules": [], "violations": [],
        "other_network_events": [], "workspace_scope": "new_synthetic_only",
    }


@pytest.mark.parametrize("fault,reason", [
    ("dotenv", "dotenv_access"), ("credential", "credential_store_access"), ("network", "other_network_access"),
])
def test_fresh_native_composition_guards_are_effective(tmp_path, fault, reason):
    """Real access attempts are stopped before I/O even with disable flags present."""
    (tmp_path / ".env").write_bytes(b"SYNTHETIC=not-a-key")
    (tmp_path / "synthetic-credential-store").mkdir()
    (tmp_path / "synthetic-credential-store/token").write_bytes(b"synthetic-not-a-real-token")
    result = _run_native_composition_child(tmp_path, fault)
    assert result.returncode == 17, result.stderr.decode("utf-8")
    assert not result.stderr
    assert json.loads(result.stdout) == {"probe": fault, "violations": [reason], "composition_started": False}


def _portable_child_path_guard():
    """Run the child's actual guard with a deterministic synthetic path resolver.

    No symlink privilege, Linux installation or private filesystem is needed.
    Resolve alias components before '..', as a real filesystem does; merely
    normalizing '..' first would erase a symlink escape. These are path-policy
    controls, not evidence of a particular CI machine's actual alias spelling.
    """
    aliases = {
        "/python-link": "/runtime",
        "/repo/src/dotenv-link": "/outside/.env",
        "/repo/src/credential-link": "/outside/.aws/credentials",
        "/repo/src/private-link": "/repo/outputs/private/report.json",
        "/repo/src/outside-link": "/outside/folder",
        "/repo/outputs/synthetic-only/escape": "/repo/outputs/private",
        "/repo/src/root-link": "/repo",
        "/repo/outputs/private/root-link": "/repo",
    }

    class ModelPath(PurePosixPath):
        def absolute(self):
            assert self.is_absolute()
            return self

        def resolve(self):
            parts = []
            for part in self.parts:
                if part == "..":
                    if len(parts) > 1:
                        parts.pop()
                else:
                    parts.append(part)
                target = aliases.get(str(PurePosixPath(*parts)))
                if target is not None:
                    parts = list(PurePosixPath(target).parts)
            return type(self)(*parts)

    namespace = {
        "os": os, "sys": sys, "pathlib": SimpleNamespace(Path=ModelPath),
        "workspace": ModelPath("/repo/outputs/synthetic-only"), "repository": ModelPath("/repo"),
        "public_roots": [ModelPath("/runtime"), ModelPath("/repo/src")],
        "violations": [], "file_events": [], "network_events": [],
        "urlsplit": urlsplit, "unquote": unquote,
    }
    tree = ast.parse(_NATIVE_COMPOSITION_CHILD)
    names = {"deny", "check_sensitive_path", "check_path", "check_sqlite_uri", "audit"}
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(ast.Module(body=selected, type_ignores=[]), "<synthetic-child-path-guard>", "exec"), namespace)
    return namespace


@pytest.mark.parametrize("path,event,writing,reason", [
    ("/runtime/lib/python3.11/lib-dynload", "os.scandir", False, None),
    ("/python-link/lib/python3.11/lib-dynload", "os.scandir", False, None),
    ("/python-link/lib/../lib/python3.11/lib-dynload", "os.listdir", False, None),
    ("/runtime/lib/python3.11/lib-dynload", "open", True, "nonpublic_file_access"),
    ("/repo/outputs/synthetic-only/new.json", "open", True, None),
    ("/repo/src/../outputs/private/report.json", "open", False, "shared_private_output_access"),
    ("/repo/src/private-link", "open", False, "shared_private_output_access"),
    ("/repo/outputs/synthetic-only/escape/report.json", "open", False, "shared_private_output_access"),
    ("/repo/outputs/synthetic-only/../private/report.json", "open", False, "shared_private_output_access"),
    ("/repo/src/dotenv-link", "open", False, "dotenv_access"),
    ("/repo/src/credential-link", "open", False, "credential_store_access"),
    ("/repo/src/outside-link/../token", "open", False, "nonpublic_file_access"),
    ("/repo/src/root-link", "os.listdir", False, None),
    ("/repo/outputs/private/root-link", "os.listdir", False, "shared_private_output_access"),
    ("/repo/outputs/synthetic-only/.env", "open", False, "dotenv_access"),
    ("/repo/outputs/synthetic-only/.aws/credentials", "open", False, "credential_store_access"),
    ("file:///repo/outputs/synthetic-only/receipt.sqlite3?mode=rw", "sqlite3.connect", False, None),
    ("file:///repo/outputs/synthetic-only/%2e%2e/private/receipt.sqlite3?mode=ro", "sqlite3.connect", False, "shared_private_output_access"),
    ("file:///repo/src/private-link?mode=rw", "sqlite3.connect", False, "shared_private_output_access"),
    ("file:///repo/outputs/synthetic-only/%2eenv?mode=ro", "sqlite3.connect", False, "dotenv_access"),
    ("file:///repo/src/credential-link?mode=ro", "sqlite3.connect", False, "credential_store_access"),
    ("file://remote/repo/outputs/synthetic-only/receipt.sqlite3?mode=rw", "sqlite3.connect", False, "invalid_sqlite_uri"),
    ("file:///repo/outputs/synthetic-only/receipt.sqlite3?mode=rw&cache=shared", "sqlite3.connect", False, "invalid_sqlite_uri"),
])
def test_child_path_guard_canonical_alias_and_escape_boundaries(path, event, writing, reason):
    """Benign runtime aliases work; lexical/public-looking paths never authorize escapes."""
    guard = _portable_child_path_guard()
    arguments = (path, "wb" if writing else "rb", os.O_WRONLY if writing else os.O_RDONLY) if event == "open" else (path,)
    if reason is None:
        guard["audit"](event, arguments)
        assert guard["violations"] == []
    else:
        with pytest.raises(AssertionError, match="^" + reason + "$"):
            guard["audit"](event, arguments)
        assert guard["violations"] == [reason]
