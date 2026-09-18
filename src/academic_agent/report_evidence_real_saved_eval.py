"""Identity-bound local RS preparation, never a live runner or an access check.

Saved benchmark files can be repaired disk snapshots. Hashes bind their current
bytes, not historical authenticity, ownership, same-run provenance or permission
to transmit them. Labels and report prose never enter callback construction.
"""

from collections.abc import Callable
from datetime import date
import hashlib
import json
import re
from typing import Literal

from pydantic import Field

from academic_agent import report_evidence_followup as core
from academic_agent.report_evidence_catalog_followup import (
    MAX_CALLBACK_BYTES, MAX_CALLBACK_REQUESTS, MAX_CATALOG_BYTES,
    MAX_CATALOG_ENTRIES, MAX_TITLE_CODEPOINTS, CatalogFollowupResult,
    build_catalog, run_catalog_followup,
)
from academic_agent.report_evidence_snapshot import (
    MAX_READ_CHARS, FrozenModel, ReportEvidenceSnapshot, SnapshotSource,
    content_hash, read_source,
)

PROTOCOL_IDENTITY = "report_evidence_real_saved_offline_v1"
CASE_IDS = ("RS01", "RS02")
GROUPS = ("academic", "patent", "market")
_FIELDS = (
    ("source_id", "source_id"), ("title", "title"), ("publisher", "publisher"),
    ("source_type", "source_type"), ("url", "url"), ("doi", "doi"),
    ("published_date", "published_date"), ("accessed_date", "accessed_date"),
    ("summary", "evidence_summary"), ("origin", "summary_source"),
)
_REQUIRED_SOURCE_FIELDS = {"source_id", "title", "publisher", "source_type", "accessed_date", "evidence_summary"}


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _object(raw: bytes, kind: str) -> dict:
    if type(raw) is not bytes or not raw:
        raise ValueError(f"{kind}: nonempty bytes required")
    try:
        value = core._strict_json(raw.decode("utf-8"))
    except (ValueError, RecursionError):
        raise ValueError(f"{kind}: invalid UTF-8 JSON") from None
    if type(value) is not dict:
        raise ValueError(f"{kind}: JSON object required")
    return value


def configuration() -> dict:
    """Preparation policy only; the existing adapter owns complete HTTP bounds."""
    return {
        "protocol_identity": PROTOCOL_IDENTITY, "case_ids": list(CASE_IDS),
        "live_authorization": False, "transport": "explicit_callback_only",
        "max_catalog_entries": MAX_CATALOG_ENTRIES, "max_title_codepoints": MAX_TITLE_CODEPOINTS,
        "max_catalog_bytes": MAX_CATALOG_BYTES, "max_read_codepoints": MAX_READ_CHARS,
        "max_callback_requests": MAX_CALLBACK_REQUESTS, "max_callback_bytes": MAX_CALLBACK_BYTES,
        "max_http_body_bytes": 12288, "http_bound_enforced_by": "existing_catalog_adapter_not_this_module",
        "max_reads_per_case": 1, "complete_catalog_required": True,
        "semantic_support": "not_assessed", "answer_verification": "not_verified",
    }


def _projection_hash() -> str:
    return content_hash({"identity": "saved_json_direct_projection_v1", "groups": GROUPS,
                         "fields": _FIELDS, "absent_or_null_origin": "unknown",
                         "dates": "preserve_iso_date_no_relative_validation"})


class SavedQuestion(FrozenModel):
    case_id: Literal["RS01", "RS02"]
    question: str = Field(min_length=1, max_length=4096)


class PreparedInputs(FrozenModel):
    """Immutable label-free input; raw report/metadata are represented only by hashes."""

    report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sources_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    questions: tuple[SavedQuestion, ...]
    snapshot: ReportEvidenceSnapshot
    projection_sha256: str
    catalog_json: str
    configuration_json: str

    @property
    def snapshot_sha256(self) -> str:
        return self.snapshot.snapshot_hash

    @property
    def catalog_sha256(self) -> str:
        return _sha(self.catalog_json.encode("ascii"))

    @property
    def configuration_sha256(self) -> str:
        return _sha(self.configuration_json.encode("ascii"))

    @property
    def questions_sha256(self) -> str:
        return content_hash([question.model_dump() for question in self.questions])

    @property
    def prepared_sha256(self) -> str:
        return content_hash(self.model_dump())


