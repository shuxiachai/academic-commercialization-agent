"""Private, purposeful-development RU preparation; never live authorization.

Only caller-supplied bytes are accepted. Hashes bind present saved data, not
historical provenance, truth, ownership, or permission to transmit it. Public
tests use synthetic data; serialization and review views remain private.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from academic_agent.report_evidence_catalog_followup import build_catalog
from academic_agent.report_evidence_followup import _strict_json
from academic_agent.report_evidence_qwen_canary import MAX_TOKENS, MODEL, REQUEST_BYTES, _encoded
from academic_agent.report_evidence_source_locator import MAX_CALLBACK_BYTES, _request
from academic_agent.report_evidence_source_locator_qwen_transport import FROZEN_DEPENDENCY_COUPLING
from academic_agent.saved_source_loader import SavedSourceUnavailable, snapshot_from_saved_bytes

ROOT = Path(__file__).resolve().parents[2]
PRIVATE_ROOT = ROOT / "outputs"
METHOD = "saved_source_real_usage_offline_v1"
CASE_IDS = ("RU01", "RU02", "RU03", "RU04")
DOC_IDS = ("D1", "D1", "D2", "D2")
GROUPS = ("academic", "patent", "market")
MAX_PACKET_BYTES = 12 * 1024 * 1024
RAW_LIMITS = {"report": 1024 * 1024, "metadata": 64 * 1024, "sources": 1024 * 1024,
              "questions": 32 * 1024, "references": 16 * 1024, "scripts": 4096}
OBSERVER_PATHS = ("tests/js/source_browser_contract.mjs", "web/static/js/result.js", "web/static/js/i18n.js")
IDENTITY_PATHS = tuple(dict.fromkeys((*FROZEN_DEPENDENCY_COUPLING, *OBSERVER_PATHS,
    "src/academic_agent/saved_source_loader.py", "src/academic_agent/saved_source_accounted_qwen.py",
    "src/academic_agent/saved_source_usage.py", "src/academic_agent/saved_source_real_eval.py",
    "src/academic_agent/saved_source_real_rehearsal.py", "api/saved_source_usage_app.py",
    "api/saved_source_receipt_app.py", "api/saved_source_controller.py", "api/saved_source_receipts.py",
    "api/saved_source_accounting.py", "api/access.py", "api/runs.py",
    "src/academic_agent/report_evidence_source_locator_comparison.py",
    "tests/test_saved_source_real_eval.py", "tests/test_saved_source_real_rehearsal.py")))


class PreparationError(ValueError):
    """Fixed diagnostics never include private bytes, paths or foreign exceptions."""

    def __init__(self):
        super().__init__("Offline saved-source preparation unavailable.")


def _require(condition):
    if not condition:
        raise PreparationError()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _dump(value, limit=MAX_PACKET_BYTES):
    # Bound the entire serialized object, including escaping, not just excerpts.
    try:
        parts, size = [], 0
        encoder = json.JSONEncoder(ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
        for part in encoder.iterencode(value):
            raw = part.encode("ascii")
            size += len(raw)
            _require(size <= limit)
            parts.append(raw)
        return b"".join(parts)
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise PreparationError() from None


def _raw(raw, kind):
    _require(type(raw) is bytes and 0 < len(raw) <= RAW_LIMITS[kind])
    return raw


def _json(raw, kind):
    try:
        value = _strict_json(_raw(raw, kind).decode("utf-8"))
        _require(type(value) is dict)
        return value
    except (ValueError, TypeError, RecursionError):
        raise PreparationError() from None


def _keys(value, names):
    _require(type(value) is dict and set(value) == set(names))


def _cases(value):
    _require(type(value) is list and len(value) == 4)
    _require(all(type(row) is dict for row in value))
    _require([row.get("case_id") for row in value] == list(CASE_IDS))
    return value


def code_identity():
    """HEAD is context; exact working-file hashes, not a commit-clean claim, bind code."""
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              check=True, timeout=10).stdout.decode("ascii").strip()
        _require(re.fullmatch(r"[a-f0-9]{40}", head) is not None)
        return {"git_head": head, "working_file_sha256": {
            name: _sha((ROOT / name).read_bytes()) for name in IDENTITY_PATHS}}
    except (OSError, subprocess.SubprocessError, ValueError):
        raise PreparationError() from None


def _document(value):
    _keys(value, ("report", "metadata", "sources"))
    try:
        _require(bool(_raw(value["report"], "report").decode("utf-8").strip()))
        meta, sources = (_json(value[name], name) for name in ("metadata", "sources"))
        _require(meta.get("status") == "success" and meta.get("evidence_mode") == "live"
                 and type(meta.get("topic")) is str and bool(meta["topic"].strip())
                 and meta["topic"] == sources.get("topic") and meta.get("dry_run", False) is False
                 and meta.get("error") in (None, ""))
        alias = "20260922T000000Z-" + _sha(value["sources"])[:32]
        snapshot = snapshot_from_saved_bytes(value["sources"], alias)
        catalog = build_catalog(snapshot)
        _require(bool(snapshot.sources) and catalog["coverage"] == "complete"
                 and catalog["omitted_count"] == catalog["title_truncation_count"] == 0
                 and catalog["returned_count"] == len(snapshot.sources))
        _require(catalog["entries"] == [{"source_id": s.source_id, "title": s.title,
                                         "title_truncated": False} for s in snapshot.sources])
        _require(all(s.summary is not None and bool(s.summary.strip()) and s.stored_length <= 1500
                     for s in snapshot.sources))
        return {"sandbox_alias": alias, "alias_scope": "sandbox_not_original_run_url",
                "raw_sha256": {name: _sha(raw) for name, raw in value.items()},
                "snapshot": snapshot.model_dump(mode="json"), "snapshot_sha256": snapshot.snapshot_hash,
                "catalog": catalog, "catalog_sha256": _sha(_encoded(catalog))}
    except (ValueError, TypeError, KeyError, SavedSourceUnavailable):
        raise PreparationError() from None


def _wire(document, question):
    request = _request(question, document["catalog"])
    _require(len(_encoded(request)) <= MAX_CALLBACK_BYTES)
    wire = _encoded({**request, "model": MODEL, "stream": False, "enable_thinking": False,
                     "parallel_tool_calls": False, "temperature": 0, "max_tokens": MAX_TOKENS})
    _require(len(wire) <= REQUEST_BYTES)
    return wire


def build_packet(*, documents: dict[str, dict[str, bytes]], questions: bytes,
                 references: bytes, scripts: bytes) -> dict:
    """Bind two complete saved registries and four separately authored RU tasks."""
    _keys(documents, ("D1", "D2"))
    prepared_docs = {name: _document(documents[name]) for name in ("D1", "D2")}
    _require(prepared_docs["D1"]["sandbox_alias"] != prepared_docs["D2"]["sandbox_alias"])
    q, refs, actions = _json(questions, "questions"), _json(references, "references"), _json(scripts, "scripts")
    _keys(q, ("cases",))
    _keys(refs, ("provenance", "blind_review", "cases"))
    _keys(actions, ("cases",))
    _require(refs["provenance"] == "AI_authored_draft" and refs["blind_review"] == "not_run")
    cases, labels, choices = _cases(q["cases"]), _cases(refs["cases"]), _cases(actions["cases"])
    for case, label, choice, doc_id in zip(cases, labels, choices, DOC_IDS, strict=True):
        _keys(case, ("case_id", "doc_id", "question", "keyword_query"))
        _keys(label, ("case_id", "acceptable_source_ids"))
        _keys(choice, ("case_id", "source_id"))
        _require(case["doc_id"] == doc_id)
        for key, cap in (("question", 4096), ("keyword_query", 256)):
            _require(type(case[key]) is str and 0 < len(case[key]) <= cap and bool(case[key].strip()))
        ids = [row["source_id"] for row in prepared_docs[doc_id]["catalog"]["entries"]]
        expected = label["acceptable_source_ids"]
        _require(type(expected) is list and all(type(item) is str and item in ids for item in expected))
        _require(len(expected) == len(set(expected)))
        _require(choice["source_id"] is None or (type(choice["source_id"]) is str and choice["source_id"] in ids))
        _wire(prepared_docs[doc_id], case["question"])
    _require(len({case["question"] for case in cases}) == 4)
    raw = {"documents": {name: {key: base64.b64encode(value).decode("ascii") for key, value in doc.items()}
                          for name, doc in documents.items()},
           **{name: base64.b64encode(value).decode("ascii") for name, value in
              (("questions", questions), ("references", references), ("scripts", scripts))}}
    prepared = {"documents": prepared_docs,
                "cases": [{key: case[key] for key in ("case_id", "doc_id", "question")} for case in cases]}
    packet = {"method": METHOD, "purpose": "purposeful_development", "live_authorization": False,
              "native_efficacy": "not_run", "reference_review": "not_run", "code_identity": code_identity(),
              "configuration": {"case_ids": list(CASE_IDS), "doc_ids": list(DOC_IDS),
                                "raw_byte_limits": dict(RAW_LIMITS), "max_packet_bytes": MAX_PACKET_BYTES,
                                "max_catalog_entries": 32, "max_title_codepoints": 256,
                                "max_catalog_bytes": 6144, "max_read_codepoints": 1500,
                                "max_callback_bytes": MAX_CALLBACK_BYTES, "max_http_bytes": REQUEST_BYTES,
                                "selection": "fixed_scripted_mock_http_only", "max_http_entries": 4},
              "raw": raw, "prepared": prepared,
              "raw_input_sha256": {name: _sha(value) for name, value in
                                   (("questions", questions), ("references", references), ("scripts", scripts))}}
    packet["packet_sha256"] = _sha(_dump(packet))
    _dump(packet)
    return packet


def _decode(value, kind):
    try:
        _require(type(value) is str and len(value) <= 4 * ((RAW_LIMITS[kind] + 2) // 3))
        raw = _raw(base64.b64decode(value, validate=True), kind)
        _require(base64.b64encode(raw).decode("ascii") == value)
        return raw
    except (ValueError, TypeError):
        raise PreparationError() from None


def _inputs(packet):
    raw = packet["raw"]
    _keys(raw, ("documents", "questions", "references", "scripts"))
    _keys(raw["documents"], ("D1", "D2"))
    for document in raw["documents"].values():
        _keys(document, ("report", "metadata", "sources"))
    return {"documents": {name: {kind: _decode(value, kind) for kind, value in doc.items()}
                          for name, doc in raw["documents"].items()},
            **{kind: _decode(raw[kind], kind) for kind in ("questions", "references", "scripts")}}


def validate_packet(packet: dict) -> None:
    """Rebuild everything from bounded raw bytes and current code; no field trusts itself."""
    try:
        encoded = _dump(packet)
        _require(encoded == _dump(build_packet(**_inputs(packet))))
    except (KeyError, TypeError, ValueError, RecursionError):
        raise PreparationError() from None


def preview_wire(packet: dict) -> dict[str, bytes]:
    """Exact complete bodies, with no draft labels, scripts, prose or original URL."""
    validate_packet(packet)
    data = packet["prepared"]
    return {case["case_id"]: _wire(data["documents"][case["doc_id"]], case["question"])
            for case in data["cases"]}


def review_view(packet: dict) -> dict:
    """Private blind-judging INPUT only; it neither supplies nor records a judgment."""
    validate_packet(packet)
    data = packet["prepared"]
    return {"cases": [{**case, "catalog": [{"source_id": row["source_id"], "title": row["title"]}
            for row in data["documents"][case["doc_id"]]["catalog"]["entries"]]} for case in data["cases"]]}


def serialize_packet(packet: dict) -> bytes:
    """PRIVATE artifact bytes, not an aggregate/public export."""
    validate_packet(packet)
    return _dump(packet)


def freeze_packet(packet: dict, path: Path) -> str:
    """Exclusive creation below ignored outputs; no overwrite, symlink, or mkdir.

    This is a single-writer helper, not hostile concurrent-filesystem isolation.
    A failed partial write stays occupied rather than becoming retry permission.
    """
    raw = serialize_packet(packet)
    try:
        target = Path(os.path.abspath(path))
        _require(target.is_relative_to(PRIVATE_ROOT.absolute()) and target != PRIVATE_ROOT.absolute())
        for parent in target.parents:
            info = parent.lstat()
            _require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode)
                     and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(target, flags, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        return _sha(raw)
    except (OSError, ValueError, TypeError):
        raise PreparationError() from None
