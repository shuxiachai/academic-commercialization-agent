"""Failed reruns restore saved input only across the privileged HTTP seams.

These reads never start a worker or call a provider. A shared run URL remains
a report read capability, not permission to recover the owner's input prose.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from academic_agent.run_spec import DecisionContext, RUN_SPEC_FILENAME, RunSpec
from api import access, accounts, runs
from api.main import app


RUN_ID = "20261125T010203Z-0123456789abcdef0123456789abcdef"
OWNER_HEADERS = {"X-Access-Code": "for-owner"}
CONTEXT = {
    "asset_description": "A saved sensor prototype",
    "target_application": "Hospital monitoring",
    "decision_owner": "The original product team",
    "decision_type": "Fund a pilot",
    "jurisdiction": "Australia",
    "time_horizon": "Twelve months",
    "constraints": "A fixed development budget",
    "success_criteria": "Meet the saved sensitivity target",
    "success_criteria_authority": "owner_approved",
}


@pytest.fixture
def failed_run(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(access, "ACCESS_CODE", None)
    monkeypatch.setattr(access, "ACCESS_CODES", "for-owner,for-other")
    monkeypatch.setattr(access, "ADMIN_CODE", "for-admin")
    monkeypatch.setattr(accounts, "enabled", lambda: False)
    directory = tmp_path / RUN_ID
    directory.mkdir()
    (directory / ".owner").write_text(access.owner_id("for-owner"), encoding="utf-8")
    (directory / "status.json").write_text(
        json.dumps({"done": False, "topic": "Saved topic", "error": "failed"}), encoding="utf-8",
    )
    RunSpec(
        topic="Saved topic", decision_context=DecisionContext(**CONTEXT),
        paper_contribution={"private": "PRIVATE PAPER CONTENT"},
    ).save(directory)
    client = TestClient(app)
    yield directory, client
    client.close()


def _responses(client, headers=OWNER_HEADERS):
    for suffix in ("", "/progress"):
        response = client.get(f"/api/runs/{RUN_ID}{suffix}", headers=headers)
        assert response.status_code == 200, response.text
        assert response.headers["Cache-Control"] == "private, no-store"
        yield response.json()


def _assert_saved_context(client, expected):
    for body in _responses(client):
        assert body["saved_decision_context"] == expected


@pytest.mark.parametrize("headers", [OWNER_HEADERS, {"X-Access-Code": "for-admin"}])
def test_owner_and_admin_receive_all_saved_fields_at_both_seams(failed_run, headers):
    """Response filtering must not drop fields or expose the rest of RunSpec."""
    _, client = failed_run
    for body in _responses(client, headers):
        assert body["state"] == "failed"
        assert body["viewer_can_modify"] is True
        assert body["saved_decision_context"] == {"status": "available", "context": CONTEXT}
        assert "PRIVATE PAPER CONTENT" not in json.dumps(body)
        assert CONTEXT["asset_description"] not in json.dumps(body["decision_gate"])


@pytest.mark.parametrize("headers", [{}, {"X-Access-Code": "for-other"}, {"X-Access-Code": "invalid"}])
def test_shared_readers_neither_receive_context_nor_open_the_spec(failed_run, headers):
    """Sharing a failed report must not disclose the saved request's prose."""
    _, client = failed_run
    with patch.object(RunSpec, "load", side_effect=AssertionError("must not read private spec")):
        for body in _responses(client, headers):
            assert body["viewer_can_modify"] is False
            assert body["saved_decision_context"] is None
            assert CONTEXT["asset_description"] not in json.dumps(body)


def test_ownerless_and_unreadable_owner_are_not_proof_of_ownership(failed_run):
    """A capability URL and unreadable ownership must not become input access."""
    directory, client = failed_run
    (directory / ".owner").unlink()
    with patch.object(RunSpec, "load", side_effect=AssertionError("must not read private spec")):
        for body in _responses(client):
            assert body["viewer_can_modify"] is None
            assert body["saved_decision_context"] is None
        with patch.object(runs, "owner_of", side_effect=runs.OwnerMarkerUnreadable("unreadable")):
            for body in _responses(client):
                assert body["viewer_can_modify"] is False
                assert body["saved_decision_context"] is None