class ExpectedCase(FrozenModel):
    case_id: Literal["RS01", "RS02"]
    source_id: str = Field(pattern=r"^[APM][1-9][0-9]{0,8}$")
    required_state: Literal["answered_with_evidence", "abstained"]
    require_full_window: bool


class PacketBinding(FrozenModel):
    protocol_identity: Literal["report_evidence_real_saved_offline_v1"] = PROTOCOL_IDENTITY
    prepared_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    live_authorization: Literal[False] = False

    @property
    def binding_sha256(self) -> str:
        return content_hash(self.model_dump())


class CaseRehearsal(FrozenModel):
    case_id: Literal["RS01", "RS02"]
    prepared_sha256: str
    question_sha256: str
    result: CatalogFollowupResult


class MechanicalReview(FrozenModel):
    case_id: Literal["RS01", "RS02"]
    passed: bool
    failures: tuple[str, ...]
    binding_sha256: str
    semantic_support: Literal["not_assessed"] = "not_assessed"
    answer_verification: Literal["not_verified"] = "not_verified"


def _known_incompleteness(document: dict) -> None:
    # Fail this preparation closed on known missing coverage; do not retrofit a
    # blocking policy into production or infer completeness from absent legacy fields.
    if "failed_domains" in document and document["failed_domains"] != {}:
        raise ValueError("failed or malformed source domains")
    for field, missing in (("authority_coverage", ("missing_categories",)),
                           ("component_coverage", ("missing_components", "unchecked_components"))):
        if field not in document:
            continue
        coverage = document[field]
        if (type(coverage) is not dict or type(coverage.get("status")) is not str
                or coverage["status"] not in {"complete", "not_applicable"}):
            raise ValueError("incomplete or malformed saved coverage")
        for name in missing:
            if name in coverage and coverage[name] != []:
                raise ValueError("missing or malformed saved coverage")


def _complete_catalog(snapshot: ReportEvidenceSnapshot) -> dict:
    catalog = build_catalog(snapshot)
    if not snapshot.sources or catalog["omitted_count"] or catalog["title_truncation_count"]:
        raise ValueError("complete untruncated catalog required; no subset selection")
    return catalog


def _questions(questions: tuple[SavedQuestion, ...] | list[dict[str, object]]) -> tuple[SavedQuestion, ...]:
    if type(questions) not in (tuple, list) or any(type(item) not in (SavedQuestion, dict) for item in questions):
        raise ValueError("ordered questions required")
    detached = tuple(SavedQuestion.model_validate(item.model_dump() if type(item) is SavedQuestion else item)
                     for item in questions)
    if tuple(item.case_id for item in detached) != CASE_IDS or any(not item.question.strip() for item in detached):
        raise ValueError("exact RS01/RS02 order and nonblank questions required")
    return detached


