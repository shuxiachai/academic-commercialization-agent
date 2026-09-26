"""Contract tests for the offline lexical candidate and callback-only bridge."""

import json
from collections.abc import Mapping
from unittest.mock import patch

import pytest

from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, SnapshotSource
from academic_agent import saved_source_candidate_search as candidate_search
from academic_agent.saved_source_candidate_search import (
    RESULT_MAX_BYTES,
    QUERY_POLICY,
    propose_saved_candidates,
    render_candidate_result,
    search_saved_candidates,
)


def source(number: int, title: str = "other", summary: str | None = None) -> SnapshotSource:
    return SnapshotSource(source_id=f"A{number}", group="academic", title=title, summary=summary,
                          publisher="synthetic", source_type="test", accessed_date="2026-09-26")


def snapshot(*sources: SnapshotSource) -> ReportEvidenceSnapshot:
    return ReportEvidenceSnapshot(report_ref="offline-control", sources=tuple(sources))


class MappingProxy(Mapping):
    def __init__(self, values):
        self.values = values

    def __getitem__(self, key):
        return self.values[key]

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)


class ProposalDict(dict):
    pass


class Key(str):
    pass


class Value(str):
    pass


def test_overlap_case_boundaries_and_separate_fields_are_preserved():
    result = search_saved_candidates(snapshot(
        source(1, "forgo go go"), source(2, "Machine learning"), source(3, "phase", "change"),
        source(4, "dose–response"), source(5, "phase-change₂"),
    ), "go-go")
    assert result["normalized_additions"]["state"] == "additions_found"
    assert result["normalized_additions"]["hits"][0]["source_id"] == "A1"
    assert search_saved_candidates(snapshot(source(1, "Machine learning")), "machine-learning")["normalized_additions"]["state"] == "no_additions"
    assert search_saved_candidates(snapshot(source(1, "phase", "change")), "phase change")["normalized_additions"]["state"] == "no_additions"
    assert search_saved_candidates(snapshot(source(1, "dose–response")), "dose response")["normalized_additions"]["state"] == "no_additions"
    assert search_saved_candidates(snapshot(source(1, "phase-change₂")), "phase change")["normalized_additions"]["state"] == "no_additions"


def test_literal_mask_includes_hidden_sixth_hit_and_lanes_cap_independently():
    sources = [source(i, "phase-change", "phase change") for i in range(1, 7)]
    sources.extend(source(i, "phase change") for i in range(7, 14))
    result = search_saved_candidates(snapshot(*sources), "phase-change")
    assert result["literal_result"]["total_count"] == 6
    lane = result["normalized_additions"]
    assert lane["total_count"] == 7 and len(lane["hits"]) == 5 and lane["truncated"] is True
    assert [item["source_id"] for item in lane["hits"]] == ["A7", "A8", "A9", "A10", "A11"]


@pytest.mark.parametrize("query", [None, "", " ", 2, "a\ud800 b", "x" * 257])
def test_invalid_query_does_not_create_a_zero_match_observation(query):
    result = search_saved_candidates(snapshot(source(1)), query)
    assert result["normalized_additions"]["state"] == "invalid_query"
    assert result["literal_result"] is None


def test_snapshot_is_revalidated_metadata_only_and_immutable():
    original = snapshot(source(1, "phase-change", None), source(2, "other", "raw summary must not appear"))
    before = original.model_dump()
    result = search_saved_candidates(original, "phase change")
    assert original.model_dump() == before
    assert result["source_observation"] == {
        "source_count": 2, "missing_summary_count": 1,
        "empty_summary_count": 0, "whitespace_only_summary_count": 0,
    }
    assert "raw summary must not appear" not in json.dumps(result)
    bad = original.model_copy(update={"sources": tuple(source(i) for i in range(1, 258))})
    assert search_saved_candidates(bad, "phase change")["normalized_additions"]["state"] == "unavailable"


