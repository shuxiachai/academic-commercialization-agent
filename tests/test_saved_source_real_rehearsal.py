"""Synthetic subprocess seams through the existing native wrapper and usage app."""

from copy import deepcopy
import json
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from academic_agent import saved_source_real_eval as prep
from academic_agent import saved_source_real_rehearsal as rehearsal
from tests.test_saved_source_real_eval import encode, synthetic_inputs


def child_with_patch(tmp_path, script):
    """Only tests inject defects; the shipped entry accepts only its packet."""
    packet = prep.build_packet(**synthetic_inputs())
    code = """import json, sys
from unittest.mock import patch
from academic_agent import saved_source_real_rehearsal as r
from academic_agent import saved_source_real_eval as p
packet = json.loads(sys.stdin.buffer.read())
""" + script + "\nprint(json.dumps(r._child(packet)))\n"
    result = subprocess.run([sys.executable, "-X", "utf8", "-c", code], input=prep.serialize_packet(packet),
                            capture_output=True, cwd=tmp_path, env=rehearsal._environment(), timeout=90)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    return json.loads(result.stdout)


def test_actual_post_get_wire_accounting_and_baseline(tmp_path):
    """The full native wire and accounting must reach both actual HTTP endpoints."""
    packet = prep.build_packet(**synthetic_inputs())
    before = deepcopy(packet)
    connect = socket.create_connection
    result = rehearsal.rehearse(packet)
    assert socket.create_connection is connect and packet == before
    assert result["state"] == "passed", result
    assert result["native_efficacy"] == result["reference_review"] == "not_run"
    assert result["live_authorization"] is False and result["external_provider_calls"] == 0
    assert result["intercepted_http_entries"] == 4 and result["guard_failures"] == []
    assert result["accounting_scope"] == "scripted_tokens_and_estimates_not_real_use"
    preview = prep.preview_wire(packet)
    for index, row in enumerate(result["cases"]):
        assert row["state"] == "passed"
        assert row["wire_sha256"] == prep._sha(preview[row["case_id"]])
        assert row["post"]["accounting"] == row["get"]["accounting"]
        assert row["post"]["receipt"]["result"] == row["get"]["receipt"]["result"]
        assert row["post"]["accounting"]["usage"] == {"status": "reported_complete", "prompt_tokens": 100 + index,
                                                        "completion_tokens": 20, "total_tokens": 120 + index}
        assert row["post"]["accounting"]["cost"]["estimated_usd"] == f"0.{(100 + index) * 573 + 20 * 3440:09d}"
        assert row["post"]["receipt"]["provider_usage"] == row["get"]["receipt"]["provider_cost"] == "not_observed"
        assert row["post"]["receipt"]["delivery_source_reads"] == 0
        assert row["get"]["receipt"]["delivery_source_reads"] == int(index < 3)
    baseline = result["baseline"]
    assert baseline["state"] == "available" and baseline["asset_hashes_before"] == baseline["asset_hashes_after"]
    assert [row["question"]["candidate_ids"] for row in baseline["cases"]] == [[], [], [], []]
    assert [row["keyword_query"]["candidate_ids"] for row in baseline["cases"]] == [["A3"], ["A1", "A2"], ["A3"], []]
    assert baseline["cases"][1]["keyword_query"]["ambiguous"] is True
    assert baseline["cases"][1]["keyword_query"]["draft_coverage"] == 1
    assert baseline["cases"][3]["keyword_query"]["draft_no_fit_match"] is True
    assert baseline["reference_provenance"] == "AI_authored_draft" and baseline["blind_review"] == "not_run"