def prepare_inputs(
    report_bytes: bytes, sources_bytes: bytes, metadata_bytes: bytes,
    questions: tuple[SavedQuestion, ...] | list[dict[str, object]],
) -> PreparedInputs:
    """Project disk JSON directly, without EvidenceSource/date-relative validation.

    Matching declared topic/status/mode is only an association gate. Other saved
    fields are bound by raw hashes, not reinterpreted as historical verification.
    """
    if type(report_bytes) is not bytes or not report_bytes:
        raise ValueError("nonempty report bytes required")
    try:
        if not report_bytes.decode("utf-8").strip():
            raise ValueError("empty report")
    except ValueError:
        raise ValueError("nonempty UTF-8 report required") from None
    sources = _object(sources_bytes, "sources")
    metadata = _object(metadata_bytes, "metadata")
    if (metadata.get("status") != "success" or metadata.get("evidence_mode") != "live"
            or type(metadata.get("topic")) is not str or not metadata["topic"].strip()
            or metadata["topic"] != sources.get("topic")
            or metadata.get("dry_run", False) is not False or metadata.get("error") not in (None, "")):
        raise ValueError("successful live metadata with exact matching topic required")
    _known_incompleteness(sources)
    _known_incompleteness(metadata)
    projected = []
    for group in GROUPS:
        rows = sources.get(f"{group}_sources")
        if type(rows) is not list:
            raise ValueError("all three source groups must be explicit lists")
        for row in rows:
            if type(row) is not dict or not _REQUIRED_SOURCE_FIELDS <= row.keys():
                raise ValueError("missing or malformed projected source fields")
            fields = {target: row.get(original) for target, original in _FIELDS}
            if fields["origin"] is None:
                fields["origin"] = "unknown"
            for name in ("accessed_date", "published_date"):
                value = fields[name]
                if name == "published_date" and value is None:
                    continue
                if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    raise ValueError("saved date must be an unchanged ISO date")
                date.fromisoformat(value)
            projected.append(SnapshotSource(group=group, **fields))
    # This opaque local association is stable and contains neither a pathname nor
    # a run URL. Report bytes remain separately bound: snapshot_hash is not their hash.
    snapshot = ReportEvidenceSnapshot(report_ref="rs_" + _sha(sources_bytes), sources=tuple(projected))
    catalog = _complete_catalog(snapshot)
    return PreparedInputs(
        report_sha256=_sha(report_bytes), sources_sha256=_sha(sources_bytes), metadata_sha256=_sha(metadata_bytes),
        questions=_questions(questions), snapshot=snapshot, projection_sha256=_projection_hash(),
        catalog_json=_canonical(catalog), configuration_json=_canonical(configuration()),
    )


def _validated(prepared: PreparedInputs) -> PreparedInputs:
    # Revalidate model_copy/model_construct too; this guards accidental drift,
    # not a hostile in-process caller who can also replace this implementation.
    prepared = PreparedInputs.model_validate(prepared.model_dump())
    _questions(prepared.questions)
    if (prepared.snapshot.report_ref != "rs_" + prepared.sources_sha256
            or prepared.catalog_json != _canonical(_complete_catalog(prepared.snapshot))
            or prepared.configuration_json != _canonical(configuration())
            or prepared.projection_sha256 != _projection_hash()):
        raise ValueError("prepared projection/catalog/configuration identity mismatch")
    return prepared


def _expected(prepared: PreparedInputs, raw: bytes) -> tuple[ExpectedCase, ...]:
    labels = _object(raw, "expected labels")
    # Additional private authorship/review notes are opaque, but ALL original
    # label bytes participate in binding; none are inputs to a callback.
    if type(labels.get("cases")) is not list:
        raise ValueError("expected labels require cases")
    cases = tuple(ExpectedCase.model_validate(item) for item in labels["cases"])
    if tuple(item.case_id for item in cases) != CASE_IDS:
        raise ValueError("expected labels require exact RS01/RS02 order")
    if (cases[0].required_state != "answered_with_evidence" or cases[1].required_state != "abstained"
            or cases[0].source_id != cases[1].source_id or not all(item.require_full_window for item in cases)):
        raise ValueError("RS cases require the same full read and their preregistered states")
    target = next((item for item in prepared.snapshot.sources if item.source_id == cases[0].source_id), None)
    if target is None or not target.summary or target.stored_length > MAX_READ_CHARS:
        raise ValueError("expected source must have nonempty completely readable saved text")
    return cases


def bind_inputs(prepared: PreparedInputs, expected_bytes: bytes) -> PacketBinding:
    prepared = _validated(prepared)
    _expected(prepared, expected_bytes)
    return PacketBinding(prepared_sha256=prepared.prepared_sha256, expected_sha256=_sha(expected_bytes))


def verify_binding(prepared: PreparedInputs, expected_bytes: bytes, binding: PacketBinding) -> None:
    binding = PacketBinding.model_validate(binding.model_dump())
    if binding != bind_inputs(prepared, expected_bytes):
        raise ValueError("packet binding mismatch")


