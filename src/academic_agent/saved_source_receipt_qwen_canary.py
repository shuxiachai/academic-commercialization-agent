"""RQ's fixed, parent-operated browser canary; identity-only unless authorized.

No production app, credential discovery, Playwright or process-global patches
are imported/installed by importing this module. The adapter owns aggregate
admission; this runner owns source identity, delivery checks and publication.
"""

from __future__ import annotations

import argparse
import ast
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import threading
import tomllib
from unittest.mock import patch

from academic_agent import report_evidence_source_locator as locator
from academic_agent import report_evidence_source_locator_qwen_transport as native
from academic_agent.report_evidence_catalog_followup import build_catalog
from academic_agent.report_evidence_followup import _strict_json
from academic_agent.report_evidence_qwen_canary import CanaryStopped, _encoded
from academic_agent.report_evidence_qwen_transport import validate_key
from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, SnapshotSource

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_IDENTITY = "saved_source_receipt_qwen_canary_v1"
FIXTURE = "tests/fixtures/saved_source_receipt_qwen_canary.json"
FIXTURE_SHA256 = "b82f67446853685195d03b8e6e9f0a99c5aa11705f10752420ca558907f06216"
PROTOCOL = "docs/prereg-2026-09-20-saved-source-receipt-qwen-canary.md"
FIXED_OUTPUT = "outputs/saved_source_receipt_qwen_canary_v1"
CASE_IDS = ("RQ01", "RQ02")
CODE = "synthetic-receipt-qwen-local-only-code"
SELECTOR_IDENTITY = PROTOCOL_IDENTITY + ":unchanged_locator_qwen_v1"
IDENTITY_SEEDS = (
    ".gitattributes", ".github/workflows/test.yml", "pyproject.toml", "uv.lock", "AGENTS.md", FIXTURE, PROTOCOL,
    "docs/saved-source-paid-controller.md", "docs/saved-source-receipt-entry.md",
    "docs/prereg-2026-09-18-source-locator-qwen-transport.md",
    "saved_source_receipt_qwen_canary.py",
    "src/academic_agent/saved_source_receipt_qwen_canary.py",
    "src/academic_agent/saved_source_receipt_qwen_adapter.py",
    "src/academic_agent/saved_source_loader.py",
    "api/saved_source_receipt_app.py", "e2e/saved_source_receipt_qwen_canary.py",
    "tests/test_saved_source_receipt_qwen_canary.py",
    "tests/test_saved_source_receipt_qwen_integration.py",
    "tests/test_saved_source_receipt_qwen_adapter.py",
    "web/saved-source-receipts/index.html", "web/saved-source-receipts/app.js",
    "web/saved-source-receipts/result.js", "web/saved-source-receipts/app.css",
)
DEPENDENCIES = (
    "httpx", "httpcore", "anyio", "certifi", "h11", "idna", "sniffio", "typing-extensions",
    "pydantic", "pydantic-core", "annotated-types", "typing-inspection", "fastapi", "starlette",
    "uvicorn", "click", "annotated-doc",
)
BROWSER_DEPENDENCIES = ("playwright", "pyee", "greenlet")
_SAFE_REASONS = native._SAFE_ERRORS | frozenset({
    "source_identity_mismatch", "committed_content_mismatch", "runtime_identity_changed",
    "fixture_identity_mismatch", "fixture_invalid_or_unavailable", "invalid_expected_commit",
    "fixture_authorization_mismatch", "identity_check_unavailable", "installed_dependency_mismatch",
    "browser_dependency_missing", "unsupported_text_normalization", "indirect_path_rejected",
    "invalid_output_destination", "output_creation_failed_or_occupied", "invalid_dedicated_key",
    "authorization_required", "case_execution_failed", "native_audit_failed", "http_contract_failed",
    "reference_mismatch", "replay_failed", "browser_delivery_failed", "source_binding_failed",
    "actual_thread_drain_failed", "network_boundary_failed", "browser_runtime_failed",
    "batch_failed", "persistence_failed",
})


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_reason(exc, fallback="case_execution_failed"):
    # Never stringify provider/Playwright/filesystem exceptions or their chains.
    if type(exc) is CanaryStopped and len(exc.args) == 1:
        reason = exc.args[0]
        if type(reason) is str and reason in _SAFE_REASONS:
            return reason
    return fallback


