"""One private positive-development batch, never production or a reusable grant.

The default is read-only binding inspection. Only an explicitly acknowledged,
committed identity can consume the fixed output and then read a process key.
Existing locator/native code owns selection and the actual local read. These
single-owner filesystem checks are not a sandbox, distributed quota, package
byte attestation, provider exactly-once delivery or power-loss guarantee.
"""

import argparse
from copy import deepcopy
from decimal import Decimal
import hashlib
from importlib.metadata import version
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import tomllib

from academic_agent import report_evidence_source_locator as locator
from academic_agent import report_evidence_source_locator_qwen_transport as native
from academic_agent.report_evidence_catalog_followup import build_catalog
from academic_agent.report_evidence_followup import _strict_json
from academic_agent.report_evidence_qwen_canary import (
    CanaryStopped, INPUT_RATE, INPUT_RESERVATION, MAX_TOKENS, MODEL, OUTPUT_RATE,
    REQUEST_BYTES, RESERVATION_USD, _encoded,
)
from academic_agent.report_evidence_qwen_transport import _usage, validate_key
from academic_agent.report_evidence_snapshot import content_hash
from academic_agent.saved_source_loader import snapshot_from_saved_bytes

PROTOCOL_IDENTITY = "saved_source_positive_qwen_canary_v1"
ROOT = Path(__file__).resolve().parents[2]
PACKET = "outputs/saved_source_positive_qwen_packet_v1/packet.json"
PREVIEW = "outputs/saved_source_positive_qwen_packet_v1/request-preview.json"
FIXED_OUTPUT = "outputs/saved_source_positive_qwen_native_v1"
PROTOCOL = "docs/prereg-2026-09-26-saved-source-positive-qwen.md"
CASE_IDS = ("P01", "P02", "P03", "P04")
DOC_IDS = ("D1", "D1", "D2", "D2")
MAX_REQUESTS = 4
USD_LIMIT = Decimal("0.05")
IDENTITY_PATHS = (
    ".gitattributes", "src/academic_agent/__init__.py",
    *native.FROZEN_DEPENDENCY_COUPLING,
    "src/academic_agent/report_evidence_stage_qwen_transport.py",
    "src/academic_agent/report_evidence_source_locator_qwen_transport.py",
    "src/academic_agent/saved_source_loader.py",
    "src/academic_agent/saved_source_positive_qwen_canary.py",
    "saved_source_positive_qwen_canary.py",
    "tests/test_saved_source_positive_qwen_canary.py", PROTOCOL,
)
DEPENDENCIES = (
    "httpx", "httpcore", "anyio", "certifi", "h11", "idna", "sniffio",
    "typing-extensions", "pydantic", "pydantic-core", "annotated-types", "typing-inspection",
)
_SAFE = native._SAFE_ERRORS | frozenset({
    "binding_unavailable", "invalid_authorization", "identity_check_failed",
    "identity_drift", "packet_invalid", "preview_mismatch", "indirect_path",
    "output_occupied", "persistence_failed", "aggregate_limit", "batch_stopped",
    "native_failed", "mechanical_failed", "reference_mismatch", "provider_refusal",
    "invalid_dedicated_key", "runner_failed",
})


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _require(condition, reason):
    if not condition:
        raise CanaryStopped(reason)


def _safe(exc, fallback="runner_failed"):
    # Never stringify even a shared exception: provider/OS text is untrusted.
    if type(exc) is CanaryStopped and len(exc.args) == 1:
        reason = exc.args[0]
        if type(reason) is str and reason in _SAFE:
            return reason
    return fallback


def _plain(path):
    for part in (*reversed(path.parents), path):
        if os.path.lexists(part):
            info = part.lstat()
            _require(not stat.S_ISLNK(info.st_mode)
                     and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                     "indirect_path")


def _read(path, limit):
    _plain(path)
    _require(path.is_file() and path.stat().st_size <= limit, "binding_unavailable")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    _require(len(raw) <= limit, "binding_unavailable")
    return raw


