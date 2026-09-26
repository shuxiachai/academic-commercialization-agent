"""Bounded offline lexical candidate search and an explicit query callback bridge.

This module performs no filesystem access, ``read_source`` calls, excerpt
delivery, provider request, or selection. Its separator lane is deliberately
lexical: it is not evidence, semantic support, or unit equivalence.
"""

from __future__ import annotations

import inspect
import json
import re
import unicodedata
from academic_agent.report_evidence_snapshot import (
    MAX_HITS,
    MAX_QUERY_CHARS,
    ReportEvidenceSnapshot,
    lookup_sources,
)

MAX_QUESTION_CHARS = 4096
MAX_PROPOSAL_BYTES = 4096
RESULT_MAX_BYTES = 160 * 1024

# The callback gets this fixed public policy and the caller's question only.
# It intentionally contains no snapshot-derived material.
QUERY_POLICY = (
    "Return exactly one proposal object: {'query': <1..256 Unicode-scalar string>} "
    "or {'action': 'decline'}. Query uses one casefold literal title/summary "
    "search, not AND or regex. A separate lexical addition preserves case and "
    "accepts only 2-4 ASCII words joined by spaces, tabs, or ASCII hyphens. "
    "Return no answer or semantic interpretation; do not add keys or explain."
)

_QUERY = re.compile(r"[A-Za-z]+(?:(?:[ \t]+|-)[A-Za-z]+){1,3}")
_PUNCTUATION = frozenset(".,;:!?()[]{}\"'")


def _scalars_string(value: object, maximum: int) -> bool:
    """Reject surrogate code points instead of silently repairing caller input."""
    return (
        type(value) is str
        and 1 <= len(value) <= maximum
        and bool(value.strip())
        and not any(0xD800 <= ord(character) <= 0xDFFF for character in value)
    )


def _lane(state: str, *, hits: list[dict[str, object]] | None = None,
          total_count: int | None = None) -> dict[str, object]:
    return {
        "state": state,
        "hits": hits,
        "total_count": total_count,
        "truncated": None if total_count is None else total_count > MAX_HITS,
        "rule": "lexical_separator_v1",
    }


def _base_search_result() -> dict[str, object]:
    return {
        "literal_result": None,
        "normalized_additions": _lane("unavailable"),
        "snapshot_hash": None,
        "source_observation": None,
        "selection": None,
        "semantic_support": "not_assessed",
        "unit_equivalence": "not_assessed",
        # Legacy casefolded substring membership is not validated equivalence.
        "literal_scope": "unchanged_casefold_substring_not_validated_equivalence",
    }


def _trusted_snapshot(snapshot: object) -> ReportEvidenceSnapshot:
    """Detach then revalidate, including malicious model_copy/model_construct values."""
    if type(snapshot) is not ReportEvidenceSnapshot:
        raise ValueError("invalid snapshot type")
    dumped = snapshot.model_dump(warnings="error")
    return ReportEvidenceSnapshot.model_validate(dumped)


def _observation(snapshot: ReportEvidenceSnapshot) -> dict[str, int]:
    return {
        "source_count": len(snapshot.sources),
        "missing_summary_count": sum(source.summary is None for source in snapshot.sources),
        "empty_summary_count": sum(source.summary == "" for source in snapshot.sources),
        "whitespace_only_summary_count": sum(
            bool(source.summary) and not source.summary.strip() for source in snapshot.sources
        ),
    }


def _unsafe_symbol(character: str) -> bool:
    category = unicodedata.category(character)
    return character in "_+-/\\°" or category[0] in "MS" or category == "Pd"


def _outer_boundary(text: str, position: int, direction: int) -> bool:
    if position < 0 or position >= len(text):
        return True
    character = text[position]
    if not character.isspace() and character not in _PUNCTUATION:
        return False
    while 0 <= position < len(text) and text[position] in " \t":
        position += direction
    return not (0 <= position < len(text) and _unsafe_symbol(text[position]))


def _matches(pattern: re.Pattern[str], text: str | None) -> bool:
    if not text:
        return False
    position = 0
    while (match := pattern.search(text, position)) is not None:
        if _outer_boundary(text, match.start() - 1, -1) and _outer_boundary(text, match.end(), 1):
            return True
        # Do not use finditer or match.end(): a rejected prefix can overlap a
        # later valid phrase (for example, "forgo go go" for "go-go").
        position = match.start() + 1
    return False


def _search_pattern(query: str) -> re.Pattern[str]:
    words = re.split(r"[ \t]+|-", query)
    return re.compile(r"(?:[ \t]+|-)".join(re.escape(word) for word in words))


def _hit(source: object) -> dict[str, object]:
    # Only bounded metadata is emitted; saved summary bytes never leave here.
    return {
        "source_id": source.source_id,
        "title": source.title,
        "origin": source.origin,
        "stored_length": source.stored_length,
        "text_status": "available" if source.summary else "missing_text",
    }