def require(condition, reason):
    if not condition:
        raise CanaryStopped(reason)


def snapshot_for(case):
    return ReportEvidenceSnapshot(report_ref=case["run_id"], sources=tuple(
        SnapshotSource(**source) for source in case["sources"]))


def load_cases():
    try:
        raw = (ROOT / FIXTURE).read_bytes()
        require(digest(raw) == FIXTURE_SHA256, "fixture_identity_mismatch")
        data = _strict_json(raw.decode("utf-8"))
        require(type(data) is dict and set(data) == {"schema_version", "protocol_identity", "scope", "cases"}
                and type(data["schema_version"]) is int and data["schema_version"] == 1
                and data["protocol_identity"] == PROTOCOL_IDENTITY
                and data["scope"] == "fictional_development_controls_not_unseen_or_human_gold"
                and type(data["cases"]) is list, "fixture_invalid_or_unavailable")
        require(tuple(row["case_id"] for row in data["cases"]) == CASE_IDS, "fixture_invalid_or_unavailable")
        references = (("A12", "excerpt", "saved_text", 1, 1),
                      (None, "declined", "selector_declined", 0, 0))
        run_ids = ("20260920T000000Z-" + "a" * 32, "20260920T000001Z-" + "b" * 32)
        for case, reference, run_id in zip(data["cases"], references, run_ids, strict=True):
            require(set(case) == {"case_id", "run_id", "question", "sources", "reference"}
                    and case["run_id"] == run_id and type(case["question"]) is str
                    and 1 <= len(case["question"]) <= 4096 and case["question"].strip()
                    and len(case["sources"]) == 3, "fixture_invalid_or_unavailable")
            fields = ("source_id", "state", "reason", "read_attempts", "read_completed")
            require(set(case["reference"]) == set(fields)
                    and tuple(case["reference"][key] for key in fields) == reference
                    and all(set(source) == set(SnapshotSource.model_fields) for source in case["sources"]),
                    "fixture_invalid_or_unavailable")
            snapshot = snapshot_for(case)
            catalog = build_catalog(snapshot)
            require(not catalog["omitted_count"] and not catalog["title_truncation_count"]
                    and all(source.stored_length <= 1500 for source in snapshot.sources),
                    "fixture_invalid_or_unavailable")
        return tuple(data["cases"])
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise CanaryStopped("fixture_invalid_or_unavailable") from None


def plain_path(path):
    path.relative_to(ROOT)
    for current in reversed((path, *path.parents)):
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode)
                and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                "indirect_path_rejected")


def _git(*arguments):
    return subprocess.run(["git", "--no-optional-locks", *arguments], cwd=ROOT,
                          capture_output=True, check=True, timeout=20).stdout