def _shape(value, keys):
    _require(type(value) is dict and set(value) == set(keys.split()), "packet_invalid")


def _hash_string(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _wire(request):
    return _encoded({**request, "model": MODEL, "stream": False, "enable_thinking": False,
                     "parallel_tool_calls": False, "temperature": 0, "max_tokens": MAX_TOKENS})


def load_packet(expected_packet_sha256, expected_preview_sha256):
    """Hashes are supplied privately, never hardcoded or returned by the CLI.

    Embedded UTF-8 strings retain the complete original file bytes. Historical
    paths/keywords/provenance are bound but never interpreted as file authority
    or copied to a prompt. Only the fixed packet and preview paths are read.
    """
    try:
        raw = _read(ROOT / PACKET, 8 * 1024 * 1024)
        preview_raw = _read(ROOT / PREVIEW, 128 * 1024)
        _require(_hash_string(expected_packet_sha256) and _digest(raw) == expected_packet_sha256,
                 "packet_invalid")
        _require(_hash_string(expected_preview_sha256) and _digest(preview_raw) == expected_preview_sha256,
                 "preview_mismatch")
        packet = _strict_json(raw.decode("utf-8"))
        _shape(packet, "schema_version protocol_identity questions_utf8 questions_sha256 preview_sha256 documents references")
        _require(type(packet["schema_version"]) is int and packet["schema_version"] == 1
                 and packet["protocol_identity"] == PROTOCOL_IDENTITY, "packet_invalid")
        _require(packet["preview_sha256"] == expected_preview_sha256, "preview_mismatch")
        questions_raw = packet["questions_utf8"].encode("utf-8")
        _require(_digest(questions_raw) == packet["questions_sha256"], "packet_invalid")
        questions = _strict_json(questions_raw.decode("utf-8"))
        _shape(questions, "purpose authoring document_paths cases rubric")
        _require(type(questions["cases"]) is list and len(questions["cases"]) == 4, "packet_invalid")
        _shape(questions["document_paths"], "D1 D2")
        docs = packet["documents"]
        _require(type(docs) is list and len(docs) == 2, "packet_invalid")
        snapshots = {}
        for doc, doc_id in zip(docs, ("D1", "D2"), strict=True):
            _shape(doc, "doc_id sources_utf8 sources_sha256")
            data = doc["sources_utf8"].encode("utf-8")
            _require(doc["doc_id"] == doc_id and _digest(data) == doc["sources_sha256"], "packet_invalid")
            snapshot = snapshot_from_saved_bytes(data, doc_id)
            catalog = build_catalog(snapshot)
            _require(catalog["coverage"] == "complete" and catalog["title_truncation_count"] == 0
                     and catalog["returned_count"] > 0, "packet_invalid")
            snapshots[doc_id] = snapshot
        refs = packet["references"]
        _shape(refs, "status provenance cases")
        _require(refs["status"] == "fallible_llm_reviewed", "packet_invalid")
        provenance = refs["provenance"]
        _shape(provenance, "reviewer_role requested_model effective_model input_sha256 output_sha256 limitations")
        _require(all(type(provenance[key]) is str and provenance[key].strip() for key in
                     ("reviewer_role", "requested_model", "limitations"))
                 and (provenance["effective_model"] is None or type(provenance["effective_model"]) is str)
                 and all(_hash_string(provenance[key]) for key in ("input_sha256", "output_sha256")), "packet_invalid")
        _require(type(refs["cases"]) is list and len(refs["cases"]) == 4, "packet_invalid")
        preview = _strict_json(preview_raw.decode("utf-8"))
        _require(type(preview) is list and len(preview) == 4, "preview_mismatch")
        cases = []
        for case_id, doc_id, question, reference, row in zip(
                CASE_IDS, DOC_IDS, questions["cases"], refs["cases"], preview, strict=True):
            _shape(question, "case_id doc_id question keyword_query")
            _shape(reference, "case_id acceptable_source_ids")
            _shape(row, "case_id body bytes sha256")
            text = question["question"]
            _require(question["case_id"] == reference["case_id"] == row["case_id"] == case_id
                     and question["doc_id"] == doc_id and type(text) is str
                     and 1 <= len(text) <= 4096 and bool(text.strip()), "packet_invalid")
            snapshot = snapshots[doc_id]
            accepted = reference["acceptable_source_ids"]
            _require(type(accepted) is list and accepted and all(type(x) is str for x in accepted)
                     and len(accepted) == len(set(accepted)), "packet_invalid")
            by_id = {source.source_id: source for source in snapshot.sources}
            _require(all(x in by_id and by_id[x].summary and by_id[x].summary.strip()
                         and by_id[x].stored_length <= locator.MAX_SAVED_CODEPOINTS for x in accepted), "packet_invalid")
            request = locator._request(text, build_catalog(snapshot))
            wire = _wire(request)
            _require(wire == _encoded(row["body"]) and row["sha256"] == _digest(wire)
                     and type(row["bytes"]) is int and row["bytes"] == len(wire)
                     and len(wire) <= REQUEST_BYTES, "preview_mismatch")
            cases.append({"case_id": case_id, "question": text, "snapshot": snapshot,
                          "accepted": tuple(accepted), "request": request, "wire": wire})
        return cases
    except Exception as exc:  # noqa: BLE001 -- private input/decoder errors must not expose data or paths.
        raise CanaryStopped(_safe(exc, "packet_invalid")) from None


def _git(*args):
    return subprocess.run(["git", "--no-optional-locks", *args], cwd=ROOT,
                          capture_output=True, check=True, timeout=10).stdout


def verify_identity(expected_commit, expected_packet_sha256, expected_preview_sha256):
    """Check committed text, actual dependency closure and installed versions.

    Only fixed text paths permit CRLF-to-LF comparison. Unrelated worktree dirt
    is preserved. An acknowledgement cannot independently prove review or CI.
    """
    try:
        _require(type(expected_commit) is str and re.fullmatch(r"[0-9a-f]{40}", expected_commit),
                 "invalid_authorization")
        _require(_git("rev-parse", "--verify", "HEAD").decode("ascii").strip() == expected_commit,
                 "identity_check_failed")
        _require(not _git("status", "--porcelain", "--untracked-files=all", "--", *IDENTITY_PATHS).strip(),
                 "identity_check_failed")
        disk = {}
        for name in IDENTITY_PATHS:
            raw = _read(ROOT / name, 4 * 1024 * 1024)
            _require(raw.replace(b"\r\n", b"\n") == _git("show", f"{expected_commit}:{name}"),
                     "identity_check_failed")
            disk[name] = _digest(raw)
        _require((ROOT / ".gitattributes").read_bytes().replace(b"\r\n", b"\n") == b"* text=auto eol=lf\n",
                 "identity_check_failed")
        locked = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))["package"]
        installed = {name: version(name) for name in DEPENDENCIES}
        _require(all(value in {row["version"] for row in locked if row["name"] == name}
                     for name, value in installed.items()), "identity_check_failed")
        load_packet(expected_packet_sha256, expected_preview_sha256)
        return {"commit": expected_commit, "packet_sha256": expected_packet_sha256,
                "preview_sha256": expected_preview_sha256, "disk_sha256": disk,
                "runtime": {"python": platform.python_version(), **installed},
                "configuration": native.locator_qwen_configuration()}
    except Exception as exc:  # noqa: BLE001 -- git/package failures may carry paths or private material.
        raise CanaryStopped(_safe(exc, "identity_check_failed")) from None


