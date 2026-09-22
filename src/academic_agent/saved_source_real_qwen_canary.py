"""RUQ's fixed, private native-to-ASGI pilot, inert unless separately authorized.

This module is a CLI, not a provider factory or production registration. The
origin packet remains an offline artifact. Only an exact, current committed
closure and a separately bound fallible LLM review can prepare a new batch;
neither hashes nor CLI flags confer external data-transfer/spending authority.
"""

from __future__ import annotations

import argparse
import ast
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import re
import secrets
import stat
import subprocess
import time
import tomllib
from unittest.mock import patch

from academic_agent import saved_source_real_eval as prep
from academic_agent.report_evidence_followup import _strict_json
from academic_agent.report_evidence_qwen_canary import MODEL, RESERVATION_USD, _encoded

ROOT = Path(__file__).resolve().parents[2]
METHOD = "saved_source_real_usage_qwen_canary_v1"
PROTOCOL = "docs/prereg-2026-09-22-real-source-usage-qwen.md"
PACKET = "outputs/saved_source_real_usage_eval_v1/packet.json"
VIEW = "outputs/saved_source_real_usage_eval_v1/blind-review-view.json"
REVIEW_ROOT = "outputs/saved_source_real_usage_review_v1/"
REVIEW_FILES = (VIEW, *(REVIEW_ROOT + name for name in (
    "review-instructions.txt", "reviewer-output.json", "review-provenance.json")))
FIXED_OUTPUT = "outputs/saved_source_real_usage_qwen_canary_v1"
MAX_REVIEW_BYTES = 256 * 1024
MAX_CASE_OBSERVATION_BYTES = 512 * 1024
MAX_REQUESTS = 4
USD_LIMIT = Decimal("0.05")
CODE = "ruq-private-sandbox-owner-not-production"
IDENTITY_SEEDS = tuple(dict.fromkeys((*prep.IDENTITY_PATHS,
    ".gitattributes", PROTOCOL, "docs/saved-source-usage.md", "docs/llm-review-policy.md",
    "src/academic_agent/saved_source_real_qwen_canary.py",
    "src/academic_agent/report_evidence_source_locator_qwen_transport.py",
    "tests/test_saved_source_real_qwen_canary.py",
    "web/saved-source-usage/index.html", "web/saved-source-usage/app.js",
    "web/saved-source-usage/accounting.js", "web/saved-source-usage/app.css",
    "web/saved-source-receipts/app.js", "web/saved-source-receipts/result.js",
    "web/saved-source-receipts/app.css")))
DEPENDENCIES = (
    "httpx", "httpcore", "anyio", "certifi", "h11", "idna", "sniffio", "typing-extensions",
    "pydantic", "pydantic-core", "annotated-types", "typing-inspection", "fastapi", "starlette",
    "uvicorn", "click", "annotated-doc", "python-dotenv",
)


class PilotStopped(ValueError):
    """Never print private inputs, filesystem paths, key material or foreign errors."""

    def __init__(self):
        super().__init__("RUQ preparation or execution unavailable; no automatic retry.")


class _ObservationWriteFailed(PilotStopped):
    """An unacknowledged artifact write cannot support a durable case claim."""


def _require(value):
    if not value:
        raise PilotStopped()


def _keys(value, keys):
    _require(type(value) is dict and set(value) == set(keys))


def _hash(value, length=64):
    _require(type(value) is str and re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value) is not None)


def _strings(value):
    _require(type(value) is list and 0 < len(value) <= 64)
    _require(all(type(item) is str and 0 < len(item) <= 8192 and item.strip() for item in value))


def _parse(raw, limit):
    _require(type(raw) is bytes and 0 < len(raw) <= limit)
    return _strict_json(raw.decode("utf-8"))