def identity_paths():
    """Static local-import closure, including deferred imports, without execution.

    Resolve only project namespaces. TYPE_CHECKING-only imports cannot execute;
    every other branch/function import is conservatively included. Package init
    files are included too. No broad repository or private-output scan occurs.
    """
    paths, pending = set(IDENTITY_SEEDS), list(IDENTITY_SEEDS)

    def add_module(name):
        parts = name.split(".")
        if parts[0] not in {"academic_agent", "api", "e2e"}:
            return
        prefix = Path("src") if parts[0] == "academic_agent" else Path()
        for size in range(1, len(parts) + 1):
            candidate = prefix.joinpath(*parts[:size])
            for path in (candidate.with_suffix(".py"), candidate / "__init__.py"):
                rel = path.as_posix()
                if (ROOT / path).is_file() and rel not in paths:
                    paths.add(rel)
                    pending.append(rel)

    class Imports(ast.NodeVisitor):
        def visit_If(self, node):
            test = node.test
            if ((isinstance(test, ast.Name) and test.id == "TYPE_CHECKING")
                    or (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")):
                for child in node.orelse:
                    self.visit(child)
            else:
                self.generic_visit(node)

        def visit_Import(self, node):
            for item in node.names:
                add_module(item.name)

        def visit_ImportFrom(self, node):
            require(not node.level, "identity_check_unavailable")
            if node.module:
                add_module(node.module)
                for item in node.names:
                    add_module(node.module + "." + item.name)

    while pending:
        name = pending.pop()
        plain_path(ROOT / name)
        if name.endswith(".py"):
            Imports().visit(ast.parse((ROOT / name).read_text(encoding="utf-8-sig")))
    return tuple(sorted(paths))


def configuration():
    return {"protocol_identity": PROTOCOL_IDENTITY, "case_ids": list(CASE_IDS),
            "fixed_output": FIXED_OUTPUT, "max_requests": 2, "usd_soft_limit": "0.05",
            "two_request_reservation_usd": "0.022298624", "first_failure_stops_batch": True,
            "resume": False, "credential_source": "process_DASHSCOPE_API_KEY_only",
            "transport": native.locator_qwen_configuration(),
            "browser": "actual_chromium_loopback_current_receipt_factory",
            "price_scope": "frozen_conservative_estimate_not_invoice",
            "wire_accounting": "provider_usage_and_cost_remain_not_observed"}


def verify_identity(expected_commit, expected_fixture_sha256, *, require_browser=False):
    """Read-only blob/disk/version binding, not binary/package attestation."""
    require(type(expected_commit) is str and re.fullmatch(r"[0-9a-f]{40}", expected_commit),
            "invalid_expected_commit")
    require(expected_fixture_sha256 == FIXTURE_SHA256, "fixture_authorization_mismatch")
    try:
        paths = identity_paths()
        head = _git("rev-parse", "--verify", "HEAD").decode("ascii").strip()
        require(head == expected_commit and not _git(
            "status", "--porcelain", "--untracked-files=all", "--", *paths).strip(), "source_identity_mismatch")
        disk, committed = {}, {}
        for name in paths:
            raw = (ROOT / name).read_bytes()
            blob = _git("show", f"{head}:{name}")
            require(raw.replace(b"\r\n", b"\n") == blob, "committed_content_mismatch")
            disk[name], committed[name] = digest(raw), digest(blob)
        require((ROOT / ".gitattributes").read_bytes().replace(b"\r\n", b"\n") == b"* text=auto eol=lf\n",
                "unsupported_text_normalization")
        load_cases()
        locked = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))["package"]
        installed = {name: version(name) for name in DEPENDENCIES}
        for name in BROWSER_DEPENDENCIES:
            try:
                installed[name] = version(name)
            except PackageNotFoundError:
                require(not require_browser, "browser_dependency_missing")
                installed[name] = None
        require(all(value is None or value in {row.get("version") for row in locked if row["name"] == name}
                    for name, value in installed.items()), "installed_dependency_mismatch")
        config = configuration()
        return {"protocol_identity": PROTOCOL_IDENTITY, "commit": head, "fixture_sha256": FIXTURE_SHA256,
                "disk_sha256": disk, "committed_sha256": committed,
                "comparison": "CRLF_to_LF_for_fixed_text_paths_only",
                "runtime": {"python": platform.python_version(), **installed},
                "configuration": config, "configuration_sha256": digest(_encoded(config))}
    except (OSError, subprocess.SubprocessError, PackageNotFoundError, ValueError, TypeError, KeyError, SyntaxError):
        raise CanaryStopped("identity_check_unavailable") from None


def validate_output():
    try:
        output = ROOT / FIXED_OUTPUT
        plain_path(output)
        require(not os.path.lexists(output), "output_creation_failed_or_occupied")
        require(output.parent.is_dir(), "invalid_output_destination")
        return output
    except (OSError, ValueError, TypeError):
        raise CanaryStopped("invalid_output_destination") from None


def read_dedicated_key():
    key = os.environ.get("DASHSCOPE_API_KEY")
    validate_key(key)
    return key


def bindings_for(cases):
    from academic_agent.saved_source_receipt_qwen_adapter import CaseBinding

    return tuple(CaseBinding(case["case_id"], case["run_id"], snapshot_for(case),
                             case["question"], SELECTOR_IDENTITY) for case in cases)