def _recheck(identity):
    actual = verify_identity(identity["commit"], identity["packet_sha256"], identity["preview_sha256"])
    _require(actual == identity, "identity_drift")


def _publish(output, name, value):
    """Write once, flush/fsync/close before atomic link; partial files stay spent."""
    try:
        pending, final = output / ("." + name + ".pending"), output / name
        _plain(pending)
        _plain(final)
        raw = _encoded(value) + b"\n"
        with pending.open("xb") as stream:
            _require(stream.write(raw) == len(raw), "persistence_failed")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(pending, final)
        # Keep the pending hard link: no cleanup step can obscure a failed run.
    except Exception:  # noqa: BLE001 -- only a fixed persistence category is safe.
        raise CanaryStopped("persistence_failed") from None


class _Run:
    """New aggregate owner; never an old runner, ledger subclass or resettable cap."""

    def __init__(self, identity):
        self.output = ROOT / FIXED_OUTPUT
        self.identity = identity
        self.ledgers = []
        self.dispatched = []
        self.http_entries = 0
        self.stop_reason = None
        self.claim = {"protocol_identity": PROTOCOL_IDENTITY, "identity": identity,
                      "reserved_requests": 4, "reserved_usd": str(4 * RESERVATION_USD),
                      "usd_soft_limit": str(USD_LIMIT), "refund_or_resume": False,
                      "independent_consent_review_ci_verified": False}
        _require(4 * RESERVATION_USD <= USD_LIMIT, "aggregate_limit")
        _plain(self.output)
        try:
            self.output.mkdir(exist_ok=False)
        except OSError:
            raise CanaryStopped("output_occupied") from None
        _publish(self.output, "claim.json", self.claim)

    def totals(self):
        records = [record for ledger in self.ledgers for record in ledger.records]
        known = sum((Decimal(row.get("estimated_usd", "0")) for row in records), Decimal(0))
        unknown = sum(row["usage_status"] != "complete" for row in records)
        unreserved_entries = len(self.dispatched) - len(records)
        uncertain = unknown + max(0, unreserved_entries)
        return {"request_count": len(records), "http_entries": self.http_entries,
                "dispatch_intents": len(self.dispatched),
                "unknown_usage_requests": uncertain,
                "known_usage_estimated_usd": str(known), "reserved_usd": str(4 * RESERVATION_USD),
                "budget_consumed_usd": str(4 * RESERVATION_USD + sum(
                    (max(Decimal(0), Decimal(row.get("estimated_usd", "0")) - RESERVATION_USD)
                     for row in records), Decimal(0))),
                "cost_coverage": "not_observed" if not records else "lower_bound" if uncertain
                else "complete_for_reported_requests",
                "pending_cases": [ledger.case_id for ledger in self.ledgers if ledger.pending is not None],
                "price_scope": "frozen_estimate_not_invoice", "invoice": "unobserved"}

    def check_claim(self):
        _require((self.output / "claim.json").read_bytes() == _encoded(self.claim) + b"\n",
                 "persistence_failed")

    def dispatch(self, case, wire, ledger):
        _require(self.stop_reason is None, "batch_stopped")
        _require(len(self.dispatched) < MAX_REQUESTS and case["case_id"] == CASE_IDS[len(self.dispatched)]
                 and len(self.ledgers) == len(self.dispatched) + 1 and self.ledgers[-1] is ledger,
                 "aggregate_limit")
        _require(type(ledger) is native.LocatorQwenLedger and ledger.pending == 1
                 and len(ledger.records) == 1 and ledger.stop_reason is None, "mechanical_failed")
        _require(all(item.pending is None and item.stop_reason is None
                     and len(item.records) == 1 and item.records[0]["usage_status"] == "complete"
                     for item in self.ledgers[:-1]), "batch_stopped")
        _require(Decimal(self.totals()["budget_consumed_usd"]) <= USD_LIMIT, "aggregate_limit")
        _require(wire == case["wire"] and _encoded(ledger.records[0]["request"]) == wire,
                 "preview_mismatch")
        self.check_claim()
        _require((ledger.output_dir / "events.jsonl").read_bytes()
                 == _encoded({"event": "request_reserved", **ledger.records[0]}) + b"\n", "persistence_failed")
        _recheck(self.identity)
        _publish(self.output, case["case_id"] + "-intent.json",
                 {"case_id": case["case_id"], "wire_sha256": _digest(wire), "ordinal": len(self.dispatched) + 1})
        self.dispatched.append(case["case_id"])
        _recheck(self.identity)  # Drift during intent/fsync must still precede HTTP.


