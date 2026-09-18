"""Synthetic in-memory RS preparation controls, never private benchmark fixtures."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from academic_agent import report_evidence_real_saved_eval as rs
from academic_agent.report_evidence_snapshot import content_hash


def encoded(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def originals():
    def source(source_id):
        return {
            "source_id": source_id, "title": f"Synthetic saved record {source_id}",
            "publisher": "Synthetic publisher", "source_type": "synthetic_record",
            "url": f"https://example.invalid/{source_id}", "doi": None,
            "accessed_date": "2020-01-01", "published_date": "2099-01-01",
            "evidence_summary": "SAVED_SUMMARY_" + source_id,
            "summary_source": "abstract" if source_id.startswith("A") else "search_snippet",
            "unprojected_metadata": "still bound by original bytes",
        }

    collection = {"topic": "Synthetic local topic", "failed_domains": {},
                  "authority_coverage": {"status": "not_applicable", "missing_categories": []}}
    for group, ids in (("academic", ("A2", "A1", "A3", "A4")),
                       ("patent", tuple(f"P{i}" for i in range(1, 9))),
                       ("market", tuple(f"M{i}" for i in range(1, 9)))):
        collection[group + "_sources"] = [source(source_id) for source_id in ids]
    # Astral and combining characters test code points, not bytes/graphemes.
    collection["academic_sources"][-1]["evidence_summary"] = "前🙂e\u0301" + "x" * 1404
    metadata = {"status": "success", "evidence_mode": "live", "topic": collection["topic"],
                "run_dir": "D:/PRIVATE_ORIGINAL_PATH", "private_note": "RAW_META_MUST_STAY_LOCAL"}
    return b"# RAW_REPORT_MUST_STAY_LOCAL\nSynthetic report.", collection, metadata


def questions():
    return [{"case_id": "RS01", "question": "解释所保存研究中的材料结果及适用限制。"},
            {"case_id": "RS02", "question": "该研究是否确立了量产汽车续航改善和立即商用？"}]


def labels():
    return {
        "label_version": 1, "provenance": {"author": "synthetic AI draft", "human_review": False},
        "reference_marker": "PRIVATE_LABEL_MARKER",
        "cases": [{"case_id": case_id, "source_id": "A4", "required_state": state, "require_full_window": True}
                  for case_id, state in (("RS01", "answered_with_evidence"), ("RS02", "abstained"))],
    }


def prepare(report=None, collection=None, metadata=None, qs=None):
    original_report, original_collection, original_metadata = originals()
    return rs.prepare_inputs(original_report if report is None else report,
                             encoded(original_collection if collection is None else collection),
                             encoded(original_metadata if metadata is None else metadata),
                             questions() if qs is None else qs)


class Script:
    def __init__(self, question, *, source_id="A4", offset=0, length=1500, early=False,
                 final_state=None, final_ids=None, answer="No semantic judgment is made."):
        self.question, self.source_id = question, source_id
        self.offset, self.length, self.early = offset, length, early
        self.final_state, self.final_ids, self.answer = final_state, final_ids, answer
        self.requests = []

    def __call__(self, **request):
        self.requests.append(deepcopy(request))
        if len(self.requests) == 1 and not self.early:
            return {"role": "assistant", "tool_calls": [{
                "id": "read_" + self.question.case_id, "type": "function", "function": {
                    "name": "read_source", "arguments": json.dumps({
                        "source_id": self.source_id, "offset": self.offset, "length": self.length})}}]}
        status = self.final_state or ("answered" if self.question.case_id == "RS01" else "abstained")
        receipt = {} if self.early else json.loads(request["messages"][-1]["content"])
        ids = [receipt["evidence_id"]] if status == "answered" and "evidence_id" in receipt else []
        return {"role": "assistant", "content": json.dumps({"answer": self.answer, "status": status,
                                                            "evidence_ids": ids if self.final_ids is None
                                                            else self.final_ids})}


def rehearse(prepared, **options):
    scripts = []

    def factory(question):
        callback = Script(question, **options)
        scripts.append(callback)
        return callback

    return rs.rehearse(prepared, transport_factory=factory), scripts


def reviews(prepared, results, expected=None):
    raw = encoded(labels()) if expected is None else expected
    return rs.review_mechanics(prepared, results, expected_bytes=raw, binding=rs.bind_inputs(prepared, raw))


def test_projection_preserves_all_twenty_sources_order_dates_and_unicode():
    """Date-relative EvidenceSource validation previously changed historical dates."""
    report, collection, metadata = originals()
    qs = questions()
    before = deepcopy((collection, metadata, qs))
    prepared = rs.prepare_inputs(report, encoded(collection), encoded(metadata), qs)
    assert (collection, metadata, qs) == before
    rows = [row for group in rs.GROUPS for row in collection[group + "_sources"]]
    assert len(prepared.snapshot.sources) == 20
    for row, source in zip(rows, prepared.snapshot.sources, strict=True):
        for field in ("source_id", "title", "publisher", "source_type", "url", "doi", "published_date", "accessed_date"):
            assert getattr(source, field) == row[field]
        assert source.summary == row["evidence_summary"] and source.origin == row["summary_source"]
    assert prepared.snapshot.sources[3].stored_length == 1408
    assert prepared.snapshot.sources[3].published_date == "2099-01-01"
    assert prepared.snapshot.report_ref == "rs_" + hashlib.sha256(encoded(collection)).hexdigest()
    catalog = json.loads(prepared.catalog_json)
    assert catalog["total_count"] == catalog["returned_count"] == 20
    assert catalog["omitted_count"] == catalog["title_truncation_count"] == 0
    assert prepared.catalog_sha256 == content_hash(catalog)
    qs[0]["question"] = "changed caller input"
    collection["academic_sources"][0]["evidence_summary"] = "changed"
    assert prepared.questions[0].question == before[2][0]["question"]
    with pytest.raises(ValidationError, match="frozen"):
        prepared.snapshot.sources[0].summary = "mutated"
    with pytest.raises(ValidationError, match="frozen"):
        prepared.report_sha256 = "0" * 64


@pytest.mark.parametrize("part", ["report", "sources", "metadata", "questions"])
def test_each_original_byte_stream_and_exact_questions_bind_independently(part):
    """Snapshot identity alone cannot detect a changed report or private metadata."""
    report, collection, metadata = originals()
    source_raw, meta_raw = encoded(collection), encoded(metadata)
    original = rs.prepare_inputs(report, source_raw, meta_raw, questions())
    binding = rs.bind_inputs(original, encoded(labels()))
    qs = questions()
    if part == "report":
        report += b"\n"
    elif part == "sources":
        source_raw += b"\n"
    elif part == "metadata":
        meta_raw += b"\n"
    else:
        qs[0]["question"] += " "
    changed = rs.prepare_inputs(report, source_raw, meta_raw, qs)
    assert changed.prepared_sha256 != original.prepared_sha256
    if part in ("report", "metadata", "questions"):
        assert changed.snapshot_sha256 == original.snapshot_sha256
    with pytest.raises(ValueError, match="binding mismatch"):
        rs.verify_binding(changed, encoded(labels()), binding)


def test_label_bytes_are_independent_and_never_change_callback_payloads():
    """Even a private reference-note-only edit invalidates binding, not model input."""
    prepared = prepare()
    binding = rs.bind_inputs(prepared, encoded(labels()))
    results, scripts = rehearse(prepared)
    changed = labels()
    changed["reference_marker"] = "DIFFERENT_PRIVATE_LABEL"
    second_labels = encoded(changed)
    with pytest.raises(ValueError, match="binding mismatch"):
        rs.verify_binding(prepared, second_labels, binding)
    other_results, other_scripts = rehearse(prepared)
    assert results == other_results
    assert [item.requests for item in scripts] == [item.requests for item in other_scripts]
    assert all(review.passed for review in reviews(prepared, other_results, second_labels))
    for script in scripts:
        assert len(script.requests) == 2
        initial = script.requests[0]
        assert initial["messages"][1]["content"] == script.question.question
        assert len(initial["messages"]) == 3
        catalog = json.loads(initial["messages"][2]["content"])
        assert all(set(row) == {"source_id", "title", "title_truncated"} for row in catalog["entries"])
        wire = json.dumps(script.requests, ensure_ascii=False)
        for private in ("RAW_REPORT_MUST_STAY_LOCAL", "RAW_META_MUST_STAY_LOCAL", "PRIVATE_ORIGINAL_PATH",
                        "PRIVATE_LABEL_MARKER", "DIFFERENT_PRIVATE_LABEL", "required_state", "require_full_window"):
            assert private not in wire
        for source in prepared.snapshot.sources:
            assert source.summary not in json.dumps(initial, ensure_ascii=False)
    assert "PRIVATE_LABEL_MARKER" not in prepared.model_dump_json()


def test_positive_answer_and_nonempty_read_then_abstention_keep_actual_receipts():
    """RS02 is not CQ missing_text: both cases read the same full saved abstract."""
    prepared = prepare()
    results, scripts = rehearse(prepared)
    assert [review.passed for review in reviews(prepared, results)] == [True, True]
    assert [item.result.state for item in results] == ["answered_with_evidence", "abstained"]
    assert results[0].result.evidence_ids and results[1].result.evidence_ids == ()
    for observed, script in zip(results, scripts, strict=True):
        result = observed.result
        delivered = json.loads(script.requests[1]["messages"][-1]["content"])
        receipt = result.served_evidence[0]
        assert receipt.text == prepared.snapshot.sources[3].summary == delivered["text"]
        assert (receipt.start, receipt.end, receipt.stored_length) == (0, 1408, 1408)
        assert not receipt.window_truncated and receipt.source_id == "A4"
        assert result.audit.forwarded_read_ids == result.audit.core.delivered_read_ids == (receipt.evidence_id,)
        assert result.audit.tool_results[0].evidence_id == receipt.evidence_id
        assert result.audit.downstream_calls == 2 and result.audit.core.tool_executions == 1
        assert result.semantic_support == "not_assessed" and result.answer_verification == "not_verified"
    # Content-addressed IDs can be equal; each separate audit still owes a read.
    assert results[0].result.served_evidence[0].evidence_id == results[1].result.served_evidence[0].evidence_id


@pytest.mark.parametrize("options,reason", [
    ({"early": True}, "one_actual_read_required"),
    ({"source_id": "A1"}, "complete_current_conversation_receipt_required"),
    ({"offset": 1, "length": 3}, "complete_current_conversation_receipt_required"),
    ({"final_state": "answered"}, "preregistered_state_and_citations_required"),
])
def test_safe_abstention_wrong_source_partial_read_and_wrong_status_do_not_pass(options, reason):
    """Safe or sensible wording does not waive the preregistered read/status gate."""
    prepared = prepare()
    results, _ = rehearse(prepared, **options)
    review = reviews(prepared, results)[1]
    assert not review.passed and reason in review.failures
    if options.get("offset"):
        assert results[1].result.served_evidence[0].text == "🙂e\u0301"


def test_foreign_receipt_without_current_read_is_not_conversation_evidence():
    """The same source hash from RS01 cannot buy RS02 a skipped read."""
    prepared = prepare()
    previous, _ = rehearse(prepared)
    old_id = previous[0].result.evidence_ids[0]

    def factory(question):
        return Script(question) if question.case_id == "RS01" else Script(question, early=True, final_ids=[old_id])

    results = rs.rehearse(prepared, transport_factory=factory)
    assert results[1].result.state == "failed" and results[1].result.served_evidence == ()
    assert results[1].result.audit.core.terminal_reason == "invalid_evidence_ids"
    assert not reviews(prepared, results)[1].passed


def test_abstention_must_not_discard_served_evidence_or_keep_final_citations():
    """Read receipts are retained even when no final evidence ID supports an answer."""
    prepared = prepare()
    results, _ = rehearse(prepared)
    lost = results[1].model_copy(update={"result": results[1].result.model_copy(update={"served_evidence": ()})})
    assert not reviews(prepared, (results[0], lost))[1].passed
    cited = results[1].model_copy(update={"result": results[1].result.model_copy(
        update={"evidence_ids": results[0].result.evidence_ids})})
    assert not reviews(prepared, (results[0], cited))[1].passed


def test_mechanics_never_promote_answer_keywords_to_semantic_support():
    """Absurd prose can pass mechanics; that must never be reported as verified."""
    prepared = prepare()
    results, _ = rehearse(prepared, answer="All vehicles fly forever. unsupported commercial claim")
    assessed = reviews(prepared, results)
    assert all(item.passed for item in assessed)
    assert all(item.semantic_support == "not_assessed" and item.answer_verification == "not_verified"
               for item in assessed)


@pytest.mark.parametrize("field,value", [
    ("status", "running"), ("status", None), ("evidence_mode", "fixture"), ("evidence_mode", None),
    ("topic", "different"), ("topic", None), ("dry_run", True), ("dry_run", 0), ("error", "known failure"),
])
def test_wrong_mode_missing_identity_and_unsuccessful_metadata_fail_closed(field, value):
    """Unlike historical reuse helpers, missing evidence_mode does not mean live."""
    metadata = originals()[2]
    if value is None:
        del metadata[field]
    else:
        metadata[field] = value
    with pytest.raises(ValueError):
        prepare(metadata=metadata)


@pytest.mark.parametrize("field,value", [
    ("failed_domains", {"patent": "unavailable"}), ("failed_domains", None), ("failed_domains", []),
    ("authority_coverage", {"status": "incomplete"}), ("authority_coverage", None),
    ("authority_coverage", {"status": []}),
    ("authority_coverage", {"status": "complete", "missing_categories": ["regulator"]}),
    ("component_coverage", {"status": "partial"}), ("component_coverage", {"status": "unchecked"}),
    ("component_coverage", {"status": "complete", "unchecked_components": ["integration"]}),
])
@pytest.mark.parametrize("target", ["sources", "metadata"])
def test_known_incomplete_or_malformed_metadata_is_not_an_implicit_pass(field, value, target):
    """Known failed-domain/coverage facts cannot be hidden behind success/live."""
    _, collection, metadata = originals()
    (collection if target == "sources" else metadata)[field] = value
    with pytest.raises(ValueError):
        prepare(collection=collection, metadata=metadata)


@pytest.mark.parametrize("source_id", ["A0", "A01", "A4\n", "M4", "../A4", 4])
def test_malformed_or_wrong_group_source_identity_is_rejected(source_id):
    """A projection cannot silently normalize or regroup a saved source ID."""
    collection = originals()[1]
    collection["academic_sources"][-1]["source_id"] = source_id
    with pytest.raises(ValueError):
        prepare(collection=collection)


def test_duplicate_sources_and_absent_source_groups_are_rejected():
    """An ID collision or missing group is not a deduplicated complete catalog."""
    collection = originals()[1]
    collection["academic_sources"].append(deepcopy(collection["academic_sources"][0]))
    with pytest.raises(ValueError, match="duplicate source_id"):
        prepare(collection=collection)
    collection = originals()[1]
    del collection["market_sources"]
    with pytest.raises(ValueError, match="explicit lists"):
        prepare(collection=collection)


@pytest.mark.parametrize("field,value", [("evidence_summary", 3), ("summary_source", "full_text"),
                                        ("accessed_date", "2020-02-30"), ("published_date", "yesterday")])
def test_malformed_projection_values_are_not_coerced(field, value):
    """Readiness preserves historical values, not malformed alternate types."""
    collection = originals()[1]
    collection["academic_sources"][0][field] = value
    with pytest.raises(ValueError):
        prepare(collection=collection)


def test_missing_origin_stays_unknown_but_missing_summary_field_fails_closed():
    """Legacy provenance absence is explicit unknown, not inferred from the group."""
    collection = originals()[1]
    del collection["academic_sources"][0]["summary_source"]
    assert prepare(collection=collection).snapshot.sources[0].origin == "unknown"
    del collection["academic_sources"][0]["evidence_summary"]
    with pytest.raises(ValueError, match="missing or malformed"):
        prepare(collection=collection)


@pytest.mark.parametrize("damage", ["count", "title", "catalog_bytes"])
def test_catalog_capacity_refuses_omissions_or_clipped_titles(damage):
    """Capacity failure stops preparation instead of deleting distractors to fit."""
    collection = originals()[1]
    if damage == "count":
        template = collection["market_sources"][0]
        collection["market_sources"].extend({**template, "source_id": f"M{i}"} for i in range(9, 23))
    elif damage == "title":
        collection["academic_sources"][0]["title"] = "x" * 257
    else:
        for group in rs.GROUPS:
            for row in collection[group + "_sources"]:
                row["title"] = "测" * 200
    with pytest.raises(ValueError, match="complete untruncated catalog"):
        prepare(collection=collection)


@pytest.mark.parametrize("damage", ["missing", "reverse", "duplicate", "extra_hint", "blank"])
def test_questions_are_exact_two_label_free_records(damage):
    """Unknown expected fields and case reordering never enter transport inputs."""
    qs = questions()
    if damage == "missing":
        qs.pop()
    elif damage == "reverse":
        qs.reverse()
    elif damage == "duplicate":
        qs[1] = qs[0]
    elif damage == "extra_hint":
        qs[0]["expected"] = "private hint"
    else:
        qs[0]["question"] = " "
    with pytest.raises(ValueError):
        prepare(qs=qs)


@pytest.mark.parametrize("raw", [b"[]", b'{"topic":"a","topic":"b"}', b'{"x":NaN}', b'\xff', b'{} garbage'])
def test_nonobject_duplicate_or_invalid_json_is_rejected(raw):
    """Ambiguous JSON cannot produce a silently selected identity."""
    report, collection, metadata = originals()
    with pytest.raises(ValueError):
        rs.prepare_inputs(report, raw, encoded(metadata), questions())
    with pytest.raises(ValueError):
        rs.prepare_inputs(report, encoded(collection), raw, questions())


@pytest.mark.parametrize("summary", [None, "", "x" * 1501])
def test_expected_missing_or_overlong_source_cannot_be_bound_as_full_read(summary):
    """RS02 cannot reuse CQ missing_text or silently weaken the full-window gate."""
    collection = originals()[1]
    collection["academic_sources"][-1]["evidence_summary"] = summary
    prepared = prepare(collection=collection)
    with pytest.raises(ValueError, match="nonempty completely readable"):
        rs.bind_inputs(prepared, encoded(labels()))


@pytest.mark.parametrize("damage", ["window", "source", "state", "order", "bool_type"])
def test_labels_cannot_relax_frozen_rs_gates(damage):
    """Reference metadata is private, but the two mechanical targets stay fixed."""
    expected = labels()
    if damage == "window":
        expected["cases"][1]["require_full_window"] = False
    elif damage == "source":
        expected["cases"][1]["source_id"] = "A1"
    elif damage == "state":
        expected["cases"][1]["required_state"] = "answered_with_evidence"
    elif damage == "order":
        expected["cases"].reverse()
    else:
        expected["cases"][1]["require_full_window"] = 1
    with pytest.raises(ValueError):
        rs.bind_inputs(prepare(), encoded(expected))


@pytest.mark.parametrize("field,value", [("catalog_json", "{}"), ("configuration_json", "{}"),
                                        ("projection_sha256", "0" * 64)])
def test_prepared_copy_drift_is_revalidated_before_callbacks(field, value):
    """Frozen model_copy is not itself evidence of unchanged preparation policy."""
    prepared = prepare().model_copy(update={field: value})
    entered = []
    with pytest.raises(ValueError, match="identity mismatch"):
        rs.rehearse(prepared, transport_factory=lambda question: entered.append(question))
    assert entered == []


def test_rehearsal_identity_is_checked_and_no_implicit_callback_exists():
    """Results from another question/input binding cannot be pasted into this packet."""
    prepared = prepare()
    with pytest.raises(TypeError):
        rs.rehearse(prepared)
    result, _ = rehearse(prepared)
    changed = result[0].model_copy(update={"question_sha256": "0" * 64})
    assert not reviews(prepared, (changed, result[1]))[0].passed
    with pytest.raises(ValueError, match="ordered"):
        reviews(prepared, tuple(reversed(result)))
    callback = Script(prepared.questions[0])
    with pytest.raises(ValueError, match="separate callable"):
        rs.rehearse(prepared, transport_factory=lambda _: callback)


def test_import_preparation_and_rehearsal_have_no_provider_key_file_or_network_route():
    """Run the actual module in a guarded child, not a self-declared offline flag."""
    report, collection, metadata = originals()
    code = r'''
import importlib.abc
import os
import sys
attempts = []
blocked = {"crewai", "openai", "litellm", "anthropic", "httpx", "requests", "dotenv", "api",
           "academic_agent.source_pipeline", "academic_agent.evidence",
           "academic_agent.report_evidence_catalog_qwen_transport"}
class BlockImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + ".") for name in blocked):
            attempts.append(fullname)
            raise RuntimeError("forbidden import")
def audit(event, args):
    if event.startswith("socket.") and event != "socket.__new__":
        attempts.append(event)
        raise RuntimeError("network forbidden")
    if event == "open" and isinstance(args[0], str) and args[0].endswith((".env", ".json", ".md")):
        attempts.append("private file read")
        raise RuntimeError("file input forbidden")
original = os._Environ.__getitem__
def deny_credentials(self, key):
    if any(word in key.upper() for word in ("API_KEY", "TOKEN", "SECRET", "CREDENTIAL")):
        attempts.append("credential read")
        raise RuntimeError("credential input forbidden")
    return original(self, key)
os._Environ.__getitem__ = deny_credentials
sys.meta_path.insert(0, BlockImports())
sys.addaudithook(audit)
from academic_agent import report_evidence_real_saved_eval as rs
import json
'''
    code += f"p = rs.prepare_inputs({report!r}, {encoded(collection)!r}, {encoded(metadata)!r}, {questions()!r})\n"
    code += r'''
def factory(question):
    return lambda **request: {"role": "assistant", "content": json.dumps(
        {"answer": "offline", "status": "abstained", "evidence_ids": []})}
observed = rs.rehearse(p, transport_factory=factory)
assert len(observed) == 2
assert not attempts, attempts
print("offline guard passed")
'''
    completed = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
                               capture_output=True, text=True, encoding="utf-8", timeout=30, check=False)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "offline guard passed"