def _plain(path):
    """Single-owner path checks, not hostile-filesystem race isolation."""
    path.relative_to(ROOT)
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        _require(not stat.S_ISLNK(info.st_mode)
                 and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _read(path, limit):
    _plain(path)
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    _require(0 < len(raw) <= limit)
    return raw


def bridge_packet(raw: bytes, expected_file_sha256: str) -> tuple[dict, dict]:
    """Permit HEAD-context drift only, without weakening the old validator.

    Restoring the old identity on a comparison COPY tests every other byte,
    including raw metadata/provenance and the internal digest. Validating the
    old packet with a patched validator would silently authorize other drift.
    """
    _hash(expected_file_sha256)
    _require(prep._sha(raw) == expected_file_sha256)
    origin = _parse(raw, prep.MAX_PACKET_BYTES)
    _require(raw == prep._dump(origin))
    identity = origin["code_identity"]
    _keys(identity, ("git_head", "working_file_sha256"))
    _hash(identity["git_head"], 40)
    current = prep.build_packet(**prep._inputs(origin))
    prep.validate_packet(current)
    _require(identity["working_file_sha256"] == current["code_identity"]["working_file_sha256"])
    comparison = deepcopy(current)
    comparison["code_identity"] = deepcopy(identity)
    del comparison["packet_sha256"]
    comparison["packet_sha256"] = prep._sha(prep._dump(comparison))
    _require(prep._dump(comparison) == raw)
    return origin, current


def review_bundle_sha256(origin_sha256: str, files: dict[str, bytes]) -> str:
    """Canonical ASCII map: fixed BASENAMES plus origin_packet_file_sha256.

    This digest is private data binding, not the public code-identity digest.
    """
    _hash(origin_sha256)
    _keys(files, [Path(path).name for path in REVIEW_FILES])
    return prep._sha(prep._dump({"origin_packet_file_sha256": origin_sha256,
                                **{name: prep._sha(raw) for name, raw in files.items()}}))


def validate_review(origin, current, origin_sha256, files, expected_bundle_sha256):
    """Bind the returned LLM judgment; quotations are not semantic attestation."""
    _hash(expected_bundle_sha256)
    _require(review_bundle_sha256(origin_sha256, files) == expected_bundle_sha256)
    view = _parse(files["blind-review-view.json"], MAX_REVIEW_BYTES)
    _require(prep._dump(view) == prep._dump(prep.review_view(current)))
    prompt_raw = files["review-instructions.txt"]
    _require(0 < len(prompt_raw) <= MAX_REVIEW_BYTES)
    prompt = prompt_raw.decode("utf-8")
    rubric, separator, data = prompt.partition("DATA:\n")
    _require(separator and rubric.strip() and prep._dump(_parse(data.encode("utf-8"), MAX_REVIEW_BYTES))
             == prep._dump(view))
    output = _parse(files["reviewer-output.json"], MAX_REVIEW_BYTES)
    sidecar = _parse(files["review-provenance.json"], MAX_REVIEW_BYTES)
    _keys(output, ("review_kind", "external_sources_checked", "cases", "overall_limitations"))
    _require(output["review_kind"] == "LLM_title_location_reference_review"
             and output["external_sources_checked"] is False)
    _strings(output["overall_limitations"])
    _require(type(output["cases"]) is list and len(output["cases"]) == 4)
    labels, quote_count = {}, 0
    for row, case in zip(output["cases"], view["cases"], strict=True):
        _keys(row, ("case_id", "doc_id", "disposition", "acceptable_source_ids", "support_status",
                    "rationale", "title_quotes", "near_misses", "limitations"))
        _require((row["case_id"], row["doc_id"]) == (case["case_id"], case["doc_id"]))
        _require(row["disposition"] in {"candidate_set", "no_catalog_fit"} and row["support_status"] == "supported")
        _strings([row["rationale"]])
        _strings(row["limitations"])
        titles = {item["source_id"]: item["title"] for item in case["catalog"]}
        ids = row["acceptable_source_ids"]
        _require(type(ids) is list and all(type(item) is str and item in titles for item in ids))
        _require(len(ids) == len(set(ids)) and bool(ids) == (row["disposition"] == "candidate_set"))
        for name, field in (("title_quotes", "quote"), ("near_misses", "reason")):
            _require(type(row[name]) is list and len(row[name]) <= 64)
            for item in row[name]:
                _keys(item, ("source_id", field))
                _require(type(item["source_id"]) is str and item["source_id"] in titles)
                _strings([item[field]])
                if field == "quote":
                    _require(item[field] in titles[item["source_id"]])
                    quote_count += 1
        labels[row["case_id"]] = list(ids)
    _keys(sidecar, ("schema_version", "status", "completed_at_utc", "origin_git_head",
        "origin_packet_file_sha256", "blind_view_sha256", "prompt_file_sha256",
        "submitted_prompt_utf8_sha256", "review_output_sha256", "provenance", "blinding",
        "mechanical_validation", "draft_comparison", "state_boundaries", "limitations"))
    _require(sidecar["schema_version"] == "ru_reference_review_sidecar_v1"
             and sidecar["status"] == "completed_with_limits"
             and sidecar["origin_git_head"] == origin["code_identity"]["git_head"]
             and sidecar["origin_packet_file_sha256"] == origin_sha256
             and sidecar["blind_view_sha256"] == prep._sha(files["blind-review-view.json"])
             and sidecar["prompt_file_sha256"] == prep._sha(prompt_raw)
             and sidecar["submitted_prompt_utf8_sha256"] == prep._sha(prompt.rstrip().encode("utf-8"))
             and sidecar["review_output_sha256"] == prep._sha(files["reviewer-output.json"]))
    _require(type(sidecar["completed_at_utc"]) is str
             and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", sidecar["completed_at_utc"]))
    datetime.fromisoformat(sidecar["completed_at_utc"].replace("Z", "+00:00"))
    provenance = sidecar["provenance"]
    fixed_provenance = {
        "kind": "LLM_generated_reference_review", "channel": "Codex_subagent",
        "requested_role": "route_reviewer", "configured_model": "gpt-6-astra",
        "configured_reasoning_effort": "high", "effective_backend_metadata": None,
        "effective_backend_metadata_status": "unavailable", "history_forked": False,
        "shared_project_instructions_may_be_present": True, "external_sources_checked": False,
        "tools_requested": False, "not_human_gold": True,
    }
    _keys(provenance, (*fixed_provenance, "agent_id"))
    _strings([provenance["agent_id"]])
    # Canonical comparisons reject bool/int substitution as well as extra claims.
    _require(prep._dump({k: v for k, v in provenance.items() if k != "agent_id"}) == prep._dump(fixed_provenance))
    _require(prep._dump(sidecar["blinding"]) == prep._dump({
        "provided": ["frozen_rubric", "case_id", "document_alias", "question", "complete_visible_source_id_title_catalog"],
        "hidden": ["draft_references", "scripted_selections", "assisted_keywords", "keyword_baseline_outcomes",
                   "saved_text", "full_reports", "run_metadata", "previous_reviews"],
        "comparison_performed": "after_judgment_returned"}))
    _require(prep._dump(sidecar["mechanical_validation"]) == prep._dump({
        "case_order_and_document_match": True, "candidate_ids_exist": True, "duplicate_candidate_ids": False,
        "title_quotes_checked": quote_count, "title_quotes_exact_matches": quote_count, "near_miss_ids_exist": True}))
    drafts = prep._json(prep._inputs(current)["references"], "references")["cases"]
    agreement = sum(set(labels[row["case_id"]]) == set(row["acceptable_source_ids"]) for row in drafts)
    _require(prep._dump(sidecar["draft_comparison"]) == prep._dump({
        "exact_set_agreement": agreement, "cases": 4, "candidate_counts": [len(labels[c]) for c in prep.CASE_IDS],
        "is_accuracy_estimate": False}))
    _require(prep._dump(sidecar["state_boundaries"]) == prep._dump({
        "original_packet_modified": False, "original_reference_review_field": "not_run", "native_efficacy": "not_run",
        "production_activation": False, "project_qwen_api_calls": 0, "project_model_key_reads": 0,
        "codex_review_usage": "not_observed_as_project_API_spend"}))
    _strings(sidecar["limitations"])
    return labels


def _git(*args):
    return subprocess.run(["git", "--no-optional-locks", *args], cwd=ROOT,
                          capture_output=True, check=True, timeout=20).stdout


def identity_paths():
    """Conservative local import closure, including deferred imports and init files.

    Checking just prep.IDENTITY_PATHS misses the current native transport and
    browser assets. No private output or broad repository discovery is needed.
    """
    paths, pending = set(IDENTITY_SEEDS), list(IDENTITY_SEEDS)

    def add_module(name):
        parts = name.split(".")
        if parts[0] not in {"academic_agent", "api"}:
            return
        prefix = Path("src") if parts[0] == "academic_agent" else Path()
        for count in range(1, len(parts) + 1):
            candidate = prefix.joinpath(*parts[:count])
            for path in (candidate.with_suffix(".py"), candidate / "__init__.py"):
                name = path.as_posix()
                if (ROOT / path).is_file() and name not in paths:
                    paths.add(name)
                    pending.append(name)

    while pending:
        name = pending.pop()
        _plain(ROOT / name)
        if name.endswith(".py"):
            for node in ast.walk(ast.parse((ROOT / name).read_text(encoding="utf-8-sig"))):
                if isinstance(node, ast.Import):
                    for item in node.names:
                        add_module(item.name)
                elif isinstance(node, ast.ImportFrom):
                    _require(not node.level)
                    if node.module:
                        add_module(node.module)
                        for item in node.names:
                            add_module(node.module + "." + item.name)
    return tuple(sorted(paths))


def configuration():
    return {"method": METHOD, "model": MODEL, "case_ids": list(prep.CASE_IDS), "doc_ids": list(prep.DOC_IDS),
            "max_requests": MAX_REQUESTS, "usd_limit": str(USD_LIMIT),
            "upfront_reservation_usd": str(MAX_REQUESTS * RESERVATION_USD), "refunds": False,
            "scope": "native_to_ASGI_HTTP_not_native_browser", "production_mounted": False,
            "credential_source": "process_DASHSCOPE_API_KEY_only", "resume": False,
            "price_scope": "frozen_engineering_policy_not_current_price_or_invoice"}


def verify_identity(expected_commit):
    """Source/lock-version check, not binary attestation or model metadata."""
    _hash(expected_commit, 40)
    paths = identity_paths()
    _require(_git("rev-parse", "HEAD").decode("ascii").strip() == expected_commit)
    _require(not _git("status", "--porcelain", "--untracked-files=all", "--", *paths).strip())
    _require((ROOT / ".gitattributes").read_bytes().replace(b"\r\n", b"\n") == b"* text=auto eol=lf\n")
    hashes = {}
    for name in paths:
        raw = (ROOT / name).read_bytes()
        _require(raw.replace(b"\r\n", b"\n") == _git("show", f"{expected_commit}:{name}"))
        hashes[name] = prep._sha(raw)
    locked = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))["package"]
    installed = {name: version(name) for name in DEPENDENCIES}
    _require(all(value in {item.get("version") for item in locked if item["name"] == name}
                 for name, value in installed.items()))
    return {"commit": expected_commit, "working_file_sha256": hashes,
            "runtime": {"python": platform.python_version(), **installed}, "configuration": configuration()}