def batch_manifest(bindings, identity):
    return {"schema_version": 1, "fixture_sha256": FIXTURE_SHA256,
            "source_identity_sha256": digest(_encoded(identity)),
            "cases": [binding.manifest_entry() for binding in bindings]}


@contextmanager
def without_provider_environment():
    """Keep the explicit Python key out of local driver/browser child environments.

    This scope must enclose the whole browser/driver/controller lifetime. Only
    this one environment name changes; unrelated Git/platform settings survive.
    """
    missing = object()
    previous = os.environ.pop("DASHSCOPE_API_KEY", missing)
    try:
        yield
    finally:
        if previous is missing:
            os.environ.pop("DASHSCOPE_API_KEY", None)
        else:
            os.environ["DASHSCOPE_API_KEY"] = previous


@contextmanager
def isolated_runtime(root, cases):
    """Reversible synthetic single-process state; never production output/reset.

    Controller leases must physically drain before patches are restored. This
    context must surround the complete server lifespan, including failure paths.
    """
    from academic_agent.saved_source_loader import SavedSourceLoader
    from academic_agent.saved_source_receipt_qwen_adapter import atomic_write_once

    with ExitStack() as stack:
        # Prevent api.access's first import from reading an operator identity.
        stack.enter_context(patch.dict(os.environ, {"ACCESS_CODE": CODE, "ACCESS_CODES": "",
                                                   "ACCESS_CODE_ADMIN": ""}))
        from api import access, runs

        require(not runs._registry and not runs._stop_claims and not runs._inline_paid_operations,
                "actual_thread_drain_failed")
        root.mkdir(exist_ok=False)
        for name, value in {"DEFAULT_OUTPUT_ROOT": root, "_registry": {}, "_stop_claims": {},
                            "_inline_paid_operations": {}, "_daily_counts": {}, "_daily_date": None,
                            "MAX_CONCURRENT": 1, "DAILY_CAP": 2}.items():
            stack.enter_context(patch.object(runs, name, value))
        for name, value in {"ACCESS_CODE": CODE, "ACCESS_CODES": None, "ADMIN_CODE": None}.items():
            stack.enter_context(patch.object(access, name, value))
        for case in cases:
            folder = root / case["run_id"]
            folder.mkdir()
            registry = {name + "_sources": [] for name in ("academic", "patent", "market")}
            for row in case["sources"]:
                saved = {key: value for key, value in row.items() if key not in {"group", "summary", "origin"}}
                saved.update(evidence_summary=row["summary"], summary_source=row["origin"])
                registry[row["group"] + "_sources"].append(saved)
            atomic_write_once(folder / "validated_sources.json", registry)
            with (folder / ".owner").open("x", encoding="ascii", newline="") as stream:
                stream.write(access.owner_id(CODE))
                stream.flush()
                os.fsync(stream.fileno())
        loader = SavedSourceLoader(root)
        for case in cases:
            require(loader(case["run_id"]) == snapshot_for(case), "source_binding_failed")
        try:
            yield loader, access.owner_id(CODE), runs
        finally:
            # Never reset globals beneath an actual operation thread.
            for token in tuple(runs._inline_paid_operations):
                thread = getattr(token, "thread", None)
                if thread is not None:
                    thread.join()
            require(runs.active_paid_operation_count() == 0, "actual_thread_drain_failed")


class CaseExecution:
    """Observe real callback/read seams without substituting successful work."""

    def __init__(self, binding, selector, loader):
        self.binding, self.selector, self.loader = binding, selector, loader
        self.threads, self.callbacks, self.local_reads, self.delivery_reads = [], [], [], []

    def load(self, run_id):
        require(run_id == self.binding.run_id, "source_binding_failed")
        snapshot = self.loader(run_id)
        require(snapshot == self.binding.snapshot, "source_binding_failed")
        return snapshot

    def callback(self, request, /):
        self.threads.append(threading.current_thread())
        self.callbacks.append(digest(_encoded(request)))
        return self.selector(request)

    @contextmanager
    def observe_reads(self):
        from api import saved_source_controller as controller

        real_local, real_delivery = locator.read_source, controller.read_source

        def observed(real, target, *args, **kwargs):
            target.append({"snapshot_hash": args[0].snapshot_hash, "arguments": list(args[1:]),
                           "completed": False})
            value = real(*args, **kwargs)
            target[-1].update(completed=True, result_sha256=digest(_encoded(value)))
            return value

        with patch.object(locator, "read_source", lambda *a, **k: observed(real_local, self.local_reads, *a, **k)), \
                patch.object(controller, "read_source", lambda *a, **k: observed(real_delivery, self.delivery_reads, *a, **k)):
            yield

    def drain(self):
        for thread in self.threads:
            thread.join()
        require(all(not thread.is_alive() for thread in self.threads), "actual_thread_drain_failed")


