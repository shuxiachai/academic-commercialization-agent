"""RQ identity/CLI isolation; fixture git replies are not committed-tree proof."""

import ast
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from academic_agent import saved_source_receipt_qwen_canary as runner
from academic_agent.report_evidence_qwen_canary import CanaryStopped


def test_frozen_six_sources_exact_question_and_native_sizes():
    """Fixture identity locks labels and local Unicode while native sees only titles/question."""
    cases = runner.load_cases()
    assert len(cases) == 2 and sum(len(case["sources"]) for case in cases) == 6
    assert runner.digest((runner.ROOT / runner.FIXTURE).read_bytes()) == runner.FIXTURE_SHA256
    for case, sizes in zip(cases, ((1738, 1861), (1665, 1788)), strict=True):
        snapshot = runner.snapshot_for(case)
        callback = runner.locator._request(case["question"], runner.build_catalog(snapshot))
        wire = {**callback, "model": "qwen3.5-plus", "stream": False, "enable_thinking": False,
                "parallel_tool_calls": False, "temperature": 0, "max_tokens": 512}
        assert (len(runner._encoded(callback)), len(runner._encoded(wire))) == sizes
        native = runner._encoded(wire).decode("ascii")
        for row in case["sources"]:
            assert json.dumps(row["summary"], ensure_ascii=True)[1:-1] not in native
        assert runner.CODE not in native and case["run_id"] not in native
        assert "reference" not in wire


def test_source_identity_closure_is_static_and_contains_shared_seams():
    """Deriving the path set cannot import access globals, dotenv or a browser."""
    paths = set(runner.identity_paths())
    assert {"api/access.py", "api/runs.py", "api/saved_source_controller.py", "api/saved_source_receipts.py",
            "src/academic_agent/saved_source_loader.py", "src/academic_agent/report_evidence_qwen_transport.py",
            "web/saved-source-receipts/result.js", ".github/workflows/test.yml"} <= paths
    assert not any("outputs/" in path or ".env" in path for path in paths)
    assert "api/main.py" not in paths


@pytest.fixture
def identity(monkeypatch):
    paths = runner.identity_paths()
    blobs = {name: (runner.ROOT / name).read_bytes().replace(b"\r\n", b"\n") for name in paths}
    state = SimpleNamespace(head="a" * 40, dirty=b"", blobs=blobs)

    def git(*args):
        if args[0] == "rev-parse":
            return state.head.encode()
        if args[0] == "status":
            return state.dirty
        assert args[0] == "show"
        return blobs[args[1].split(":", 1)[1]]

    monkeypatch.setattr(runner, "_git", git)
    return state


def test_identity_only_never_reads_key_or_creates_output(identity, monkeypatch):
    """The default path must end before live output eligibility or key discovery."""
    monkeypatch.setattr(runner, "read_dedicated_key", lambda: pytest.fail("key read"))
    monkeypatch.setattr(runner, "validate_output", lambda: pytest.fail("output touched"))
    result = runner.run_canary(expected_commit=identity.head, expected_fixture_sha256=runner.FIXTURE_SHA256)
    assert result["mode"] == "identity_only" and result["native_requests"] == 0
    assert result["identity"]["disk_sha256"] and result["identity"]["committed_sha256"]


@pytest.mark.parametrize("fault", ["head", "dirty", "blob", "fixture", "dependency"])
def test_identity_mismatch_before_secret(identity, monkeypatch, fault):
    """Dirty code, wrong commits/fixture/dependencies cannot reach live credential lookup."""
    monkeypatch.setattr(runner, "read_dedicated_key", lambda: pytest.fail("key read"))
    expected = identity.head
    fixture = runner.FIXTURE_SHA256
    if fault == "head":
        identity.head = "b" * 40
    elif fault == "dirty":
        identity.dirty = b" M api/runs.py\n"
    elif fault == "blob":
        identity.blobs["api/runs.py"] += b"# drift\n"
    elif fault == "fixture":
        fixture = "0" * 64
    else:
        monkeypatch.setattr(runner, "version", lambda _name: "0.0.0")
    with pytest.raises(CanaryStopped):
        runner.run_canary(expected_commit=expected, expected_fixture_sha256=fixture,
                          authorize_paid=runner.PROTOCOL_IDENTITY)