def search_saved_candidates(snapshot: object, query: object) -> dict[str, object]:
    """Return legacy literal hits plus strictly bounded separator-only additions."""
    result = _base_search_result()
    if not _scalars_string(query, MAX_QUERY_CHARS):
        result["normalized_additions"] = _lane("invalid_query")
        return result
    try:
        trusted = _trusted_snapshot(snapshot)
        result["snapshot_hash"] = trusted.snapshot_hash
        result["source_observation"] = _observation(trusted)
        literal = lookup_sources(trusted, query)
        result["literal_result"] = literal
        if _QUERY.fullmatch(query) is None:
            result["normalized_additions"] = _lane("unsupported_query")
            return result
        if not trusted.sources:
            result["normalized_additions"] = _lane("empty_snapshot", hits=[], total_count=0)
            return result

        # lookup_sources exposes at most five hits. Rebuild only its old literal
        # predicate to mask every literal member, including hidden sixth hits.
        # This distinct legacy casefold substring is not validated equivalence.
        needle = query.casefold()
        literal_ids = [
            source.source_id for source in trusted.sources
            if needle in source.title.casefold() or needle in (source.summary or "").casefold()
        ]
        if (
            literal["status"] != "ok"
            or literal["total_count"] != len(literal_ids)
            or literal["truncated"] != (len(literal_ids) > MAX_HITS)
            or [hit["source_id"] for hit in literal["hits"]] != literal_ids[:MAX_HITS]
        ):
            raise ValueError("literal predicate drift")
        literal_id_set = set(literal_ids)
        pattern = _search_pattern(query)
        additions = [
            source for source in trusted.sources
            if source.source_id not in literal_id_set
            and (_matches(pattern, source.title) or _matches(pattern, source.summary))
        ]
        result["normalized_additions"] = _lane(
            "additions_found" if additions else "no_additions",
            hits=[_hit(source) for source in additions[:MAX_HITS]],
            total_count=len(additions),
        )
    except (ValueError, TypeError, AttributeError, KeyError, OverflowError):
        # Validation/scanning failure is observable but does not expose details.
        result["literal_result"] = None
        result["normalized_additions"] = _lane("unavailable")
    return result


def _wrapper(state: str, reason: str, *, query: str | None = None,
             callback_entries: int = 0, query_executions: int = 0,
             proposal_bytes: int | None = None,
             search_result: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "state": state,
        "reason": reason,
        "query": query,
        "callback_entries": callback_entries,
        "query_executions": query_executions,
        "proposal_bytes": proposal_bytes,
        "search_result": search_result,
        "selection": None,
        "semantic_support": "not_assessed",
        "unit_equivalence": "not_assessed",
    }


def _canonical_proposal(value: object) -> tuple[str | None, str | None, int | None]:
    """Accept only a plain one-item dict, then serialize a rebuilt safe copy."""
    if type(value) is not dict or len(value) != 1:
        return None, None, None
    key, proposal_value = next(iter(value.items()))
    if type(key) is not str or type(proposal_value) is not str:
        return None, None, None
    if key == "action" and proposal_value == "decline":
        canonical = {"action": "decline"}
        return "decline", None, len(json.dumps(canonical, ensure_ascii=True, separators=(",", ":")).encode("ascii"))
    if key != "query" or not _scalars_string(proposal_value, MAX_QUERY_CHARS):
        return None, None, None
    canonical = {"query": proposal_value}
    size = len(json.dumps(canonical, ensure_ascii=True, separators=(",", ":")).encode("ascii"))
    if size > MAX_PROPOSAL_BYTES:
        return None, None, None
    return "query", proposal_value, size


def propose_saved_candidates(snapshot: object, question: object, *, proposer: object) -> dict[str, object]:
    """Call one trusted synchronous proposal callback without exposing snapshot data."""
    if not _scalars_string(question, MAX_QUESTION_CHARS) or not callable(proposer):
        return _wrapper("invalid_input", "invalid_question_or_proposer")
    try:
        trusted = _trusted_snapshot(snapshot)
    except (ValueError, TypeError, AttributeError, KeyError, OverflowError):
        return _wrapper("snapshot_unavailable", "snapshot_validation_failed")
    if not trusted.sources:
        return _wrapper("no_sources", "empty_snapshot")
    try:
        response = proposer(question, QUERY_POLICY)  # type: ignore[operator]
    except Exception:  # noqa: BLE001 - callback failures are intentionally opaque at this boundary.
        return _wrapper("callback_failure", "callback_raised", callback_entries=1)
    if inspect.iscoroutine(response):
        # Close a real coroutine so rejecting it does not create a warning; do
        # not call arbitrary close methods on foreign awaitable objects.
        response.close()
        return _wrapper("invalid_proposal", "awaitable_response", callback_entries=1)
    if inspect.isawaitable(response):
        return _wrapper("invalid_proposal", "awaitable_response", callback_entries=1)
    action, query, proposal_bytes = _canonical_proposal(response)
    if action is None:
        return _wrapper("invalid_proposal", "invalid_proposal_shape", callback_entries=1)
    if action == "decline":
        return _wrapper("proposal_declined", "proposal_declined", callback_entries=1,
                        proposal_bytes=proposal_bytes)
    search_result = search_saved_candidates(trusted, query)
    state = "search_unavailable" if search_result["normalized_additions"]["state"] == "unavailable" else "completed"
    return _wrapper(state, "search_completed" if state == "completed" else "search_unavailable",
                    query=query, callback_entries=1, query_executions=1,
                    proposal_bytes=proposal_bytes, search_result=search_result)


def render_candidate_result(result: dict[str, object]) -> bytes:
    """Render a bounded canonical JSON result for an explicit delivery seam."""
    rendered = json.dumps(result, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    if len(rendered) > RESULT_MAX_BYTES:
        raise ValueError("candidate result exceeds delivery bound")
    return rendered