def audit_http(case, execution, post_raw, get_raw, receipt_key):
    """Reconcile all fourteen wire fields, original facts and actual replay reads."""
    from api.saved_source_receipt_app import _wire_reply

    post, replay = (_strict_json(raw.decode("utf-8")) for raw in (post_raw, get_raw))
    for payload, raw in ((post, post_raw), (replay, get_raw)):
        require(type(payload) is dict and len(payload) == 14
                and payload.get("receipt_key_sha256") == digest(receipt_key.encode("ascii")),
                "http_contract_failed")
        body = {key: value for key, value in payload.items() if key != "receipt_key_sha256"}
        require(_wire_reply(body, receipt_key, run_id=case["run_id"]).body == raw, "http_contract_failed")
        require(payload["state"] == "completed" and payload["delivery"] == "available"
                and payload["admission_state"] == "admitted"
                and payload["provider_usage"] == payload["provider_cost"] == "not_observed",
                "http_contract_failed")
    result = post["result"]
    require(replay["result"] == result and post["delivery_snapshot_reads"] == post["delivery_source_reads"] == 0
            and replay["delivery_snapshot_reads"] == 1, "replay_failed")
    require(len(execution.callbacks) == result["callback_entries"] == 1
            and execution.callbacks[0] == execution.binding.manifest_entry()["callback_sha256"],
            "native_audit_failed")
    require(result["read_attempts"] == len(execution.local_reads)
            and result["read_completed"] == sum(row["completed"] for row in execution.local_reads)
            and replay["delivery_source_reads"] == len(execution.delivery_reads), "replay_failed")
    source, saved = result["source"], result["saved_text"]
    if source is not None:
        original = next(row for row in execution.binding.snapshot.sources if row.source_id == source["source_id"])
        require(source["snapshot_hash"] == execution.binding.snapshot.snapshot_hash
                and source["source_hash"] == execution.binding.snapshot.source_hash(original), "source_binding_failed")
        if saved is not None:
            require(saved["text"] == original.summary
                    and saved["text_sha256"] == digest(original.summary.encode("utf-8")), "source_binding_failed")
        require(len(execution.local_reads) == len(execution.delivery_reads) == 1
                and execution.local_reads == execution.delivery_reads, "replay_failed")
    else:
        require(not execution.local_reads and not execution.delivery_reads, "replay_failed")
    audit = execution.selector.audit()
    require(audit["callback_entries"] == audit["native_http_entries"] == audit["native_transport_entries"] == 1,
            "native_audit_failed")
    require(audit["callback_sha256"] == execution.callbacks[0], "native_audit_failed")
    selected = audit["selection"]
    require(selected is not None and selected["source_id"] == (source["source_id"] if source else None),
            "native_audit_failed")
    require((selected["kind"] == "read_source" and source is not None)
            or (selected["kind"] == "decline" and result["reason"] == "selector_declined")
            or (selected["kind"] == "refusal" and result["reason"] == "selector_refused"), "native_audit_failed")
    # Mechanical delivery is established before comparing frozen development labels.
    reference = case["reference"]
    observed = {"source_id": source["source_id"] if source else None,
                **{key: result[key] for key in ("state", "reason", "read_attempts", "read_completed")}}
    return {"mechanical_passed": True, "reference_passed": observed == reference,
            "result": deepcopy(result), "result_sha256": digest(locator.render_locator_result(
                locator.LocatorResult.model_validate(result)).encode("ascii")),
            "post_sha256": digest(post_raw), "get_sha256": digest(get_raw),
            "receipt_key_sha256": post["receipt_key_sha256"], "replay_passed": True,
            "wire_field_count": len(post), "native_audit": audit,
            "local_reads": deepcopy(execution.local_reads), "delivery_reads": deepcopy(execution.delivery_reads)}