def test_summary_observations_and_long_saved_text_remain_bounded_but_searchable():
    result = search_saved_candidates(snapshot(
        source(1, "other", None), source(2, "other", ""), source(3, "other", " \t"),
        source(4, "other", "x" * 1501 + " phase-change"),
    ), "phase change")
    assert result["source_observation"] == {
        "source_count": 4, "missing_summary_count": 1,
        "empty_summary_count": 1, "whitespace_only_summary_count": 1,
    }
    assert result["normalized_additions"]["hits"][0]["source_id"] == "A4"


def test_callback_gets_only_question_and_fixed_policy_and_uses_detached_snapshot():
    original = snapshot(source(1, "phase-change"))
    calls = []

    def proposer(question, policy):
        calls.append((question, policy))
        object.__setattr__(original.sources[0], "title", "mutated")
        return {"query": "phase change"}

    result = propose_saved_candidates(original, "find source", proposer=proposer)
    assert calls == [("find source", QUERY_POLICY)]
    assert result["state"] == "completed"
    assert result["query_executions"] == result["callback_entries"] == 1
    assert result["search_result"]["normalized_additions"]["state"] == "additions_found"
    assert set(result) == {
        "state", "reason", "query", "callback_entries", "query_executions",
        "proposal_bytes", "search_result", "selection", "semantic_support",
        "unit_equivalence",
    }
    payload = render_candidate_result(result)
    assert json.loads(payload) == result and b"raw summary" not in payload


@pytest.mark.parametrize(
    ("question", "snap", "proposer", "state", "calls"),
    [
        (" ", snapshot(source(1)), lambda *_: {"query": "phase change"}, "invalid_input", 0),
        ("q", snapshot(), lambda *_: {"query": "phase change"}, "no_sources", 0),
        ("q", snapshot(source(1)), lambda *_: {"action": "decline"}, "proposal_declined", 1),
        ("q", snapshot(source(1)), lambda *_: {"query": ""}, "invalid_proposal", 1),
    ],
)
def test_callback_dispatch_boundaries(question, snap, proposer, state, calls):
    observed = []
    def spy(*args):
        observed.append(args)
        return proposer(*args)
    result = propose_saved_candidates(snap, question, proposer=spy)
    assert result["state"] == state and len(observed) == calls
    assert result["query_executions"] == (1 if state == "completed" else 0)


def test_callback_failure_bad_shape_awaitable_and_unavailable_are_distinct():
    snap = snapshot(source(1))
    def raises(*_):
        raise RuntimeError("PRIVATE_CALLBACK_DETAIL")
    assert propose_saved_candidates(snap, "q", proposer=raises)["state"] == "callback_failure"
    assert "PRIVATE_CALLBACK_DETAIL" not in json.dumps(propose_saved_candidates(snap, "q", proposer=raises))
    assert propose_saved_candidates(snap, "q", proposer=lambda *_: {"query": "x", "extra": "no"})["state"] == "invalid_proposal"
    async def response():
        return {"query": "phase change"}
    assert propose_saved_candidates(snap, "q", proposer=lambda *_: response())["reason"] == "awaitable_response"


@pytest.mark.parametrize("response", [
    '{"query":"phase change"}',
    MappingProxy({"query": "phase change"}),
    ProposalDict(query="phase change"),
    {Key("query"): "phase change"},
    {"query": Value("phase change")},
    {"query": {"nested": "object"}},
])
def test_only_plain_exact_one_item_proposal_dict_is_accepted(response):
    result = propose_saved_candidates(snapshot(source(1)), "q", proposer=lambda *_: response)
    assert result["state"] == "invalid_proposal"
    assert result["proposal_bytes"] is None and result["query_executions"] == 0


@pytest.mark.parametrize("question, state", [
    ("q" * 4096, "completed"), ("q" * 4097, "invalid_input"), ("q\ud800", "invalid_input"),
])
def test_question_unicode_bounds_and_noncallable_boundary(question, state):
    result = propose_saved_candidates(
        snapshot(source(1)), question, proposer=lambda *_: {"query": "phase change"}
    )
    assert result["state"] == state
    assert propose_saved_candidates(snapshot(source(1)), "q", proposer=object())["state"] == "invalid_input"