def preflight(expected_commit, expected_packet_sha256, expected_review_bundle_sha256):
    identity = verify_identity(expected_commit)
    raw = _read(ROOT / PACKET, prep.MAX_PACKET_BYTES)
    origin, current = bridge_packet(raw, expected_packet_sha256)
    files = {Path(name).name: _read(ROOT / name, MAX_REVIEW_BYTES) for name in REVIEW_FILES}
    labels = validate_review(origin, current, expected_packet_sha256, files, expected_review_bundle_sha256)
    _require(current["code_identity"]["git_head"] == expected_commit)
    _require(all(identity["working_file_sha256"][name] == digest for name, digest in
                 current["code_identity"]["working_file_sha256"].items()))
    return {"identity": identity, "origin_packet_file_sha256": expected_packet_sha256,
            "review_bundle_sha256": expected_review_bundle_sha256, "packet": current, "labels": labels}


def _new_bytes(path, raw):
    _plain(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags, 0o600), "wb") as stream:
        _require(stream.write(raw) == len(raw))
        stream.flush()
        os.fsync(stream.fileno())


class _Batch:
    """One exclusive occupied output, all four reservations upfront, no refunds.

    Each one-shot native wrapper still has its own ledger. This outer durable
    fence and the single daily journal prevent per-case construction from
    resetting the aggregate bound. Partial creation remains permanently spent.
    """

    def __init__(self, prepared):
        _require(MAX_REQUESTS == len(prep.CASE_IDS) == 4
                 and 0 < MAX_REQUESTS * RESERVATION_USD < USD_LIMIT == Decimal("0.05"))
        self.root = ROOT / FIXED_OUTPUT
        _plain(self.root)
        self.root.mkdir(exist_ok=False)
        self.rows = [{"case_id": case, "state": "not_run"} for case in prep.CASE_IDS]
        self.entries = 0
        self.selectors = 0
        self.started = 0
        self.events = b""
        self.manifest = {"method": METHOD, "identity": prepared["identity"],
            "origin_packet_file_sha256": prepared["origin_packet_file_sha256"],
            "review_bundle_sha256": prepared["review_bundle_sha256"], "cases": deepcopy(self.rows),
            "batch_reservation_usd": str(MAX_REQUESTS * RESERVATION_USD), "invoice_status": "not_observed",
            "authorization": "operator_asserted_external_grant_not_derived_from_packet"}
        _new_bytes(self.root / "manifest.json", prep._dump(self.manifest))
        _new_bytes(self.root / "batch-events.jsonl", b"")
        self.append({"event": "batch_reserved", "requests": MAX_REQUESTS,
                     "reservation_usd": str(MAX_REQUESTS * RESERVATION_USD)})

    def append(self, value):
        raw = prep._dump(value) + b"\n"
        with (self.root / "batch-events.jsonl").open("r+b") as stream:
            _require(stream.read(len(self.events) + 1) == self.events)
            _require(stream.write(raw) == len(raw))
            stream.flush()
            os.fsync(stream.fileno())
        self.events += raw

    def start(self, index, case, wire):
        _require(index == self.started < MAX_REQUESTS and self.entries == index
                 and all(row["state"] == "passed" for row in self.rows[:index]))
        key = f"v1.{int(time.time())}.{secrets.token_hex(32)}"
        intent = {"case_id": case["case_id"], "doc_id": case["doc_id"], "receipt_key": key,
                  "question_sha256": prep._sha(case["question"].encode("utf-8")),
                  "wire_sha256": prep._sha(wire), "wire_bytes": len(wire),
                  "reservation_usd": str(RESERVATION_USD)}
        _new_bytes(self.root / (case["case_id"] + "-intent.json"), prep._dump(intent))
        self.append({"event": "case_intent", **intent})
        self.started += 1
        return key

    def before_http(self, index, wire, expected):
        _require(wire == expected and self.entries == index < self.started <= MAX_REQUESTS)
        self.append({"event": "native_entry", "case_id": prep.CASE_IDS[index],
                     "wire_sha256": prep._sha(wire), "wire_bytes": len(wire)})
        self.entries += 1