def rehearse(
    prepared: PreparedInputs, *, transport_factory: Callable[[SavedQuestion], Callable[..., object]],
) -> tuple[CaseRehearsal, ...]:
    """Two independent real catalog executions; no labels or implicit transport.

    The caller supplies local scripted/intercepted callbacks. This function grants
    no live authorization and does not claim to sandbox arbitrary Python callbacks.
    """
    prepared = _validated(prepared)
    results, callbacks = [], []
    for question in prepared.questions:
        callback = transport_factory(question)
        if not callable(callback) or any(callback is previous for previous in callbacks):
            raise ValueError("a separate callable is required for each conversation")
        callbacks.append(callback)
        result = run_catalog_followup(prepared.snapshot, question.question, transport=callback)
        results.append(CaseRehearsal(case_id=question.case_id, prepared_sha256=prepared.prepared_sha256,
                                     question_sha256=content_hash(question.model_dump()), result=result))
    return tuple(results)


def review_mechanics(
    prepared: PreparedInputs, rehearsals: tuple[CaseRehearsal, ...], *,
    expected_bytes: bytes, binding: PacketBinding,
) -> tuple[MechanicalReview, ...]:
    """Compare actual receipts/coverage, not answer keywords or semantic truth."""
    prepared = _validated(prepared)
    verify_binding(prepared, expected_bytes, binding)
    expected = _expected(prepared, expected_bytes)
    rehearsals = tuple(CaseRehearsal.model_validate(item.model_dump()) for item in rehearsals)
    if tuple(item.case_id for item in rehearsals) != CASE_IDS:
        raise ValueError("two ordered independent case results required")
    reviews = []
    for question, case, observed in zip(prepared.questions, expected, rehearsals, strict=True):
        result, failures = observed.result, []
        audit = result.audit
        if (observed.prepared_sha256 != prepared.prepared_sha256
                or observed.question_sha256 != content_hash(question.model_dump())):
            failures.append("rehearsal_identity_mismatch")
        if (audit.downstream_calls != 2 or len(audit.callback_bytes) != 2
                or any(not 0 < count <= MAX_CALLBACK_BYTES for count in audit.callback_bytes)
                or audit.blocked_callback_bytes is not None or audit.refusal is not None
                or audit.downstream_exception_type is not None
                or audit.advertised_tools != (("read_source",), ())):
            failures.append("two_callback_read_to_final_required")
        if (audit.catalog_hash != prepared.catalog_sha256 or audit.catalog_bytes != len(prepared.catalog_json)
                or audit.total_count != len(prepared.snapshot.sources) or audit.returned_count != audit.total_count
                or audit.coverage != "complete" or audit.omitted_count or audit.title_truncation_count):
            failures.append("complete_bound_catalog_required")
        if (audit.core.transport_turns != 2 or audit.core.observed_tool_requests != 1
                or audit.core.tool_attempts != 1 or audit.core.tool_executions != 1 or audit.core.tool_errors
                or audit.core.no_tools or len(audit.core.call_ids) != 1 or audit.core.exception_type is not None):
            failures.append("one_actual_read_required")
        target = next(item for item in prepared.snapshot.sources if item.source_id == case.source_id)
        full = read_source(prepared.snapshot, case.source_id, 0, target.stored_length)
        payload = {name: full[name] for name in core.ServedEvidence.model_fields if name != "evidence_id"}
        evidence_id = "ev_" + content_hash(payload)
        receipt = core.ServedEvidence(evidence_id=evidence_id, **payload)
        # RS02 must retain this NONEMPTY delivered receipt after abstaining. A
        # previous conversation's identical content hash alone is not a read.
        if (result.served_evidence != (receipt,) or audit.forwarded_read_ids != (evidence_id,)
                or audit.core.delivered_read_ids != (evidence_id,) or len(audit.tool_results) != 1
                or audit.tool_results[0].status != "ok" or audit.tool_results[0].evidence_id != evidence_id
                or (audit.tool_results[0].call_id,) != audit.core.call_ids):
            failures.append("complete_current_conversation_receipt_required")
        required_ids = (evidence_id,) if case.required_state == "answered_with_evidence" else ()
        if result.state != case.required_state or result.evidence_ids != required_ids:
            failures.append("preregistered_state_and_citations_required")
        reviews.append(MechanicalReview(case_id=case.case_id, passed=not failures, failures=tuple(failures),
                                        binding_sha256=binding.binding_sha256))
    return tuple(reviews)