class _CheckedSelector:
    def __init__(self, transport, run, case):
        self.transport, self.run, self.case = transport, run, case
        self.entries, self.failure, self.response = 0, None, None
        original_post = transport._post

        async def checked_post(wire, observation):
            # Instance-local guard around the unchanged HTTP primitive, not a
            # new adapter. Native reserve has already fsynced the actual body.
            try:
                run.dispatch(case, wire, transport.ledger)
            except Exception as exc:  # noqa: BLE001 -- transport may convert exceptions; retain the runner fault.
                self.failure = _safe(exc)
                raise CanaryStopped(self.failure) from None
            run.http_entries += 1
            return await original_post(wire, observation)

        transport._post = checked_post

    def __call__(self, request, /):
        self.entries += 1
        try:
            _require(self.entries == 1 and self.run.stop_reason is None, "aggregate_limit")
            _recheck(self.run.identity)
            _require(_encoded(request) == _encoded(self.case["request"]), "preview_mismatch")
            try:
                self.response = self.transport(request)
                return deepcopy(self.response)
            finally:
                # Check after native parsing/finalization so drift cannot erase
                # known usage by interrupting the response before it is counted.
                _recheck(self.run.identity)
                self.run.check_claim()
        except Exception as exc:  # noqa: BLE001 -- locator catches selector errors; retain a separate explicit gate.
            self.failure = self.failure or _safe(exc, "native_failed")
            self.run.stop_reason = self.failure
            raise CanaryStopped(self.failure) from None


