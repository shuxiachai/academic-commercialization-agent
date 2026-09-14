"""Exclusive, non-resumable synthetic canary and pre-dispatch accounting.

Reservations are conservative estimates, not token guarantees or invoices.
Unknown usage stops the batch; its outstanding reservation is never refunded.
"""

from copy import deepcopy
from decimal import Decimal
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tomllib

from academic_agent.report_evidence_followup import run_followup, _strict_json
from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, SnapshotSource

MODEL = "qwen3.5-plus"
ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
MAX_REQUESTS = 6
USD_LIMIT = Decimal("0.10")
INPUT_RATE = Decimal("0.573")
OUTPUT_RATE = Decimal("3.44")
INPUT_RESERVATION = 16384
MAX_TOKENS = 512
RESERVATION_USD = Decimal("0.011149312")
REQUEST_BYTES = 12 * 1024
RESPONSE_BYTES = 64 * 1024
CONNECT_SECONDS = 10
TOTAL_SECONDS = 60
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = "tests/fixtures/report_evidence_followup_qwen.json"
FIXTURE_SHA256 = "4e026d9cf051a264b65f7b5f3e6d75cf501cc2acc2f4d5dcceb513cc37d37435"
IDENTITY_PATHS = (
    "src/academic_agent/report_evidence_snapshot.py",
    "src/academic_agent/report_evidence_followup.py",
    "src/academic_agent/report_evidence_qwen_transport.py",
    "src/academic_agent/report_evidence_qwen_canary.py",
    "report_evidence_followup_canary.py", FIXTURE,
    "tests/test_report_evidence_qwen_transport.py",
    "tests/test_report_evidence_qwen_canary.py", "pyproject.toml", "uv.lock",
    "docs/prereg-2026-09-14-report-evidence-followup-qwen.md",
)


class CanaryStopped(RuntimeError):
    """Only code-owned categories cross the transport/CLI exception boundary."""


def _encoded(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _new_json(path: Path, value: object) -> None:
    with path.open("xb") as stream:
        stream.write(_encoded(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def configuration() -> dict:
    return {"model": MODEL, "endpoint": ENDPOINT, "max_requests": MAX_REQUESTS,
            "usd_soft_limit": str(USD_LIMIT), "reservation_usd": str(RESERVATION_USD),
            "input_rate_per_million": str(INPUT_RATE), "output_rate_per_million": str(OUTPUT_RATE),
            "input_token_reservation": INPUT_RESERVATION, "max_tokens": MAX_TOKENS,
            "request_bytes": REQUEST_BYTES, "response_bytes": RESPONSE_BYTES,
            "connect_seconds": CONNECT_SECONDS, "total_seconds": TOTAL_SECONDS,
            "stream": False, "enable_thinking": False, "parallel_tool_calls": False,
            "temperature": 0, "tool_choice": "auto", "retries": 0,
            "follow_redirects": False, "trust_env": False, "verify_tls": True,
            "price_scope": "frozen_conservative_estimate_not_invoice"}


def load_cases() -> list[dict]:
    raw = (ROOT / FIXTURE).read_bytes()
    if hashlib.sha256(raw).hexdigest() != FIXTURE_SHA256:
        raise CanaryStopped("fixture_identity_mismatch")
    return _strict_json(raw.decode("utf-8"))


def verify_identity(expected_commit: str) -> dict:
    """Only the explicit CLI performs git reads; private unrelated dirt is preserved."""
    if not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise CanaryStopped("invalid_expected_commit")
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True, timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--", *IDENTITY_PATHS],
                               cwd=ROOT, capture_output=True, text=True, check=True, timeout=10).stdout
        if head != expected_commit or dirty.strip():
            raise CanaryStopped("source_identity_mismatch")
        load_cases()
        hashes = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in IDENTITY_PATHS}
        locked = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))["package"]
        installed = {name: version(name) for name in (
            "httpx", "httpcore", "anyio", "certifi", "h11", "idna", "sniffio", "typing-extensions",
            "pydantic", "pydantic-core", "annotated-types", "typing-inspection", "python-dotenv",
        )}
        if any(value not in {row["version"] for row in locked if row["name"] == name}
               for name, value in installed.items()):
            raise CanaryStopped("installed_dependency_mismatch")
        return {"commit": head, "fixture_sha256": FIXTURE_SHA256, "source_dependency_sha256": hashes,
                "runtime": {"python": platform.python_version(), **installed}, "configuration": configuration()}
    except (OSError, subprocess.SubprocessError, PackageNotFoundError, KeyError, tomllib.TOMLDecodeError):
        raise CanaryStopped("identity_check_unavailable") from None