@pytest.mark.parametrize("fault,reason", [
    ("wire", "wire_mismatch"), ("network", "network_denied"), ("missing_mock", "mock_transport_missing"),
    ("swallowed_assertion", "deliberate_guard_failure"),
])
def test_guard_failure_survives_adapter_catch_and_stops_all_later_cases(tmp_path, fault, reason):
    """A swallowed AssertionError or unavailable result is not a scripted pass."""
    scripts = {
        "wire": "original_wire = p._wire\np._wire = lambda *a: original_wire(*a) + b' '",
        "network": "r._Guard.dispatch = lambda self, request: __import__('socket').create_connection(('example.invalid',443))",
        "swallowed_assertion": "r._Guard.dispatch = lambda self, request: self.check(False, 'deliberate_guard_failure')",
        "missing_mock": """import httpx
original_transport = httpx.AsyncHTTPTransport
install = r._install_guards
def broken(stack, guard):
    install(stack, guard)
    httpx.AsyncHTTPTransport = original_transport
r._install_guards = broken
""",
    }
    result = child_with_patch(tmp_path, scripts[fault])
    assert result["state"] == "failed"
    assert [row["state"] for row in result["cases"]] == ["failed", "not_run", "not_run", "not_run"]
    assert reason in result["guard_failures"]
    assert result["intercepted_http_entries"] <= 1


@pytest.mark.parametrize("phase", ["get", "client_exit", "after_case"])
@pytest.mark.parametrize("ordinal", [1, 4])
def test_late_swallowed_guard_failure_fails_its_case_and_stops(tmp_path, phase, ordinal):
    """The last GET/client exit cannot hide a denied operation behind valid delivery."""
    script = """from fastapi.testclient import TestClient
install = r._install_guards
guard = None
def capture(stack, value):
    global guard
    guard = value
    install(stack, value)
r._install_guards = capture
target = TestClient if PHASE != 'after_case' else r
name = {'get': 'get', 'client_exit': '__exit__', 'after_case': '_case'}[PHASE]
original = getattr(target, name)
def changed(*args, **kwargs):
    value = original(*args, **kwargs)
    if len(guard.requests) == ORDINAL:
        try:
            guard.deny()
        except AssertionError:
            pass
    return value
setattr(target, name, changed)
""".replace("PHASE", repr(phase)).replace("ORDINAL", str(ordinal))
    result = child_with_patch(tmp_path, script)
    assert "network_denied" in result["guard_failures"]
    assert result["state"] == "failed"
    assert [row["state"] for row in result["cases"]] == ["passed"] * (ordinal - 1) + ["failed"] + ["not_run"] * (4 - ordinal)
    assert result["intercepted_http_entries"] == ordinal


def test_guard_failure_after_case_cleanup_prevents_aggregate_pass(tmp_path):
    """A late final identity/cleanup guard failure cannot produce a passed aggregate."""
    result = child_with_patch(tmp_path, """install = r._install_guards
guard = None
def capture(stack, value):
    global guard
    guard = value
    install(stack, value)
r._install_guards = capture
original_validate = p.validate_packet
def late_validate(packet):
    original_validate(packet)
    if guard is not None:
        try:
            guard.deny()
        except AssertionError:
            pass
p.validate_packet = late_validate
""")
    assert all(row["state"] == "passed" for row in result["cases"])
    assert result["guard_failures"] == ["network_denied"]
    assert result["state"] == "failed"


@pytest.mark.parametrize("fault", ["guard", "case", "count", "baseline"])
def test_parent_rejects_inconsistent_child_success(monkeypatch, fault):
    """A passed string cannot override the actual returned checks at the subprocess seam."""
    packet = prep.build_packet(**synthetic_inputs())
    original = subprocess.run
    def changed(command, **kwargs):
        result = original(command, **kwargs)
        if "--child" in command:
            value = json.loads(result.stdout)
            assert value["state"] == "passed"
            if fault == "guard":
                value["guard_failures"] = ["network_denied"]
            elif fault == "case":
                value["cases"][3]["state"] = "failed"
            elif fault == "count":
                value["intercepted_http_entries"] = 3
            else:
                value["baseline"]["state"] = "not_available"
            result.stdout = json.dumps(value).encode()
        return result
    monkeypatch.setattr(subprocess, "run", changed)
    with pytest.raises(prep.PreparationError):
        rehearsal.rehearse(packet)


