"""Synthetic snapshot boundaries; no archived cohorts or retrieval fixtures."""

from copy import deepcopy
from datetime import date, datetime, UTC

import pytest
from pydantic import ValidationError

from academic_agent.evidence import EvidenceSource
from academic_agent.source_pipeline import SourceCollection
from academic_agent.report_evidence_snapshot import (
    CONTENT_WARNING, MAX_SOURCES, MAX_SUMMARY_CHARS, MAX_TOTAL_SUMMARY_CHARS,
    ReadArguments, ReportEvidenceSnapshot, SnapshotSource,
    build_snapshot, catalog_payload, lookup_sources, read_source,
)


def synthetic_collection():
    """Already loaded source models, including legacy/missing saved fields.

    model_construct deliberately avoids today's retrieval validation: the
    projection must not revalidate or mutate this caller-owned saved material.
    """
    def source(source_id, text, origin):
        return EvidenceSource.model_construct(
            source_id=source_id, title=f"Synthetic {source_id} sensor record",
            publisher="Synthetic publisher", source_type="academic_paper",
            url=None, doi="10.1234/synthetic", published_date=date(2099, 1, 1),
            accessed_date=date(2020, 1, 1), evidence_summary=text, summary_source=origin,
        )

    return SourceCollection.model_construct(
        topic="Synthetic sensor", collected_at=datetime(2020, 1, 1, tzinfo=UTC),
        academic_sources=[source("A1", "A测🙂e\u0301\nStraße sensor [literal].", "abstract")],
        patent_sources=[source("P1", "Saved patent search snippet.", "search_snippet")],
        market_sources=[source("M1", None, None)],
        academic_queries=["synthetic"], patent_queries=["synthetic"], market_queries=["synthetic"],
    )


@pytest.fixture
def snapshot():
    return build_snapshot(synthetic_collection(), "synthetic-report-one")


def test_snapshot_is_detached_frozen_and_does_not_revalidate_old_dates():
    """A source mutation and date-relative validators must not change saved evidence."""
    collection = synthetic_collection()
    before = deepcopy(collection.model_dump())
    snapshot = build_snapshot(collection, "one")
    frozen = snapshot.model_dump()
    digest = snapshot.snapshot_hash
    assert collection.model_dump() == before
    assert snapshot.sources[0].published_date == "2099-01-01"
    collection.academic_sources[0].evidence_summary = "Changed by original caller"
    collection.academic_sources[0].title = "Changed title"
    collection.academic_sources.clear()
    assert snapshot.model_dump() == frozen
    assert snapshot.snapshot_hash == digest
    with pytest.raises(ValidationError, match="frozen"):
        snapshot.report_ref = "another"
    with pytest.raises(ValidationError, match="frozen"):
        snapshot.sources[0].summary = "changed"
    detached = snapshot.model_dump()
    detached["sources"][0]["title"] = "changed"
    assert snapshot.model_dump() == frozen


@pytest.mark.parametrize("target", ["academic_sources", "patent_sources", "market_sources"])
def test_duplicate_source_ids_are_rejected_globally(target):
    """An ID-keyed projection must not silently overwrite duplicate source records."""
    collection = synthetic_collection()
    getattr(collection, target).append(collection.academic_sources[0].model_copy(deep=True))
    with pytest.raises(ValueError, match="duplicate source_id"):
        build_snapshot(collection, "one")


def test_direct_snapshot_rejects_duplicate_ids(snapshot):
    """Direct typed construction must preserve the builder's no-overwrite contract."""
    with pytest.raises(ValueError, match="duplicate source_id"):
        ReportEvidenceSnapshot(report_ref="one", sources=(snapshot.sources[0], snapshot.sources[0]))


@pytest.mark.parametrize("source_id", ["P1", "A0", "A01", "a1", "A1\n", "A1234567890", "../A1"])
def test_wrong_group_and_noncanonical_ids_are_rejected(source_id):
    """An academic row cannot smuggle a patent ID or an alternate scope selector."""
    collection = synthetic_collection()
    collection.academic_sources[0].source_id = source_id
    with pytest.raises(ValueError):
        build_snapshot(collection, "one")


@pytest.mark.parametrize("field,value", [
    ("title", ""), ("title", "x" * 1025), ("publisher", "x" * 513),
    ("source_type", "x" * 65), ("doi", "x" * 513),
    pytest.param("evidence_summary", "x" * (MAX_SUMMARY_CHARS + 1), id="oversized-summary"),
    ("evidence_summary", 3), ("summary_source", "fulltext"), ("summary_source", ""),
])
def test_projected_fields_have_strict_bounds(field, value):
    """Malformed mutable source fields must not become silently coerced snapshot data."""
    collection = synthetic_collection()
    setattr(collection.academic_sources[0], field, value)
    with pytest.raises(ValueError):
        build_snapshot(collection, "one")


@pytest.mark.parametrize("report_ref", ["", "x" * 257, 42, True])
def test_report_reference_is_bounded_and_strict(report_ref):
    """Only a bounded caller-provided string can define the report binding."""
    with pytest.raises(ValueError):
        build_snapshot(synthetic_collection(), report_ref)