def _accounting(ledger, case):
    _require(type(ledger) is native.LocatorQwenLedger and ledger.pending is None
             and ledger.stop_reason is None and len(ledger.records) == 1, "mechanical_failed")
    row = ledger.records[0]
    _require(row["request_id"] == 1 and row["case_id"] == case["case_id"]
             and row["protocol_accepted"] is True and row["provider_response_received"] is True
             and row["response_model_matches_authorized"] is True and row["usage_status"] == "complete"
             and row["error"] is None and row["reservation_usd"] == str(RESERVATION_USD)
             and _encoded(row["request"]) == case["wire"] and row["request_sha256"] == _digest(case["wire"]),
             "mechanical_failed")
    usage = _usage({"usage": row["reported_usage"]})
    _require(usage is not None and usage == row["reported_usage"]
             and usage["prompt_tokens"] <= INPUT_RESERVATION and usage["completion_tokens"] <= MAX_TOKENS,
             "mechanical_failed")
    cost = (Decimal(usage["prompt_tokens"]) * INPUT_RATE + Decimal(usage["completion_tokens"]) * OUTPUT_RATE) / 1_000_000
    _require(row["estimated_usd"] == str(cost), "mechanical_failed")
    reserved = {key: row[key] for key in ("request_id", "case_id", "request", "request_sha256", "reservation_usd")}
    reserved.update(usage_status="unknown", provider_response_received=False,
                    response_model_matches_authorized=None, protocol_accepted=False)
    _require(set(row) == set(reserved) | {"reported_usage", "estimated_usd", "error"}, "mechanical_failed")
    expected = b"".join(_encoded(event) + b"\n" for event in (
        {"event": "request_reserved", **reserved}, {"event": "request_finished", **row}))
    _require((ledger.output_dir / "events.jsonl").read_bytes() == expected, "persistence_failed")