@contextmanager
def _isolated_runtime(root):
    # Dedicated CLI process only. This scope never installs a production app,
    # reads its output tree, borrows its credentials or clears its durable quota.
    # State remains shared across ALL cases; putting this inside _case resets it.
    from api import access, runs
    _require(not runs._registry and not runs._inline_paid_operations and not runs._stop_claims)
    with ExitStack() as stack:
        for name in ("_registry", "_stop_claims", "_inline_paid_operations", "_daily_counts"):
            stack.enter_context(patch.object(runs, name, {}))
        for target, name, value in ((runs, "_daily_date", None), (runs, "DEFAULT_OUTPUT_ROOT", root),
                (runs, "MAX_CONCURRENT", 1), (runs, "DAILY_CAP", 4), (access, "ACCESS_CODE", CODE),
                (access, "ACCESS_CODES", None), (access, "ADMIN_CODE", None)):
            stack.enter_context(patch.object(target, name, value))
        yield
        _require(runs.active_paid_operation_count() == 0)


def _check_copies(packet, root):
    inputs = prep._inputs(packet)
    for doc_id, doc in packet["prepared"]["documents"].items():
        _require(_read(root / doc["sandbox_alias"] / "validated_sources.json", prep.RAW_LIMITS["sources"])
                 == inputs["documents"][doc_id]["sources"])