def test_invalid_model_copy_is_rejected_before_callback_without_warning_or_dispatch():
    bad = snapshot(source(1)).model_copy(update={"sources": ("not-a-source",)})
    calls = []
    result = propose_saved_candidates(bad, "q", proposer=lambda *_: calls.append("called"))
    assert result["state"] == "snapshot_unavailable"
    assert result["callback_entries"] == result["query_executions"] == 0
    assert calls == []


@pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit])
def test_callback_base_exceptions_are_not_swallowed(exception):
    def raises(*_):
        raise exception()
    with pytest.raises(exception):
        propose_saved_candidates(snapshot(source(1)), "q", proposer=raises)


def test_search_unavailable_keeps_unknown_counts_and_one_real_callback_query():
    with patch.object(candidate_search, "lookup_sources", side_effect=ValueError("private")) as lookup:
        result = propose_saved_candidates(
            snapshot(source(1)), "q", proposer=lambda *_: {"query": "phase change"}
        )
    assert lookup.call_count == 1
    assert result["state"] == "search_unavailable"
    assert result["callback_entries"] == result["query_executions"] == 1
    lane = result["search_result"]["normalized_additions"]
    assert lane["total_count"] is lane["hits"] is lane["truncated"] is None


def test_socket_and_read_source_are_not_used_and_result_is_exactly_serialized():
    with patch("socket.socket", side_effect=AssertionError) as socket, patch.object(
        candidate_search, "lookup_sources", wraps=candidate_search.lookup_sources
    ) as lookup, patch(
        "academic_agent.report_evidence_snapshot.read_source", side_effect=AssertionError
    ) as reader:
        result = propose_saved_candidates(
            snapshot(source(1, "phase-change")), "q", proposer=lambda *_: {"query": "phase change"}
        )
    payload = render_candidate_result(result)
    assert socket.call_count == reader.call_count == 0 and lookup.call_count == 1
    assert json.loads(payload) == result
    assert payload == json.dumps(result, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def test_unsupported_numeric_and_symbol_queries_keep_legacy_hits_but_not_equivalence():
    for query in ("10 mW", "dose+response", "3D imaging"):
        result = search_saved_candidates(snapshot(source(1, "Uses 10 MW and dose-response.")), query)
        assert result["normalized_additions"]["state"] == "unsupported_query"
        assert result["unit_equivalence"] == "not_assessed"
    assert search_saved_candidates(snapshot(source(1, "Uses 10 MW.")), "10 mW")["literal_result"]["total_count"] == 1


def test_max_titles_result_bound_and_renderer_rejection():
    """Both lanes must actually deliver full-size titles, not an empty payload."""
    title = "😀" * 1024
    sources = [source(i, title, "alpha-beta") for i in range(1, 6)]
    sources.extend(source(i, title, "alpha beta") for i in range(6, 11))
    result = search_saved_candidates(snapshot(*sources), "alpha-beta")
    assert len(result["literal_result"]["hits"]) == len(result["normalized_additions"]["hits"]) == 5
    payload = render_candidate_result(result)
    assert 120 * 1024 < len(payload) <= RESULT_MAX_BYTES
    assert json.loads(payload) == result
    # The locator's smaller catalog cap must not silently limit this snapshot.
    beyond_catalog = snapshot(*(source(i) for i in range(1, 33)), source(33, "alpha beta"))
    observed = search_saved_candidates(beyond_catalog, "alpha-beta")
    assert [hit["source_id"] for hit in observed["normalized_additions"]["hits"]] == ["A33"]
    with pytest.raises(ValueError, match="delivery bound"):
        render_candidate_result({"x": "😀" * RESULT_MAX_BYTES})


def test_proposal_unicode_and_result_bounds_are_real_serialized_bounds():
    emoji_query = "😀" * 256
    assert len(emoji_query) == 256
    result = propose_saved_candidates(snapshot(source(1)), "q", proposer=lambda *_: {"query": emoji_query})
    assert result["state"] == "completed" and result["proposal_bytes"] == 3084
    assert render_candidate_result(result) == json.dumps(result, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")