def test_occupied_output_is_not_reused_before_key(identity, tmp_path, monkeypatch):
    """An empty occupied directory is already consumed; no reset or key read follows."""
    monkeypatch.setattr(runner, "verify_identity", lambda *a, **k: {})
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    output = tmp_path / runner.FIXED_OUTPUT
    output.mkdir(parents=True)
    monkeypatch.setattr(runner, "read_dedicated_key", lambda: pytest.fail("key read"))
    with pytest.raises(CanaryStopped, match="occupied"):
        runner.run_canary(expected_commit=identity.head, expected_fixture_sha256=runner.FIXTURE_SHA256,
                          authorize_paid=runner.PROTOCOL_IDENTITY)
    assert not list(output.iterdir())


def test_indirect_output_rejected_without_filesystem_symlink_privilege(tmp_path, monkeypatch):
    """Reparse attributes must fail on Windows even when ordinary symlinks cannot be made."""
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    actual = Path.lstat

    def lstat(path):
        if path == tmp_path:
            value = actual(path)
            return SimpleNamespace(st_mode=value.st_mode, st_file_attributes=0x400)
        return actual(path)

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(CanaryStopped, match="indirect"):
        runner.validate_output()


def test_dedicated_key_single_name_and_safe_cli_error(monkeypatch, capsys):
    """No alternate key/env fallback and no exception/refusal/body disclosure is allowed."""
    lookups = []

    def get(name):
        lookups.append(name)
        return "sk-offline-only"

    monkeypatch.setattr(runner, "os", SimpleNamespace(environ=SimpleNamespace(get=get)))
    assert runner.read_dedicated_key() == "sk-offline-only"
    assert lookups == ["DASHSCOPE_API_KEY"]
    monkeypatch.setattr(runner, "run_canary", lambda **_kwargs: (_ for _ in ()).throw(
        CanaryStopped("RAW_SECRET_PROVIDER_BODY")))
    assert runner.main(["--expected-commit", "a" * 40, "--expected-fixture-sha256", runner.FIXTURE_SHA256]) == 1
    assert "RAW_SECRET" not in capsys.readouterr().out


def test_import_and_identity_path_discovery_no_app_browser_or_environment_reads():
    """A fresh interpreter proves laziness; test-suite cached app modules cannot mask it."""
    script = '''
import builtins, os, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == "api" or name.startswith(("api.", "playwright", "dotenv")):
        raise AssertionError("forbidden import")
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from academic_agent import saved_source_receipt_qwen_canary as runner
class Denied(dict):
    def get(self, *args): raise AssertionError("environment read")
    def __getitem__(self, key): raise AssertionError("environment read")
os.environ = Denied()
assert runner.identity_paths()
assert not any(name.startswith(("api.", "playwright", "dotenv")) for name in sys.modules)
print("lazy identity pass")
'''
    result = subprocess.run([sys.executable, "-c", script], cwd=runner.ROOT,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "lazy identity pass"


def test_offline_cli_has_no_paid_flag_and_uses_shared_journey():
    """The fifth CI command must execute a rehearsal, never silently import or enable native."""
    from e2e import saved_source_receipt_qwen_canary as browser

    with pytest.raises(SystemExit) as error:
        browser.main(["--authorize-paid", runner.PROTOCOL_IDENTITY])
    assert error.value.code == 2
    tree = ast.parse((runner.ROOT / "e2e/saved_source_receipt_qwen_canary.py").read_text(encoding="utf-8"))
    rehearsal = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "rehearsal")
    assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "browser_batch"
               for node in ast.walk(rehearsal))


def test_offline_network_guard_denies_provider_before_dns():
    """A missing native HTTP interceptor cannot escape through DNS in rehearsal."""
    import socket
    from e2e.saved_source_receipt_qwen_canary import network_guard

    with network_guard(live=False) as faults:
        with pytest.raises(CanaryStopped, match="network_boundary_failed"):
            socket.getaddrinfo("dashscope.aliyuncs.com", 443)
    assert faults == ["network_boundary_failed"]


def test_fixture_loader_does_not_admit_changed_hash(tmp_path, monkeypatch):
    """Re-encoding or relabeling a frozen case is not a fresh authorization."""
    source = deepcopy(runner.load_cases()[0])
    source["reference"]["source_id"] = "A11"
    path = tmp_path / runner.FIXTURE
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(source), encoding="utf-8")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    with pytest.raises(CanaryStopped, match="fixture_identity_mismatch"):
        runner.load_cases()