def test_snapshot_count_and_total_text_bounds(snapshot):
    """Per-row limits alone must not permit an unbounded aggregate snapshot."""
    collection = synthetic_collection()
    collection.academic_sources = [collection.academic_sources[0].model_copy(update={"source_id": f"A{i}"})
                                   for i in range(1, MAX_SOURCES + 2)]
    with pytest.raises(ValueError, match="source budget"):
        build_snapshot(collection, "one")
    source = snapshot.sources[0].model_dump()
    rows = tuple(SnapshotSource(**{**source, "source_id": f"A{i}", "summary": "x" * MAX_SUMMARY_CHARS})
                 for i in range(1, MAX_TOTAL_SUMMARY_CHARS // MAX_SUMMARY_CHARS + 2))
    with pytest.raises(ValueError, match="summary budget"):
        ReportEvidenceSnapshot(report_ref="one", sources=rows)


def test_hashes_bind_projected_metadata_text_and_report_ref():
    """The same A1 label in different reports is not interchangeable evidence."""
    collection = synthetic_collection()
    first = build_snapshot(collection, "one")
    second = build_snapshot(collection, "two")
    assert first.snapshot_hash != second.snapshot_hash
    assert first.source_hash(first.sources[0]) != second.source_hash(second.sources[0])
    for field, value in (("title", "Changed title"), ("evidence_summary", "Changed text"),
                         ("summary_source", "search_snippet"), ("publisher", "Other publisher")):
        changed = collection.model_copy(deep=True)
        setattr(changed.academic_sources[0], field, value)
        other = build_snapshot(changed, "one")
        assert other.snapshot_hash != first.snapshot_hash
        assert other.source_hash(other.sources[0]) != first.source_hash(first.sources[0])


def test_lookup_is_literal_casefolded_bounded_and_reports_total(snapshot):
    """Substring search must not execute regexes or hide matches beyond the hit cap."""
    assert lookup_sources(snapshot, "STRASSE")["hits"][0]["source_id"] == "A1"
    assert lookup_sources(snapshot, "[literal]")["total_count"] == 1
    assert lookup_sources(snapshot, ".*")["total_count"] == 0
    row = snapshot.sources[0].model_dump()
    many = ReportEvidenceSnapshot(report_ref="many", sources=tuple(
        SnapshotSource(**{**row, "source_id": f"A{i}"}) for i in range(1, 8)))
    result = lookup_sources(many, "sensor")
    assert result["total_count"] == 7 and result["truncated"] is True
    assert [hit["source_id"] for hit in result["hits"]] == ["A1", "A2", "A3", "A4", "A5"]
    assert all("summary" not in hit and "url" not in hit and "evidence_id" not in hit for hit in result["hits"])


@pytest.mark.parametrize("query", ["", "x" * 257, True, 3, None])
def test_query_bounds_are_strict(snapshot, query):
    """Queries cannot gain meaning through coercion or exceed the advertised bound."""
    with pytest.raises(ValueError):
        lookup_sources(snapshot, query)


@pytest.mark.parametrize("field,value", [
    ("offset", True), ("offset", "0"), ("offset", 0.0), ("offset", -1),
    ("length", True), ("length", "2"), ("length", 1.0), ("length", 0), ("length", 1501),
    ("source_id", 1),
])
def test_read_arguments_refuse_coercion(snapshot, field, value):
    """Boolean and numeric-looking strings must not become offsets or lengths."""
    args = {"source_id": "A1", "offset": 0, "length": 2, field: value}
    with pytest.raises(ValueError):
        read_source(snapshot, **args)


@pytest.mark.parametrize("extra", ["path", "url", "report_ref", "report_id", "snapshot", "provider"])
def test_tool_arguments_have_no_scope_parameters(extra):
    """The model cannot redirect a read by extending the tool argument object."""
    with pytest.raises(ValueError):
        ReadArguments.model_validate({"source_id": "A1", "offset": 0, "length": 1, extra: "other"})


def test_unicode_windows_are_verbatim_half_open_and_saved_only(snapshot):
    """UTF-16 or byte slicing would corrupt emoji, combining marks and CJK text."""
    result = read_source(snapshot, "A1", 1, 4)
    assert result["text"] == "测🙂e\u0301"
    assert (result["start"], result["end"]) == (1, 5)
    assert result["stored_length"] == len(snapshot.sources[0].summary)
    assert result["window_truncated"] is True
    assert result["origin"] == "abstract"
    full = read_source(snapshot, "A1", 0, 1500)
    assert full["text"] == snapshot.sources[0].summary
    assert full["window_truncated"] is False
    assert full["text_scope"] == "saved_summary_only"
    assert full["content_warning"] == CONTENT_WARNING
    assert read_source(snapshot, "P1", 0, 1500)["origin"] == "search_snippet"


def test_unknown_source_missing_text_and_empty_window_stay_distinct(snapshot):
    """Absence is not a successful empty evidence read or a different-source fallback."""
    assert read_source(snapshot, "A99", 0, 1) == {"status": "unknown_source"}
    missing = read_source(snapshot, "M1", 0, 1)
    assert missing["status"] == "missing_text" and missing["origin"] == "unknown"
    assert missing["stored_length"] == 0 and "text" not in missing
    size = snapshot.sources[0].stored_length
    assert read_source(snapshot, "A1", size, 1)["status"] == "empty_window"
    assert read_source(snapshot, "A1", size + 1, 1)["status"] == "offset_out_of_range"
    collection = synthetic_collection()
    collection.academic_sources[0].evidence_summary = ""
    assert read_source(build_snapshot(collection, "one"), "A1", 0, 1)["status"] == "missing_text"
    del collection.academic_sources[0].evidence_summary
    del collection.academic_sources[0].summary_source
    missing = build_snapshot(collection, "one").sources[0]
    assert missing.summary is None and missing.origin == "unknown"


def test_catalog_exposes_bounds_without_private_scope_or_saved_text(snapshot):
    """The initial catalog must not leak a report reference or bypass bounded reads."""
    payload = catalog_payload(snapshot)
    assert payload["bounds"] == {"query_length": [1, 256], "max_hits": 5,
                                 "offset_min": 0, "read_length": [1, 1500]}
    assert payload["source_count"] == 3
    assert payload["content_warning"] == CONTENT_WARNING
    assert snapshot.report_ref not in str(payload)
    assert snapshot.sources[0].summary not in str(payload)