def _native_gate(selector, wire, accounting):
    from academic_agent.saved_source_usage import ReportedUsage, decimal_usd, estimated_usd
    ledger = selector._ledger
    raw = _read(ledger.output_dir / "events.jsonl", 96 * 1024)
    events = [_parse(line, 96 * 1024) for line in raw.splitlines()]
    _require([row["event"] for row in events] == ["request_reserved", "request_finished"])
    first, last = events
    for event in events:
        _require(event["request_id"] == 1 and type(event["request_id"]) is int and event["case_id"] is None
                 and _encoded(event["request"]) == wire and event["request_sha256"] == prep._sha(wire)
                 and event["reservation_usd"] == str(RESERVATION_USD))
    _require(first["usage_status"] == "unknown" and last["usage_status"] == "complete"
             and last["provider_response_received"] is True and last["protocol_accepted"] is True
             and last["response_model_matches_authorized"] is True and last["error"] is None
             and ledger.pending is None and ledger.stop_reason is None and len(ledger.records) == 1
             and prep._dump(last) == prep._dump({"event": "request_finished", **ledger.records[0]}))
    usage = ReportedUsage.model_validate(last["reported_usage"])
    _require(accounting["usage"] == {"status": "reported_complete", **usage.model_dump()})
    _require(accounting["publication_state"] == "sealed" and accounting["dispatch_state"] == "response_received"
             and accounting["native_journal_state"] == "complete" and accounting["model_matches_authorized"] is True
             and accounting["fault_codes"] == [])
    _require(accounting["cost"] == {"currency": "USD", "status": "estimated",
        "estimated_usd": estimated_usd(usage), "reservation_usd": decimal_usd(RESERVATION_USD),
        "price_policy_id": "locator_qwen_frozen_rates_v1", "invoice_status": "not_observed"})
    _require(Decimal(last["estimated_usd"]) == Decimal(accounting["cost"]["estimated_usd"]) <= RESERVATION_USD)