def _projection(case, result, checked):
    """Reconcile observed native choice with the real locator's serialized result.

    No extra read or scripted callback fabricates a receipt. Decline can pass
    mechanics but fails this positive reference; refusal stops separately.
    """
    _require(checked.failure is None and checked.entries == 1, checked.failure or "mechanical_failed")
    _accounting(checked.transport.ledger, case)
    _require(type(result) is locator.LocatorResult, "mechanical_failed")
    observed = _strict_json(locator.render_locator_result(result))
    _require(observed == result.model_dump(mode="json"), "mechanical_failed")
    message = checked.response
    calls = message.get("tool_calls") or []
    snapshot = case["snapshot"]
    selected = text = source_id = None
    if calls:
        source_id = _strict_json(calls[0]["function"]["arguments"])["source_id"]
        source = next(item for item in snapshot.sources if item.source_id == source_id)
        selected = {**source.model_dump(exclude={"summary"}), "stored_length": source.stored_length,
                    "snapshot_hash": snapshot.snapshot_hash, "source_hash": snapshot.source_hash(source),
                    "summary_hash": content_hash(source.summary)}
        if source.stored_length > locator.MAX_SAVED_CODEPOINTS:
            state, reason, reads = "out_of_scope", "selected_text_too_long", 0
        elif not source.summary:
            state, reason, reads = "missing_text", "saved_text_missing", 1
        else:
            state = "excerpt" if source.summary.strip() else "blank_text"
            reason, reads = "saved_text" if source.summary.strip() else "saved_text_blank", 1
            text = {"text": source.summary, "start": 0, "end": source.stored_length,
                    "window_truncated": False, "text_sha256": _digest(source.summary.encode("utf-8")),
                    "text_scope": "saved_summary_only"}
    else:
        state, reads = "declined", 0
        reason = "selector_refused" if message.get("refusal") else "selector_declined"
    catalog = build_catalog(snapshot)
    expected = {"method_id": locator.METHOD_ID, "state": state, "reason": reason,
                "catalog": {"catalog_hash": content_hash(catalog), "catalog_bytes": len(_encoded(catalog)),
                            **{key: catalog[key] for key in ("total_count", "returned_count", "omitted_count",
                                                           "coverage", "title_truncation_count")}},
                "source": selected, "saved_text": text, "callback_entries": 1,
                "callback_bytes": len(_encoded(case["request"])), "read_attempts": reads, "read_completed": reads,
                "selection_relevance": "not_assessed", "semantic_support": "not_assessed"}
    _require(_encoded(observed) == _encoded(expected), "mechanical_failed")
    return source_id, state, reason


