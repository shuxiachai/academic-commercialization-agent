"""Fresh engineering controls; no old cohorts, provider calls or quality labels."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

from pydantic import ValidationError
from pydantic_core import PydanticSerializationError
import pytest

from academic_agent import report_evidence_source_locator as locator
from academic_agent.report_evidence_catalog_followup import build_catalog
from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, SnapshotSource, content_hash
from report_evidence_source_locator_demo import main, synthetic_snapshot


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def call(source_id="A101", *, arguments=None, content=None, name="read_source"):
    return {"role": "assistant", "content": content, "tool_calls": [{
        "id": "locator_control", "type": "function",
        "function": {"name": name, "arguments": arguments if arguments is not None else json.dumps({"source_id": source_id})},
    }]}


def snapshot_with_text(text):
    snapshot = synthetic_snapshot()
    source = snapshot.sources[0].model_copy(update={"summary": text})
    return ReportEvidenceSnapshot(report_ref=snapshot.report_ref, sources=(source,))


def many_sources(count, title="Synthetic spool record"):
    return ReportEvidenceSnapshot(report_ref="locator-fresh-boundary", sources=tuple(
        SnapshotSource(
            source_id=f"A{index + 1}", group="academic", title=title,
            publisher="Synthetic notebook", source_type="academic", accessed_date="2026-09-18",
            summary=f"Unique saved spool note {index + 1}.",
        ) for index in range(count)
    ))


class Script:
    def __init__(self, reply):
        self.reply = reply
        self.requests = []

    def __call__(self, request, /):
        self.requests.append(deepcopy(request))
        return self.reply(request) if callable(self.reply) else deepcopy(self.reply)


@pytest.fixture
def reader(monkeypatch):
    """Spy on the real positional local read, not merely claimed result counters."""
    original = locator.read_source
    spy = Mock(wraps=original)
    monkeypatch.setattr(locator, "read_source", spy)
    return spy


def run(snapshot, reply=None, question="Locate the saved note."):
    script = Script(call() if reply is None else reply)
    result = locator.locate_saved_source(snapshot, question, selector=script)
    wire = locator.render_locator_result(result)
    payload = json.loads(wire)
    assert canonical(payload).decode() == wire
    assert payload == result.model_dump(mode="json")
    return result, payload, script


def test_actual_selection_read_serialization_preserves_exact_saved_text(reader):
    """Substituting tool-call prose for saved bytes must fail this delivery assertion."""
    text = "  保存文本 🌿 e\u0301\n<script>untrusted()</script> \\ \"  "
    snapshot = snapshot_with_text(text)
    before = snapshot.model_dump()
    question = " \nWhich saved note?\t "
    result, payload, script = run(snapshot, call(), question)
    request = script.requests[0]
    assert len(script.requests) == payload["callback_entries"] == 1
    assert len(request["messages"]) == 3
    assert request["messages"][1] == {"role": "user", "content": question}
    assert json.loads(request["messages"][2]["content"]) == build_catalog(snapshot)
    assert all(source.summary not in str(request) for source in snapshot.sources)
    assert snapshot.report_ref not in str(request)
    parameters = request["tools"][0]["function"]["parameters"]
    assert set(parameters["properties"]) == {"source_id"}
    assert parameters["properties"]["source_id"]["enum"] == ["A101"]
    assert parameters["required"] == ["source_id"] and parameters["additionalProperties"] is False
    assert len(request["tools"]) == 1 and request["tool_choice"] == "auto"
    assert payload["callback_bytes"] == len(canonical(request)) <= 12 * 1024
    reader.assert_called_once()
    actual_snapshot, source_id, offset, length = reader.call_args.args
    assert reader.call_args.kwargs == {}
    assert actual_snapshot is not snapshot and actual_snapshot.sources[0] is not snapshot.sources[0]
    assert actual_snapshot.model_dump() == before and snapshot.model_dump() == before
    assert (source_id, offset, length) == ("A101", 0, 1500)
    assert payload["state"] == "excerpt"
    assert payload["saved_text"]["text"] == text
    assert payload["saved_text"] == {
        "text": text, "start": 0, "end": len(text), "window_truncated": False,
        "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "text_scope": "saved_summary_only",
    }
    assert payload["source"] == {
        **snapshot.sources[0].model_dump(exclude={"summary"}),
        "stored_length": len(text), "snapshot_hash": snapshot.snapshot_hash,
        "source_hash": snapshot.source_hash(snapshot.sources[0]), "summary_hash": content_hash(text),
    }
    assert payload["catalog"]["catalog_hash"] == content_hash(build_catalog(snapshot))
    assert payload["read_attempts"] == payload["read_completed"] == 1
    assert result.selection_relevance == result.semantic_support == "not_assessed"
    assert set(payload) == {
        "method_id", "state", "reason", "catalog", "source", "saved_text",
        "callback_entries", "callback_bytes", "read_attempts", "read_completed",
        "selection_relevance", "semantic_support",
    }
    assert "MODEL_PROSE_MUST_NOT_APPEAR" not in locator.render_locator_result(result)


def test_catalog_is_only_saved_order_title_id_metadata(reader):
    """Non-title metadata must not hitchhike into the selector request."""
    snapshot = synthetic_snapshot()
    source = snapshot.sources[0].model_copy(update={
        "url": "https://synthetic.invalid/PRIVATE_LOCATOR", "doi": "PRIVATE_DOI",
        "publisher": "PRIVATE_PUBLISHER",
    })
    snapshot = ReportEvidenceSnapshot(report_ref="PRIVATE_REFERENCE", sources=(source,))
    _, payload, script = run(snapshot)
    request = canonical(script.requests[0]).decode()
    for secret in ("PRIVATE_LOCATOR", "PRIVATE_DOI", "PRIVATE_PUBLISHER", "PRIVATE_REFERENCE", "shelf-life"):
        assert secret not in request
    assert payload["source"]["doi"] == "PRIVATE_DOI"


def test_only_absent_null_or_empty_tool_content_is_admitted(reader):
    for content in (None, ""):
        result, _, _ = run(synthetic_snapshot(), call(content=content))
        assert result.state == "excerpt"
    reply = call()
    del reply["content"]
    result, _, _ = run(synthetic_snapshot(), reply)
    assert result.state == "excerpt" and reader.call_count == 3


@pytest.mark.parametrize("text,state", [(None, "missing_text"), ("", "missing_text"), (" \t\n\u2003", "blank_text")])
def test_missing_and_blank_are_completed_reads_not_excerpts(reader, text, state):
    """Whitespace is delivered verbatim but cannot be labeled useful saved evidence."""
    result, payload, _ = run(snapshot_with_text(text))
    assert result.state == state
    assert payload["read_attempts"] == payload["read_completed"] == reader.call_count == 1
    assert (payload["saved_text"]["text"] if payload["saved_text"] else None) == (text if text else None)


def test_empty_snapshot_never_enters_callback_or_reader(reader):
    snapshot = ReportEvidenceSnapshot(report_ref="fresh-empty-control", sources=())
    result, payload, script = run(snapshot)
    assert result.state == "no_sources"
    assert script.requests == [] and reader.call_count == 0
    assert payload["callback_bytes"] is None
    assert payload["callback_entries"] == payload["read_attempts"] == payload["read_completed"] == 0


@pytest.mark.parametrize("reply,reason", [
    ({"role": "assistant", "content": '{"action":"decline"}'}, "selector_declined"),
    ({"role": "assistant", "refusal": "PRIVATE_MODEL_REFUSAL"}, "selector_refused"),
])
def test_only_explicit_decline_or_standalone_refusal_is_declined(reader, reply, reason):
    result, payload, script = run(synthetic_snapshot(), reply)
    assert result.state == "declined" and result.reason == reason
    assert len(script.requests) == 1 and reader.call_count == 0
    assert payload["source"] is None and payload["saved_text"] is None
    assert "PRIVATE_MODEL_REFUSAL" not in locator.render_locator_result(result)


@pytest.mark.parametrize("reply,reason", [
    (call(content="PRIVATE_GENERATED_PROSE"), "mixed_response"),
    (call(content=" "), "mixed_response"),
    ({"role": "assistant", "content": "PRIVATE_FREE_ANSWER"}, "invalid_decline"),
    ({"role": "assistant", "content": '{"action":"decline","reason":"PRIVATE_REASON"}'}, "invalid_decline"),
    ({"role": "assistant", "content": '{"action":"decline","action":"decline"}'}, "invalid_decline"),
    ({"role": "assistant", "content": '{"action":false}'}, "invalid_decline"),
    ({"role": "assistant", "content": '{"action":NaN}'}, "invalid_decline"),
    ({"role": "assistant", "refusal": "PRIVATE_REFUSAL", "content": '{"action":"decline"}'}, "invalid_assistant_message"),
    ({"role": "user", "content": '{"action":"decline"}'}, "invalid_assistant_message"),
    ({"role": "assistant", "content": {"action": "decline"}}, "invalid_assistant_message"),
    ({**call(), "tool_calls": call()["tool_calls"] * 2}, "invalid_assistant_message"),
    ({**call(), "extra": "PRIVATE_EXTRA"}, "invalid_assistant_message"),
    (call(name="lookup_sources"), "unadvertised_tool"),
    (call(arguments='{"source_id":"A101","source_id":"A101"}'), "invalid_arguments"),
    (call(arguments='{"source_id":"A101","offset":0,"length":1500}'), "invalid_arguments"),
    (call(arguments='{"source_id":101}'), "invalid_arguments"),
    (call(arguments='{"source_id":true}'), "invalid_arguments"),
    (call(arguments='["A101"]'), "invalid_arguments"),
    (call(arguments='{"source_id":"A101"}' + " " * 4096), "invalid_arguments"),
    (call(source_id="A999"), "read_id_not_permitted"),
])
def test_strict_contract_failures_never_read_or_leak(reader, reply, reason):
    """A failed selector contract is not a decline or an invitation to repair."""
    result, payload, script = run(synthetic_snapshot(), reply)
    assert result.state == "failed" and result.reason == reason
    assert len(script.requests) == 1 and reader.call_count == 0
    assert payload["read_attempts"] == payload["read_completed"] == 0
    assert payload["source"] is payload["saved_text"] is None
    assert "PRIVATE_" not in locator.render_locator_result(result)


def test_hidden_id_is_rejected_before_actual_read(reader):
    """Bypassing the visible-ID guard must fail even for a real hidden source."""
    snapshot = many_sources(33)
    result, payload, script = run(snapshot, call(source_id="A33"))
    assert result.state == "failed" and result.reason == "read_id_not_permitted"
    assert reader.call_count == payload["read_attempts"] == 0
    catalog = json.loads(script.requests[0]["messages"][2]["content"])
    assert catalog["returned_count"] == 32 and catalog["omitted_count"] == 1
    assert catalog["coverage"] == "partial"
    assert payload["catalog"]["returned_count"] == 32
    assert [entry["source_id"] for entry in catalog["entries"]] == [f"A{i}" for i in range(1, 33)]


def test_long_selected_text_is_out_of_scope_without_prefix_read(reader):
    """Removing the length guard must fail; a truncated prefix is not a full read."""
    result, payload, script = run(snapshot_with_text("界" * 1501))
    assert result.state == "out_of_scope" and result.reason == "selected_text_too_long"
    assert len(script.requests) == 1
    assert reader.call_count == payload["read_attempts"] == payload["read_completed"] == 0
    assert payload["source"]["stored_length"] == 1501 and payload["saved_text"] is None


def test_exact_saved_codepoint_limit_and_catalog_byte_limit(reader):
    text = "🌿" * 1500
    _, payload, _ = run(snapshot_with_text(text))
    assert payload["saved_text"]["text"] == text and payload["saved_text"]["end"] == 1500
    snapshot = many_sources(32, title="🌿" * 257)
    result, payload, script = run(snapshot, call(source_id="A1"))
    catalog = json.loads(script.requests[0]["messages"][2]["content"])
    assert catalog == build_catalog(snapshot)
    assert catalog["coverage"] == "partial" and catalog["returned_count"] < 32
    assert catalog["title_truncation_count"] == catalog["returned_count"]
    assert all(entry["title"] == "🌿" * 256 for entry in catalog["entries"])
    assert payload["catalog"]["catalog_bytes"] == len(canonical(catalog)) <= 6144
    assert result.state == "excerpt"


def test_full_callback_byte_boundary_before_entry(reader):
    """The limit covers escaping, instructions, tool schema and original question."""
    snapshot = synthetic_snapshot()
    _, payload, _ = run(snapshot, question="x")
    base = payload["callback_bytes"] - 1
    budget = 12 * 1024 - base
    # Escaped BMP code points cost six canonical ASCII bytes, not one.
    question = "界" * (budget // 6) + "x" * (budget % 6)
    assert 1 <= len(question) < 4096
    result, payload, script = run(snapshot, question=question)
    assert result.state == "excerpt" and payload["callback_bytes"] == 12 * 1024
    assert script.requests[0]["messages"][1]["content"] == question
    reader.reset_mock()
    result, payload, script = run(snapshot, question=question + "x")
    assert result.reason == "callback_budget_exceeded" and result.state == "out_of_scope"
    assert payload["callback_bytes"] == 12 * 1024 + 1
    assert script.requests == [] and reader.call_count == 0


@pytest.mark.parametrize("question", ["", " \t\n", "x" * 4097, 123, True])
def test_invalid_question_raises_before_callback(reader, question):
    script = Script(call())
    with pytest.raises(ValueError, match="^invalid_question$"):
        locator.locate_saved_source(synthetic_snapshot(), question, selector=script)
    assert script.requests == [] and reader.call_count == 0


def test_maximum_question_preserves_raw_characters(reader):
    question = " " + "x" * 4094 + "\n"
    _, _, script = run(synthetic_snapshot(), question=question)
    assert script.requests[0]["messages"][1]["content"] == question


def test_bypass_constructed_snapshot_and_noncallable_fail_before_entry(reader):
    snapshot = synthetic_snapshot()
    bad_source = snapshot.sources[0].model_copy(update={"summary": 123})
    bad = snapshot.model_copy(update={"sources": (bad_source,)})
    script = Script(call())
    # No warning suppression: serialization itself must fail before validation.
    with pytest.raises(PydanticSerializationError):
        bad.model_dump(warnings="error")
    with pytest.raises(ValueError, match="^invalid_snapshot$"):
        locator.locate_saved_source(bad, "Locate.", selector=script)
    with pytest.raises(ValueError, match="^invalid_selector$"):
        locator.locate_saved_source(snapshot, "Locate.", selector=None)
    assert script.requests == [] and reader.call_count == 0


def test_mutated_request_cannot_expand_visible_ids_or_poison_next_request(reader):
    snapshot = many_sources(33)
    before = snapshot.model_dump()

    def mutate(request):
        request["tools"][0]["function"]["parameters"]["properties"]["source_id"]["enum"].append("A33")
        request["messages"][1]["content"] = "MUTATED"
        request["messages"][2]["content"] = '{"entries":[{"source_id":"A33"}]}'
        return call(source_id="A33")

    result, _, _ = run(snapshot, mutate)
    assert result.reason == "read_id_not_permitted" and reader.call_count == 0
    result, _, script = run(snapshot, call(source_id="A1"))
    assert result.state == "excerpt" and snapshot.model_dump() == before
    assert "A33" not in script.requests[0]["tools"][0]["function"]["parameters"]["properties"]["source_id"]["enum"]
    assert script.requests[0]["messages"][1]["content"] == "Locate the saved note."


def test_callback_cannot_mutate_trusted_snapshot_via_retained_original(reader):
    snapshot = synthetic_snapshot()
    original_text = snapshot.sources[0].summary

    def mutate(_request):
        # Frozen Pydantic blocks normal assignment, not hostile Python. Detach
        # before entering the trusted callback even when it retained the input.
        object.__setattr__(snapshot.sources[0], "summary", "MUTATED_ORIGINAL")
        return call()

    _, payload, _ = run(snapshot, mutate)
    assert payload["saved_text"]["text"] == original_text
    assert reader.call_args.args[0].sources[0].summary == original_text


@pytest.mark.parametrize("stage", ["selector", "reader"])
def test_execution_errors_are_unavailable_without_raw_diagnostics(reader, stage):
    class PrivateFailure(RuntimeError):
        pass

    def fail(_request):
        raise PrivateFailure("PRIVATE_ERROR_CONTENT")

    if stage == "reader":
        reader.side_effect = PrivateFailure("PRIVATE_READ_CONTENT")
    result, payload, script = run(synthetic_snapshot(), fail if stage == "selector" else call())
    assert result.state == "unavailable"
    assert result.reason == ("selector_error" if stage == "selector" else "read_error")
    assert len(script.requests) == 1
    assert payload["read_attempts"] == reader.call_count == int(stage == "reader")
    assert payload["read_completed"] == 0 and payload["saved_text"] is None
    assert "PRIVATE_" not in locator.render_locator_result(result)
    assert "PrivateFailure" not in locator.render_locator_result(result)


def test_incomplete_or_inconsistent_actual_read_never_becomes_excerpt(reader):
    """A self-consistent prefix/hash still fails equality with the whole saved text."""
    snapshot = synthetic_snapshot()
    actual = reader._mock_wraps(snapshot, "A101", 0, 1500)
    prefix = actual["text"][:8]
    actual.update(text=prefix, end=len(prefix), stored_length=len(prefix), window_truncated=False,
                  text_sha256=hashlib.sha256(prefix.encode()).hexdigest(), summary_hash=content_hash(prefix))
    reader.return_value = actual
    result, payload, _ = run(snapshot)
    assert result.reason == "invalid_read_result" and result.state == "failed"
    assert payload["read_attempts"] == payload["read_completed"] == reader.call_count == 1
    assert payload["saved_text"] is None


def test_renderer_revalidates_bypassed_nested_and_top_level_results(reader):
    result, _, _ = run(synthetic_snapshot())
    malformed = result.model_copy(update={"source": "PRIVATE_MALFORMED_SOURCE"})
    with pytest.raises(PydanticSerializationError):
        malformed.model_dump(warnings="error")
    with pytest.raises(ValueError, match="^invalid_locator_result$"):
        locator.render_locator_result(malformed)
    for updates in (
        {"state": "declined"}, {"reason": "PRIVATE_REASON"}, {"callback_entries": True},
        {"read_completed": 0}, {"saved_text": None}, {"semantic_support": "supported"},
        {"source": result.source.model_copy(update={"stored_length": 1501})},
        {"catalog": result.catalog.model_copy(update={"returned_count": 0})},
        {"saved_text": result.saved_text.model_copy(update={"text": "MODEL_PROSE"})},
        {"saved_text": result.saved_text.model_copy(update={"window_truncated": True})},
        {"saved_text": result.saved_text.model_copy(update={"start": False})},
        {"saved_text": result.saved_text.model_copy(update={"window_truncated": 0})},
    ):
        with pytest.raises(ValueError, match="^invalid_locator_result$"):
            locator.render_locator_result(result.model_copy(update=updates))
    with pytest.raises(ValidationError):
        result.state = "declined"
    with pytest.raises(ValidationError):
        result.saved_text.text = "MUTATED"
    with pytest.raises(ValueError, match="^invalid_locator_result$"):
        locator.render_locator_result({"state": "excerpt"})


def test_demo_is_scripted_no_io_and_no_generated_answer(monkeypatch, capsys):
    """Scoped guards must not leak into pytest's own configuration/teardown."""
    def forbidden(*_args, **_kwargs):
        raise AssertionError("unexpected_demo_io")

    # Imports finish before the guard. No file, credential or network work
    # occurs inside the callback-only implementation or fresh demo.
    with monkeypatch.context() as guard:
        guard.setattr("builtins.open", forbidden)
        guard.setattr("pathlib.Path.open", forbidden)
        guard.setattr("os.getenv", forbidden)
        guard.setattr("socket.create_connection", forbidden)
        main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "scripted_offline" and payload["selection_quality"] == "not_assessed"
    assert [item["state"] for item in payload["results"]] == ["excerpt", "missing_text", "declined"]
    assert all("answer" not in item for item in payload["results"])


def test_demo_cli_rejects_arguments_without_echo():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "report_evidence_source_locator_demo.py"), "--key=PRIVATE_ARGUMENT"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0 and result.stdout == ""
    assert result.stderr.strip() == "This scripted_offline demo accepts no arguments."
    assert "PRIVATE_ARGUMENT" not in result.stderr