def _record_http(progress, response, lane, batch, case_id, key, receipt_key):
    """Only two bounded app replies, never raw provider replies or exceptions.

    Invalid application replies retain status/length/classification only. A
    later GET must never be used to invent an unreceived POST acknowledgement.
    Each captured phase is exclusively written before the next observation.
    """
    from academic_agent.report_evidence_qwen_transport import _contains_secret
    from academic_agent.saved_source_usage import UsageProjectionV1
    from api import access, runs
    from api.saved_source_receipt_app import MAX_RESPONSE_BYTES, _wire_reply
    from api.saved_source_usage_app import CONTRACT
    _require(lane in {"post", "get"})
    counts = {"native_entries": batch.entries, "selector_entries": batch.selectors,
              "paid_admissions": runs._daily_counts.get(access.owner_id(CODE))}
    item = {"state": "lost_ack" if lane == "post" and progress["observations"]["lost_ack"] else "not_received",
            "counts": counts}
    if response is not None:
        item.update(state="received_invalid", http_status=response.status_code, response_bytes=len(response.content))
        try:
            value = _parse(response.content, MAX_RESPONSE_BYTES)
            _keys(value, ("contract", "receipt", "accounting"))
            _require(value["contract"] == CONTRACT and not _contains_secret(value, key))
            receipt = value["receipt"]
            legacy = {k: v for k, v in receipt.items() if k != "receipt_key_sha256"}
            _require(dump_equal(receipt, json.loads(_wire_reply(legacy, receipt_key).body)))
            checked = UsageProjectionV1.model_validate(value["accounting"]).model_dump(mode="json")
            _require(dump_equal(checked, value["accounting"]))
            _require(all(checked[name] == receipt[name] for name in ("receipt_key_sha256", "run_id", "expires_at")))
            item.update(state="received", payload=value)
        except Exception:  # noqa: BLE001 -- invalid/untrusted replies get no body or foreign error text on disk.
            pass
    progress["observations"][lane] = item
    progress["observations"]["publication"] = "complete_for_captured_observations"
    try:
        _new_bytes(batch.root / (case_id + "-http-" + lane + ".json"),
                   prep._dump(progress["observations"], MAX_CASE_OBSERVATION_BYTES))
    except Exception:  # noqa: BLE001 -- failed fsync/partial output stays occupied, not a successful publication.
        progress["observations"]["publication"] = "failed"
        raise _ObservationWriteFailed() from None


def dump_equal(first, second):
    """Canonical equality preserves strict bool/int distinctions in captured replies."""
    return prep._dump(first, MAX_CASE_OBSERVATION_BYTES) == prep._dump(second, MAX_CASE_OBSERVATION_BYTES)