def run_canary(*, expected_commit, expected_packet_sha256, expected_preview_sha256, authorize_paid):
    """Explicit parent-only native entry. Tests intercept the existing HTTP seam."""
    _require(authorize_paid == PROTOCOL_IDENTITY, "invalid_authorization")
    identity = verify_identity(expected_commit, expected_packet_sha256, expected_preview_sha256)
    cases = load_packet(expected_packet_sha256, expected_preview_sha256)
    run = _Run(identity)  # Exclusive durable aggregate claim BEFORE any key lookup.
    outcomes = [{"case_id": case_id, "status": "not_run", "mechanical_passed": None,
                 "reference_match": None, "reason": None} for case_id in CASE_IDS]
    try:
        _recheck(identity)
        run.check_claim()
        key = os.environ.get("DASHSCOPE_API_KEY")
        validate_key(key)
        for case, outcome in zip(cases, outcomes, strict=True):
            _recheck(identity)
            ledger = native.LocatorQwenLedger(run.output / case["case_id"])
            ledger.case_id = case["case_id"]
            run.ledgers.append(ledger)
            transport = native.LocatorQwenTransport(key, ledger, snapshot=case["snapshot"], question=case["question"])
            checked = _CheckedSelector(transport, run, case)
            outcome["status"] = "failed"
            outcome["mechanical_passed"] = False
            observation = None
            try:
                result = locator.locate_saved_source(case["snapshot"], case["question"], selector=checked)
                source_id, state, reason = _projection(case, result, checked)
                # Only mechanically reconciled observations are published. No
                # provider prose, raw excerpt or diagnostic reaches this file.
                observation = {
                    "selected_source_id": source_id, "state": state, "reason": reason,
                    "saved_text_length": len(result.saved_text.text) if result.saved_text is not None else None,
                    "saved_text_sha256": result.saved_text.text_sha256 if result.saved_text is not None else None,
                    "callback_entries": result.callback_entries, "callback_bytes": result.callback_bytes,
                    "read_attempts": result.read_attempts, "read_completed": result.read_completed,
                    "wire_sha256": _digest(case["wire"]),
                }
                outcome["mechanical_passed"] = True
                outcome["reference_match"] = (source_id in case["accepted"] and state == "excerpt" and reason == "saved_text")
                if reason == "selector_refused":
                    raise CanaryStopped("provider_refusal")
                _require(outcome["reference_match"], "reference_mismatch")
                _require(Decimal(run.totals()["budget_consumed_usd"]) <= USD_LIMIT, "aggregate_limit")
                outcome["status"] = "passed"
            except Exception as exc:  # noqa: BLE001 -- retain usage and fixed reason even when locator swallowed a fault.
                outcome["reason"] = run.stop_reason = _safe(exc, "mechanical_failed")
            _publish(run.output, case["case_id"] + "-result.json", {**outcome, "observation": observation})
            _recheck(identity)
            if run.stop_reason is not None:
                break
    except Exception as exc:  # noqa: BLE001 -- interrupted/failed runs remain occupied; never echo a key or source.
        run.stop_reason = _safe(exc)
    except KeyboardInterrupt:
        run.stop_reason = "native_failed"
    summary = {"mode": "native_positive_development", "batch_passed": run.stop_reason is None
               and all(row["status"] == "passed" for row in outcomes), "cases": outcomes,
               "stop_reason": run.stop_reason, "summary_persisted": True,
               "mechanical_passes": sum(row["mechanical_passed"] is True for row in outcomes),
               "reference_checks": sum(row["reference_match"] is not None for row in outcomes),
               "reference_matches": sum(row["reference_match"] is True for row in outcomes),
               "unrun_cases": [row["case_id"] for row in outcomes if row["status"] == "not_run"],
               "semantic_support": "not_assessed", "reference_scope": "fallible_llm_development_not_accuracy",
               **run.totals()}
    try:
        _publish(run.output, "summary.json", summary)
    except Exception:  # noqa: BLE001 -- observed lower bounds survive failed publication in the safe return.
        summary.update(batch_passed=False, summary_persisted=False, stop_reason="persistence_failed")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-commit")
    parser.add_argument("--expected-packet-sha256")
    parser.add_argument("--expected-preview-sha256")
    parser.add_argument("--authorize-paid")
    args = parser.parse_args(argv)
    try:
        expected = {"expected_commit": args.expected_commit, "expected_packet_sha256": args.expected_packet_sha256,
                    "expected_preview_sha256": args.expected_preview_sha256}
        if args.authorize_paid is None:
            if not all(expected.values()) or not (ROOT / PACKET).is_file() or not (ROOT / PREVIEW).is_file():
                print('{"mode":"identity_only","binding":"unavailable","ready":false}')
                return 1
            verify_identity(**expected)
            print('{"mode":"identity_only","binding":"verified","ready":false,"live_authorized":false}')
            return 0
        summary = run_canary(**expected, authorize_paid=args.authorize_paid)
        print(_encoded(summary).decode("ascii"))
        return 0 if summary["batch_passed"] else 1
    except Exception as exc:  # noqa: BLE001 -- all CLI failure text is a fixed category, never private identity/data.
        print(_encoded({"ready": False, "error": _safe(exc)}).decode("ascii"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