class CanaryLedger:
    """One process, one fresh directory, append/fsync before each possible POST."""

    def __init__(self, output_dir: Path, manifest: dict):
        self.output_dir = Path(output_dir)
        self.records: list[dict] = []
        self.stop_reason: str | None = None
        self.pending: int | None = None
        self.case_id: str | None = None
        try:
            self.output_dir.mkdir(exist_ok=False)
            _new_json(self.output_dir / "manifest.json", manifest)
            with (self.output_dir / "events.jsonl").open("xb") as stream:
                stream.flush()
                os.fsync(stream.fileno())
        except OSError:
            raise CanaryStopped("output_creation_failed_or_occupied") from None

    def _append(self, event: dict) -> None:
        try:
            # r+b refuses to recreate a ledger removed after initialization.
            with (self.output_dir / "events.jsonl").open("r+b") as stream:
                stream.seek(0, 2)
                stream.write(_encoded(event) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
        except OSError:
            self.stop_reason = "persistence_failed"
            raise CanaryStopped("persistence_failed") from None

    def stop(self, reason: str) -> None:
        if self.stop_reason is None:
            self.stop_reason = reason
            self._append({"event": "batch_stopped", "reason": reason})

    def reserve(self, body: dict) -> int:
        if self.stop_reason is not None:
            raise CanaryStopped("batch_already_stopped")
        if self.pending is not None:
            self.stop("unresolved_request")
            raise CanaryStopped("unresolved_request")
        if len(self.records) >= MAX_REQUESTS:
            self.stop("request_limit")
            raise CanaryStopped("request_limit")
        if Decimal(self.summary()["budget_consumed_usd"]) + RESERVATION_USD > USD_LIMIT:
            self.stop("budget_limit")
            raise CanaryStopped("budget_limit")
        ordinal = len(self.records) + 1
        record = {"request_id": ordinal, "case_id": self.case_id, "request": deepcopy(body),
                  "request_sha256": hashlib.sha256(_encoded(body)).hexdigest(),
                  "reservation_usd": str(RESERVATION_USD), "usage_status": "unknown",
                  "provider_response_received": False, "response_model_matches_authorized": None,
                  "protocol_accepted": False}
        self._append({"event": "request_reserved", **record})
        self.records.append(record)
        self.pending = ordinal
        return ordinal

    def finish(self, ordinal: int, *, received: bool, usage: dict | None,
               error: str | None, message: dict | None = None,
               response_model_matches_authorized: bool | None = None) -> None:
        if self.pending != ordinal:
            self.stop("request_identity_mismatch")
            raise CanaryStopped("request_identity_mismatch")
        record = self.records[ordinal - 1]
        record.update(provider_response_received=received, protocol_accepted=error is None,
                      usage_status="complete" if usage is not None else "unknown", error=error,
                      response_model_matches_authorized=response_model_matches_authorized)
        if usage is not None:
            record["reported_usage"] = deepcopy(usage)
            record["estimated_usd"] = str((Decimal(usage["prompt_tokens"]) * INPUT_RATE
                                           + Decimal(usage["completion_tokens"]) * OUTPUT_RATE) / 1_000_000)
        if message is not None:
            record["assistant_message"] = deepcopy(message)
        # Keep observed usage in memory even if finalization fails on disk.
        self._append({"event": "request_finished", **record})
        self.pending = None
        if error is not None:
            self.stop(error)

    def summary(self) -> dict:
        known = sum((Decimal(record.get("estimated_usd", "0")) for record in self.records), Decimal(0))
        consumed = sum((max(Decimal(record["reservation_usd"]), Decimal(record.get("estimated_usd", "0")))
                        for record in self.records), Decimal(0))
        unknown = sum(record["usage_status"] != "complete" for record in self.records)
        return {"request_count": len(self.records), "unknown_usage_requests": unknown,
                "known_usage_estimated_usd": str(known), "budget_consumed_usd": str(consumed),
                "cost_coverage": "lower_bound" if unknown else "complete_for_reported_requests",
                "price_scope": "frozen_conservative_estimate_not_invoice", "stop_reason": self.stop_reason,
                "pending_request_id": self.pending}

    def save(self, name: str, value: dict) -> None:
        try:
            _new_json(self.output_dir / name, value)
        except OSError:
            self.stop_reason = "persistence_failed"
            raise CanaryStopped("persistence_failed") from None


def _case_gate(case: dict, result, records: list[dict]) -> bool:
    observed_reads = [call for record in records for call in record.get("assistant_message", {}).get("tool_calls", [])
                      if call["function"]["name"] == "read_source"]
    delivered = [_strict_json(message["content"]) for record in records if record["protocol_accepted"]
                 for message in record["request"]["messages"] if message["role"] == "tool"]
    if not observed_reads:
        return False
    if case["case_id"] == "FQ02":
        return (result.state == "abstained" and not result.evidence_ids and not result.served_evidence
                and any(item.get("source_id") == "M1" and item.get("status") == "missing_text" for item in delivered))
    # Temperature/field-deployment prose is a separate narrow parent review,
    # not a phrase-matching semantic verdict disguised as a protocol gate.
    return (result.state == "answered_with_evidence"
            and any(item.get("source_id") == "A1" and item.get("text") == case["summary"]
                    and item.get("evidence_id") in result.evidence_ids for item in delivered))


def run_canary(*, api_key: str, output_dir: Path, manifest: dict) -> dict:
    """Only the frozen cases run, sharing one ledger and six-request allowance."""
    from academic_agent.report_evidence_qwen_transport import QwenFollowupTransport

    cases = load_cases()
    ledger = CanaryLedger(output_dir, manifest)
    transport = QwenFollowupTransport(api_key, ledger)
    outcomes = []
    for case in cases:
        ledger.case_id = case["case_id"]
        snapshot = ReportEvidenceSnapshot(report_ref=case["case_id"], sources=(SnapshotSource(
            **{key: value for key, value in case.items() if key not in {"case_id", "question"}},
            source_type=case["group"],
        ),))
        first = len(ledger.records)
        result = run_followup(snapshot, case["question"], transport=transport)
        passed = ledger.stop_reason is None and _case_gate(case, result, ledger.records[first:])
        outcome = {"case_id": case["case_id"], "passed": passed, "result": result.model_dump(mode="json"),
                   "narrow_content_control": "requires_parent_review" if case["case_id"] == "FQ01" else "not_applicable"}
        ledger.save(case["case_id"] + ".json", outcome)
        outcomes.append(outcome)
        if not passed:
            ledger.stop("core_protocol_failed" if result.state == "failed" else "case_gate_failed")
            break
    summary = {"mode": "synthetic_qwen_canary", "passed": len(outcomes) == 2 and all(row["passed"] for row in outcomes),
               "cases": [{"case_id": row["case_id"], "passed": row["passed"]} for row in outcomes],
               "unrun_cases": [case["case_id"] for case in cases[len(outcomes):]],
               "semantic_support": "not_assessed", "answer_verification": "not_verified", **ledger.summary()}
    ledger.save("summary.json", summary)
    return summary