def _case(prepared, batch, case, index, key, progress):
    import httpx
    from fastapi.testclient import TestClient
    from academic_agent.report_evidence_source_locator import LocatorResult
    from academic_agent.saved_source_accounted_qwen import AccountedQwenSelector
    from academic_agent.saved_source_loader import SavedSourceLoader
    from academic_agent.saved_source_usage import UsageProjectionV1
    from api import access, runs, saved_source_controller
    from api.saved_source_receipt_app import MAX_RESPONSE_BYTES, _REPLY_FIELDS
    from api.saved_source_usage_app import CONTRACT, GET_PATH, POST_PATH, create_saved_source_usage_app

    packet = prepared["packet"]
    doc = packet["prepared"]["documents"][case["doc_id"]]
    wire = prep._wire(doc, case["question"])
    receipt_key = batch.start(index, case, wire)
    loader = SavedSourceLoader(batch.root)
    snapshot = loader(doc["sandbox_alias"])
    _require(snapshot.model_dump(mode="json") == doc["snapshot"])
    selector = AccountedQwenSelector(key, snapshot=snapshot, question=case["question"],
                                     ledger_dir=batch.root / (case["case_id"] + "-native"))
    original_post, original_select = selector._native._post, selector.select

    async def audited_post(body, observation):
        batch.before_http(index, body, wire)
        return await original_post(body, observation)

    def select(*args, **kwargs):
        _require(batch.selectors == index)
        batch.selectors += 1
        return original_select(*args, **kwargs)

    selector._native._post, selector.select = audited_post, select
    app = create_saved_source_usage_app(load_snapshot=loader, journal_root=batch.root,
                                        accounted_selector=selector, selector_identity=METHOD)
    observations = []
    observe = saved_source_controller.SavedSourceController._observe

    def observed(self, *args, **kwargs):
        reply = observe(self, *args, **kwargs)
        observations.append(deepcopy(reply))
        return reply

    headers = {"Idempotency-Key": receipt_key, "X-Access-Code": CODE}
    responses = []
    lost_ack = False
    with patch.object(saved_source_controller.SavedSourceController, "_observe", observed), TestClient(app) as client:
        # Exactly one POST. A lost acknowledgement can only lead to one GET,
        # never POST replay, a new receipt, a new selector or a polling loop.
        post = None
        try:
            post = client.post(POST_PATH.replace("{run_id}", doc["sandbox_alias"]),
                               headers=headers, json={"question": case["question"]})
            responses.append((post, 0))
        except (httpx.TransportError, TimeoutError):
            lost_ack = True
            progress["observations"]["lost_ack"] = True
        _record_http(progress, post, "post", batch, case["case_id"], key, receipt_key)
        # Recording an invalid reply is evidence, not acceptance. Python dict
        # equality treats True == 1; the typed capture gate must also block use.
        _require(progress["observations"]["post"]["state"] == ("lost_ack" if lost_ack else "received"))
        _require(post is None or post.status_code == 200)
        progress["failed_gate"] = "accounting_gate"
        before = (batch.entries, batch.selectors, runs._daily_counts.get(access.owner_id(CODE)))
        _require(before == (index + 1, index + 1, index + 1))
        progress["failed_gate"] = "http_envelope"
        replay = client.get(GET_PATH, headers=headers)
        _record_http(progress, replay, "get", batch, case["case_id"], key, receipt_key)
        _require(progress["observations"]["get"]["state"] == "received")
        _require(replay.status_code == 200)
        responses.append((replay, 1))
        progress["failed_gate"] = "accounting_gate"
        _require(before == (batch.entries, batch.selectors, runs._daily_counts.get(access.owner_id(CODE))))
    _require(len(observations) == 2 and runs.active_paid_operation_count() == 0)
    payloads = []
    for response, ordinal in responses:
        progress["failed_gate"] = "http_envelope"
        _require(len(response.content) <= MAX_RESPONSE_BYTES)
        value = _parse(response.content, MAX_RESPONSE_BYTES)
        _keys(value, ("contract", "receipt", "accounting"))
        receipt, accounting = value["receipt"], value["accounting"]
        _keys(receipt, _REPLY_FIELDS | {"receipt_key_sha256"})
        observed_value = observations[ordinal]
        _require(value["contract"] == CONTRACT
                 and dump_equal(receipt, {**{k: v for k, v in observed_value.items() if k != "accounting"},
                                         "receipt_key_sha256": prep._sha(receipt_key.encode())})
                 and dump_equal(accounting, observed_value["accounting"]))
        progress["failed_gate"] = "accounting_gate"
        _require(UsageProjectionV1.model_validate(accounting).model_dump(mode="json") == accounting)
        _require(receipt["state"] == "completed" and receipt["delivery"] == "available"
                 and receipt["admission_state"] == "admitted" and receipt["error_code"] is None
                 and receipt["provider_usage"] == receipt["provider_cost"] == "not_observed")
        _native_gate(selector, wire, accounting)
        payloads.append(value)
    progress["failed_gate"] = "http_envelope"
    first, second = observations
    _require(first["accounting"] == second["accounting"] and first["result"] == second["result"])
    result = second["result"]
    _require(LocatorResult.model_validate(result).model_dump(mode="json") == result)
    ids = prepared["labels"][case["case_id"]]
    choice = result["source"]["source_id"] if result["source"] else None
    _require(result["callback_entries"] == 1 and result["read_attempts"] == result["read_completed"] == int(choice is not None))
    _require(second == {**first, "delivery_snapshot_reads": 1, "delivery_source_reads": int(choice is not None)}
             and first["delivery_snapshot_reads"] == first["delivery_source_reads"] == 0)
    progress["failed_gate"] = "reference_gate"
    if ids:
        _require(choice in ids and result["state"] == "excerpt" and result["reason"] == "saved_text")
        saved = next(item for item in snapshot.sources if item.source_id == choice)
        _require(result["saved_text"]["text"] == saved.summary and result["saved_text"]["end"] == saved.stored_length)
    else:
        _require(result["state"] == "declined" and result["reason"] == "selector_declined"
                 and result["source"] is result["saved_text"] is None)
    return {"case_id": case["case_id"], "state": "passed", "post": None if lost_ack else payloads[0],
            "get": payloads[-1], "lost_ack": lost_ack, "wire_sha256": prep._sha(wire), "wire_bytes": len(wire),
            "native_entries": 1, "selector_entries": 1, "paid_admissions": 1,
            "observations": deepcopy(progress["observations"]),
            "reference_agreement": "fallible_LLM_title_reference_not_accuracy"}