def audit_native_journal(binding, ledger):
    """A memory record alone is not proof of the durable reserve/finish pair."""
    events = [_strict_json(line) for line in (ledger.output_dir / "events.jsonl").read_text(
        encoding="utf-8").splitlines()]
    expected = {**locator._request(binding.question, build_catalog(binding.snapshot)),
                "model": "qwen3.5-plus", "stream": False, "enable_thinking": False,
                "parallel_tool_calls": False, "temperature": 0, "max_tokens": 512}
    require(len(events) == 2 and [event.get("event") for event in events]
            == ["request_reserved", "request_finished"] and len(ledger.records) == 1,
            "native_audit_failed")
    for event in events:
        require(event["request_id"] == 1 and _encoded(event["request"]) == _encoded(expected)
                and event["request_sha256"] == binding.manifest_entry()["wire_sha256"], "native_audit_failed")
    require({key: value for key, value in events[1].items() if key != "event"} == ledger.records[0]
            and ledger.pending is None and ledger.stop_reason is None
            and ledger.records[0]["usage_status"] == "complete"
            and ledger.records[0]["response_model_matches_authorized"] is True, "native_audit_failed")
    return {"durable_reservations": 1, "durable_finishes": 1,
            "wire_sha256": binding.manifest_entry()["wire_sha256"],
            "events_sha256": digest((ledger.output_dir / "events.jsonl").read_bytes())}


def run_canary(*, expected_commit, expected_fixture_sha256, authorize_paid=None):
    identity = verify_identity(expected_commit, expected_fixture_sha256,
                               require_browser=authorize_paid is not None)
    if authorize_paid is None:
        return {"mode": "identity_only", "native_requests": 0, "identity": identity}
    require(authorize_paid == PROTOCOL_IDENTITY, "authorization_required")
    output = validate_output()
    key = read_dedicated_key()

    def check_identity():
        require(verify_identity(expected_commit, expected_fixture_sha256, require_browser=True) == identity,
                "runtime_identity_changed")

    check_identity()
    from academic_agent.saved_source_receipt_qwen_adapter import BatchGate, atomic_write_once
    from e2e.saved_source_receipt_qwen_canary import browser_batch

    cases = load_cases()
    bindings = bindings_for(cases)
    batch = BatchGate(output, batch_manifest(bindings, identity))
    try:
        atomic_write_once(output / "authorization.json", {
            "protocol_identity": PROTOCOL_IDENTITY, "identity": identity,
            "operator_acknowledgement": authorize_paid, "independent_consent_review_ci_verified": False,
            "journal_scope": "private_synthetic_question_title_catalog_not_public_safe",
        })
        return browser_batch(cases=cases, bindings=bindings, batch=batch, api_key=key,
                             check_identity=check_identity, live=True)
    except Exception as exc:  # noqa: BLE001 -- preserve gate accounting but never expose arbitrary exception text.
        reason = safe_reason(exc)
        try:
            batch.stop(reason)
        except Exception:  # noqa: BLE001 -- a publication failure cannot authorize another request.
            reason = "persistence_failed"
        raise CanaryStopped(reason) from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-fixture-sha256", required=True)
    parser.add_argument("--authorize-paid", choices=[PROTOCOL_IDENTITY])
    args = parser.parse_args(argv)
    try:
        result = run_canary(expected_commit=args.expected_commit,
                            expected_fixture_sha256=args.expected_fixture_sha256,
                            authorize_paid=args.authorize_paid)
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0 if result.get("mode") == "identity_only" or result.get("batch_passed") else 1
    except Exception as exc:  # noqa: BLE001 -- CLI diagnostics never include raw keys, provider bodies or paths.
        print(json.dumps({"protocol_identity": PROTOCOL_IDENTITY, "error": safe_reason(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