@pytest.mark.parametrize("fault", ["get_redispatch", "dropped_cost", "changed_result"])
def test_delivery_defects_fail_at_the_real_http_seam(tmp_path, fault):
    """Hidden GET charge, dropped accounting and changed delivery cannot pass equality."""
    changes = {
        "get_redispatch": "runs._daily_counts[access.owner_id(r._CODE)] += 1",
        "dropped_cost": "value['accounting']['cost']['estimated_usd'] = None",
        "changed_result": "value['receipt']['result']['saved_text']['text'] += ' changed'",
    }
    script = """from fastapi.testclient import TestClient
from api import runs, access
original_get = TestClient.get
def changed(self, *args, **kwargs):
    result = original_get(self, *args, **kwargs)
    value = result.json()
    CHANGE
    result._content = json.dumps(value).encode()
    return result
TestClient.get = changed
""".replace("CHANGE", changes[fault])
    result = child_with_patch(tmp_path, script)
    assert [row["state"] for row in result["cases"]] == ["failed", "not_run", "not_run", "not_run"]
    assert result["intercepted_http_entries"] == 1


@pytest.mark.parametrize("fault", ["missing_node", "asset_drift", "missing_state"])
def test_baseline_unavailable_is_not_an_empty_set_or_automatic_pass(tmp_path, fault):
    """Missing Node or incomplete observation remains independent from HTTP success."""
    scripts = {
        "missing_node": "r.shutil.which = lambda _: None",
        "asset_drift": """assets = r._assets
calls = 0
def drift():
    global calls
    calls += 1
    result = assets()
    if calls > 1:
        result['web/static/js/result.js'] = 'changed'
    return result
r._assets = drift
""",
        "missing_state": "r._run_node = lambda *_: {'states': []}",
    }
    result = child_with_patch(tmp_path, scripts[fault])
    assert result["state"] == "failed" and result["baseline"]["state"] == "not_available"
    assert all(row["state"] == "passed" for row in result["cases"])
    assert all(row["question"] is row["keyword_query"] is None for row in result["baseline"]["cases"])


def test_rebound_reference_does_not_control_scripted_execution(tmp_path):
    """Draft overlap may change, but the same separately bound script still selects A3."""
    data = synthetic_inputs()
    labels = json.loads(data["references"])
    labels["cases"][0]["acceptable_source_ids"] = ["M1"]
    data["references"] = encode(labels)
    result = rehearsal.rehearse(prep.build_packet(**data))
    assert result["state"] == "passed"
    assert result["cases"][0]["post"]["receipt"]["result"]["source"]["source_id"] == "A3"
    assert result["baseline"]["cases"][0]["keyword_query"]["draft_coverage"] == 0


def test_no_execution_options_or_credential_inheritance(monkeypatch, tmp_path):
    """The only child recipe carries a bounded packet and a noncredential environment."""
    packet = prep.build_packet(**synthetic_inputs())
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-not-inherited")
    monkeypatch.setenv("QWEN_API_KEY", "synthetic-not-inherited")
    assert "OPENAI_API_KEY" not in rehearsal._environment() and "QWEN_API_KEY" not in rehearsal._environment()
    for name in ("api_key", "endpoint", "callback", "live"):
        with pytest.raises(TypeError):
            rehearsal.rehearse(packet, **{name: None})
    # Fail only the actual child launch; code identity still runs read-only git.
    original = subprocess.run
    def failed(command, **kwargs):
        if "--child" in command:
            assert kwargs["env"] == rehearsal._environment()
            assert Path(kwargs["cwd"]).is_relative_to(prep.PRIVATE_ROOT)
            raise OSError("PRIVATE path and contents")
        return original(command, **kwargs)
    monkeypatch.setattr(subprocess, "run", failed)
    with pytest.raises(prep.PreparationError) as error:
        rehearsal.rehearse(packet)
    assert "PRIVATE" not in str(error.value)