def _execute(prepared, batch, key):
    from api import access
    packet = prepared["packet"]
    inputs = prep._inputs(packet)
    with _isolated_runtime(batch.root):
        for doc_id, doc in packet["prepared"]["documents"].items():
            folder = batch.root / doc["sandbox_alias"]
            folder.mkdir()
            _new_bytes(folder / ".owner", access.owner_id(CODE).encode("utf-8"))
            _new_bytes(folder / "validated_sources.json", inputs["documents"][doc_id]["sources"])
        for index, case in enumerate(packet["prepared"]["cases"]):
            progress = {"failed_gate": "http_envelope", "observations": {
                "post": {"state": "not_received"}, "get": {"state": "not_received"},
                "lost_ack": False, "publication": "no_observation"}}
            try:
                _check_copies(packet, batch.root)
                prep.validate_packet(packet)
                _require(verify_identity(prepared["identity"]["commit"]) == prepared["identity"])
                row = _case(prepared, batch, case, index, key, progress)
                _check_copies(packet, batch.root)
                batch.append({"event": "case_passed", "case_id": case["case_id"]})
                _new_bytes(batch.root / (case["case_id"] + "-result.json"), prep._dump(row))
                batch.rows[index] = row
            except _ObservationWriteFailed:
                # Do not write a success/failure artifact claiming a reply was
                # durably recorded after its observation publication failed.
                raise
            except Exception:  # noqa: BLE001 -- private/provider exceptions never become public diagnostics.
                batch.rows[index] = {"case_id": case["case_id"], "state": "failed", "reason": "pilot_gate_failed",
                                     **deepcopy(progress)}
                _new_bytes(batch.root / (case["case_id"] + "-failure.json"),
                           prep._dump(batch.rows[index], MAX_CASE_OBSERVATION_BYTES))
                # If persistence itself fails, leave the occupied partial batch;
                # do not manufacture a summary or free a reservation for retry.
                batch.append({"event": "case_failed", "case_id": case["case_id"]})
                break
        _check_copies(packet, batch.root)
    _require(verify_identity(prepared["identity"]["commit"]) == prepared["identity"])
    summary = {"method": METHOD, "state": "passed" if all(row["state"] == "passed" for row in batch.rows) else "failed",
               "cases": batch.rows, "native_entries": batch.entries, "selector_entries": batch.selectors,
               "batch_reservation_usd": str(MAX_REQUESTS * RESERVATION_USD), "invoice_status": "not_observed",
               "scope": "native_to_ASGI_HTTP_not_native_browser", "user_benefit": "not_assessed",
               "production_activation": False}
    _new_bytes(batch.root / "summary.json", prep._dump(summary))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-commit")
    parser.add_argument("--expected-packet-sha256")
    parser.add_argument("--expected-review-bundle-sha256")
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--authorization-confirmed", action="store_true")
    args = parser.parse_args(argv)
    try:
        commit = args.expected_commit or _git("rev-parse", "HEAD").decode("ascii").strip()
        identity = verify_identity(commit)
        prepared = None
        if args.expected_packet_sha256 or args.expected_review_bundle_sha256:
            _require(args.expected_packet_sha256 and args.expected_review_bundle_sha256 and args.expected_commit)
            prepared = preflight(commit, args.expected_packet_sha256, args.expected_review_bundle_sha256)
        if not args.native:
            # Only public source identity, never private packet/review hashes,
            # titles, paths, labels, result data or even raw exception messages.
            print(json.dumps({"state": "identity_only", "identity_sha256": prep._sha(prep._dump(identity))}))
            return 0
        _require(args.authorization_confirmed and args.expected_commit and prepared is not None)
        batch = _Batch(prepared)
        # No dotenv, key loader, alternate variable, endpoint or CLI key option.
        # Even key failure consumes the freshly fsynced batch claim permanently.
        from academic_agent.report_evidence_qwen_transport import validate_key
        key = os.environ.get("DASHSCOPE_API_KEY")
        validate_key(key)
        result = _execute(prepared, batch, key)
        print(json.dumps({"state": result["state"]}))
        return 0 if result["state"] == "passed" else 2
    except Exception:  # noqa: BLE001 -- CLI must not reveal private paths, bytes, provider bodies or secrets.
        print('{"state":"unavailable"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