def test_single_tenant_without_identity_gate_keeps_its_existing_read_verdict(failed_run, monkeypatch):
    """No configured identity system means local single-tenant access, as before."""
    _, client = failed_run
    monkeypatch.setattr(access, "ACCESS_CODES", None)
    monkeypatch.setattr(access, "ADMIN_CODE", None)
    for body in _responses(client, {}):
        assert body["viewer_can_modify"] is True
        assert body["saved_decision_context"] == {"status": "available", "context": CONTEXT}


@pytest.mark.parametrize("state", ["running", "completed", "cancelled", "timeout", "unknown"])
def test_only_failed_reads_open_the_spec(failed_run, state):
    """Frequent running polls must not read a spec, nor offer an unrelated rerun."""
    _, client = failed_run
    with patch.object(runs, "get_state", return_value={"run_id": RUN_ID, "state": state}), \
         patch.object(RunSpec, "load", side_effect=AssertionError("must not read spec")):
        _assert_saved_context(client, None)


def test_partial_saved_context_preserves_only_supplied_fields(failed_run):
    """Missing core fields are incomplete input, not a reason to lose saved text."""
    directory, client = failed_run
    context = DecisionContext(constraints="A saved constraint")
    RunSpec(topic="Saved topic", decision_context=context).save(directory)
    _assert_saved_context(client, {"status": "available", "context": context.model_dump()})


def test_explicit_saved_empty_is_distinct_from_unavailable(failed_run):
    """The real save format records null when the user supplied no context."""
    directory, client = failed_run
    path = RunSpec(topic="Saved topic").save(directory)
    assert json.loads(path.read_text(encoding="utf-8"))["decision_context"] is None
    _assert_saved_context(client, {"status": "empty", "context": None})


@pytest.mark.parametrize("schema_version", [1, 2, 3])
def test_legacy_missing_field_is_unknown_not_known_empty(failed_run, schema_version):
    """Model defaults must not turn absent historical data into an empty request."""
    directory, client = failed_run
    (directory / RUN_SPEC_FILENAME).write_text(
        json.dumps({"schema_version": schema_version, "topic": "Saved topic"}), encoding="utf-8",
    )
    _assert_saved_context(client, {"status": "unavailable", "context": None})


@pytest.mark.parametrize("payload", [
    None,
    b"{broken",
    b'{"topic":"Saved topic","decision_context":{"constraints":3}}',
    b'{"topic":"Saved topic","decision_context":{"success_criteria_authority":"owner_approved"}}',
    b'{"topic":"Saved topic","decision_context":{"private_extra":"do not disclose"}}',
])
def test_missing_or_invalid_saved_context_stays_unavailable(failed_run, payload):
    """A damaged request must not turn a readable failed run into a 500 or empty input."""
    directory, client = failed_run
    path = directory / RUN_SPEC_FILENAME
    if payload is None:
        path.unlink()
    else:
        path.write_bytes(payload)
    _assert_saved_context(client, {"status": "unavailable", "context": None})


def test_unreadable_spec_stays_unavailable_without_filesystem_details(failed_run):
    """Input read loss must remain explicit without exposing a local path."""
    _, client = failed_run
    with patch.object(RunSpec, "load", side_effect=PermissionError("PRIVATE FILE PATH")):
        _assert_saved_context(client, {"status": "unavailable", "context": None})


def test_saved_context_never_enters_public_state_or_history(failed_run):
    """Only per-caller details may carry prose, never the shared state projection."""
    _, client = failed_run
    assert "saved_decision_context" not in runs.get_state(RUN_ID)
    response = client.get("/api/runs", headers=OWNER_HEADERS)
    assert response.status_code == 200
    assert "saved_decision_context" not in response.text
    assert CONTEXT["asset_description"] not in response.text
