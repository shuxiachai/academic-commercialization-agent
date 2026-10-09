"""Separate offline scope regressions; never part of the original 529 checks.

These tests use caller-owned mappings and paths. They never invoke the real runner,
install a global guard, mutate the live sysconfig cache, or launch a child.
"""

import builtins
from contextlib import nullcontext
from pathlib import Path
import sys
from types import ModuleType

import pytest

from evals.reviewer_comparison_v3 import test_invoker as invoker


def diagnostic(mode="isolated"):
    return dict(zip(invoker._SYSCONFIG_INPUTS, (mode, invoker._SYSCONFIG_CASES[mode], "a" * 64), strict=True))


def test_default_invocation_requires_no_h1_diagnostic_values():
    """The fixed existing CLI must not become dependent on one H1 control UUID."""
    config = invoker._sysconfig_configuration({}, platform=("nt", "cpython", (3, 11)))
    assert config == {
        "mode": "isolated", "diagnostic_binding": "not_requested", "case_id": None,
        "control_sha256": None, "policy_sha256": config["policy_sha256"],
        "policy_applicable": True, "platform_validation": "not_evaluated",
    }
    assert len(config["policy_sha256"]) == 64


@pytest.mark.parametrize("mode", ["isolated", "missing-control"])
def test_explicit_h1_configuration_binds_all_three_fields(mode):
    """The negative mode is unavailable without its matching case and control."""
    config = invoker._sysconfig_configuration(diagnostic(mode), platform=("nt", "cpython", (3, 11)))
    assert config["mode"] == mode
    assert config["case_id"] == invoker._SYSCONFIG_CASES[mode]
    assert config["control_sha256"] == "a" * 64
    assert config["diagnostic_binding"] == "explicit_h1"


@pytest.mark.parametrize("missing", invoker._SYSCONFIG_INPUTS)
def test_partial_h1_configuration_cannot_fall_back_to_default(missing):
    """Dropping one diagnostic field must fail instead of changing the case."""
    values = diagnostic("missing-control")
    del values[missing]
    with pytest.raises(RuntimeError, match="binding_incomplete_or_unsupported"):
        invoker._sysconfig_configuration(values, platform=("nt", "cpython", (3, 11)))


@pytest.mark.parametrize("field,value", [
    ("REVIEWER_V3_SYSCONFIG_MODE", "other"),
    ("REVIEWER_V3_SYSCONFIG_CASE", "d2641d46-78e5-49a4-afc4-d86ebf91ed69"),
    ("REVIEWER_V3_SYSCONFIG_CONTROL_SHA256", "A" * 64),
    ("REVIEWER_V3_SYSCONFIG_CONTROL_SHA256", "a" * 63),
])
def test_h1_selector_and_identity_values_are_strict(field, value):
    """Malformed explicit identity cannot be silently normalized or ignored."""
    values = diagnostic()
    values[field] = value
    with pytest.raises(RuntimeError, match="binding_invalid"):
        invoker._sysconfig_configuration(values, platform=("nt", "cpython", (3, 11)))


@pytest.mark.parametrize("platform,expected_applicable", [
    (("nt", "cpython", (3, 12)), True), (("posix", "cpython", (3, 11)), False),
], ids=["nt312-default", "posix311-default"])
def test_other_platforms_retain_default_but_refuse_requested_h1(platform, expected_applicable):
    """NT312 default eligibility must not admit a legacy H1 diagnostic selector."""
    config = invoker._sysconfig_configuration({}, platform=platform)
    assert config["policy_applicable"] is expected_applicable
    assert config["platform_validation"] == "not_evaluated"
    with pytest.raises(RuntimeError, match="binding_incomplete_or_unsupported"):
        invoker._sysconfig_configuration(diagnostic(), platform=platform)


@pytest.mark.parametrize("exit_kind", ["normal", "exception", "base_exception"])
def test_prepare_scope_sets_owned_base_and_restores_missing_state(tmp_path, exit_kind):
    """A failed prepare used to risk leaking the override into cold children."""
    environment = {"UNCHANGED": "value"}
    original = dict(environment)
    error = {"normal": None, "exception": RuntimeError, "base_exception": KeyboardInterrupt}[exit_kind]
    caught = None
    try:
        with invoker._sysconfig_prepare_scope(tmp_path, "isolated", environ=environment, modules={}):
            assert environment["_PYTHON_PROJECT_BASE"] == str(tmp_path)
            if error is not None:
                raise error()
    except (RuntimeError, KeyboardInterrupt) as failure:
        caught = type(failure)
    assert caught is error
    assert environment == original
    assert invoker._sysconfig_environment_absent(environment)


def test_missing_control_exposes_actual_absence_without_creating_override(tmp_path):
    """The negative control must exercise the absent setting, not fake a denial."""
    environment = {"UNCHANGED": "value"}
    with invoker._sysconfig_prepare_scope(tmp_path, "missing-control", environ=environment, modules={}):
        assert environment == {"UNCHANGED": "value"}
    assert environment == {"UNCHANGED": "value"}


@pytest.mark.parametrize("environment,modules", [
    ({}, {"sysconfig": object()}),
    ({"_python_project_base": "prior"}, {}),
    ({"_PYTHON_PROJECT_BASE": "prior"}, {}),
])
def test_scope_rejects_cached_sysconfig_and_any_preexisting_base(tmp_path, environment, modules):
    """Prewarming or inheriting a base cannot masquerade as the cold H1 case."""
    before = dict(environment)
    with pytest.raises(RuntimeError, match="requires_cold_absent_environment"):
        with invoker._sysconfig_prepare_scope(tmp_path, "isolated", environ=environment, modules=modules):
            pytest.fail("the cold precondition must reject before entering prepare")
    assert environment == before


def test_project_directory_is_fresh_empty_and_cannot_be_reused(tmp_path):
    """A preoccupied owned directory must not carry a build marker into prepare."""
    project = invoker._sysconfig_project(tmp_path)
    assert project == tmp_path / "sysconfig-project"
    assert list(project.iterdir()) == []
    with pytest.raises(FileExistsError):
        invoker._sysconfig_project(tmp_path)


def test_nt_expectations_compare_all_eight_paths_to_independent_prefixes():
    """Copying sysconfig's returned paths would make a changed scheme self-validating."""
    assert invoker._sysconfig_nt_expectations({"prefix": "C:/venv", "base_prefix": "D:/python"}) == {
        "stdlib": "D:\\python\\Lib", "platstdlib": "C:\\venv\\Lib",
        "purelib": "C:\\venv\\Lib\\site-packages", "platlib": "C:\\venv\\Lib\\site-packages",
        "include": "D:\\python\\Include", "platinclude": "D:\\python\\Include",
        "scripts": "C:\\venv\\Scripts", "data": "C:\\venv",
    }


def test_nonapplicable_scope_does_not_touch_original_environment(monkeypatch):
    """Other platforms must retain their old prepare path without a cold gate."""
    def forbidden(*args, **kwargs):
        pytest.fail("nonapplicable platform entered the CP311 configuration scope")

    monkeypatch.setattr(invoker, "_sysconfig_prepare_scope", forbidden)
    with invoker._normal_sysconfig_scope(None, {"policy_applicable": False}):
        pass


def test_separate_regressions_do_not_change_original_check_files():
    """Adding scope regressions must not inflate the frozen 529-test denominator."""
    assert invoker.CHECK_FILES == ("tests/reviewer_comparison_v3_checks.py", "tests/reviewer_output_contract_checks.py")
    assert Path(__file__).name not in {Path(path).name for path in invoker.CHECK_FILES}


def bare_observation(guard, mode="isolated"):
    observation = object.__new__(invoker._SysconfigObservation)
    observation.guard = guard
    observation.data = {"observer_fault": False, "configuration": {"mode": mode},
                        "refusal_windows": []}
    return observation


def broken_diagnostic(*args, **kwargs):
    raise RuntimeError("injected_observation_failure")


def test_path_observation_fault_preserves_original_return_and_is_nonpass(tmp_path, monkeypatch):
    """A diagnostic exception must not replace a successful Guard return."""
    guard = invoker.Guard(tmp_path, [], [])
    observation = bare_observation(guard)
    monkeypatch.setattr(observation, "_path_observation", broken_diagnostic)
    expected = object()
    observed = observation._wrap_path(lambda *args, **kwargs: expected)
    assert observed(tmp_path, "probe") is expected
    assert guard.violations == []
    assert observation.data["observer_fault"] is True
    with pytest.raises(RuntimeError, match="observer_fault_before_pytest"):
        observation.require_prepare_ledger("before")


def test_path_observation_fault_preserves_original_permission_error(tmp_path, monkeypatch):
    """Failed diagnostics must preserve the exact original denial and ledger."""
    guard = invoker.Guard(tmp_path, [], [])
    observation = bare_observation(guard)
    monkeypatch.setattr(observation, "_path_observation", broken_diagnostic)
    original_errors = []

    def original(*args, **kwargs):
        try:
            guard.deny("read_outside_admitted_sources")
        except PermissionError as error:
            original_errors.append(error)
            raise

    with pytest.raises(PermissionError) as caught:
        observation._wrap_path(original)(tmp_path, "probe")
    assert caught.value is original_errors[0]
    assert guard.violations == ["read_outside_admitted_sources"]
    assert observation.data["observer_fault"] is True


@pytest.mark.parametrize("refusal_stage", ["before", "after"])
def test_actual_main_stops_before_pytest_on_swallowed_prepare_refusal(tmp_path, monkeypatch, refusal_stage):
    """The real main seam must stop a swallowed denial before pytest import."""
    observations, preparation_calls, pytest_imports = [], [], []
    observation_type = invoker._SysconfigObservation
    config = invoker._sysconfig_configuration(diagnostic(), platform=("nt", "cpython", (3, 11)))

    def observation_factory(guard, owned, script, configuration):
        observation = object.__new__(observation_type)
        observation.guard = guard
        observation.data = {"observer_fault": False, "configuration": configuration,
                            "refusal_windows": [], "executed_entry": None}
        observations.append(observation)
        return observation

    def swallow_original_denial():
        try:
            observations[0].guard.deny("read_outside_admitted_sources")
        except PermissionError:
            pass

    def dependencies(*args):
        if refusal_stage == "before":
            swallow_original_denial()
        return {}, None

    def preparation():
        preparation_calls.append(True)
        if refusal_stage == "after":
            swallow_original_denial()
        return {}

    # Only the outer main sequencing is real here. All setup with process-wide
    # effects and the project runner are replaced before entry; no guard, atexit
    # callback, provider, native loader or genuine preparation is installed/run.
    runner = ModuleType("evals.reviewer_comparison_v3.runner")
    runner.prepare = preparation
    monkeypatch.setitem(sys.modules, runner.__name__, runner)
    monkeypatch.setattr(sys.modules["evals.reviewer_comparison_v3"], "runner", runner, raising=False)
    monkeypatch.setattr(invoker, "_fixed_invocation", lambda *args: True)
    monkeypatch.setattr(invoker, "_sysconfig_configuration", lambda *args: config)
    monkeypatch.setattr(invoker, "_verified_environment", lambda: (tmp_path, tmp_path, "0" * 64))
    monkeypatch.setattr(invoker, "_owned_profile", lambda: (tmp_path, {"work": tmp_path, "tmp": tmp_path}))
    monkeypatch.setattr(invoker, "_test_environment", lambda *args: None)
    monkeypatch.setattr(invoker, "_preload_canonical", lambda: {})
    monkeypatch.setattr(invoker, "_cold_script_and_names", lambda: ("", set()))
    monkeypatch.setattr(invoker, "_install_io_guard", lambda *args: None)
    monkeypatch.setattr(invoker, "_install_cold_envelope", lambda *args: None)
    monkeypatch.setattr(invoker.atexit, "register", lambda *args: None)
    monkeypatch.setattr(invoker, "_SysconfigObservation", observation_factory)
    monkeypatch.setattr(invoker, "_normal_dependency_startup", dependencies)
    monkeypatch.setattr(invoker, "_normal_model_shims", lambda *args: {})
    monkeypatch.setattr(invoker, "_sysconfig_project", lambda owned: owned / "sysconfig-project")
    monkeypatch.setattr(invoker, "_normal_sysconfig_scope", lambda *args: nullcontext())
    monkeypatch.setattr(invoker, "_sysconfig_environment_absent", lambda *args: True)
    original_import = builtins.__import__

    def observe_import(name, *args, **kwargs):
        if name == "pytest":
            pytest_imports.append(True)
            raise AssertionError("pytest imported after a cumulative denial")
        return original_import(name, *args, **kwargs)

    original_path = sys.path[:]
    with pytest.raises(RuntimeError, match="prepare_cumulative_refusal_mismatch"):
        monkeypatch.setattr(builtins, "__import__", observe_import)
        try:
            invoker.main()
        finally:
            monkeypatch.setattr(builtins, "__import__", original_import)
            sys.path[:] = original_path
    assert preparation_calls == ([] if refusal_stage == "before" else [True])
    assert pytest_imports == []
    assert observations[0].guard.violations == ["read_outside_admitted_sources"]


def test_missing_control_requires_zero_baseline_and_exact_two_real_ledger_entries(tmp_path):
    """The negative case cannot absorb an earlier or extra refusal into its two."""
    guard = invoker.Guard(tmp_path, [], [])
    observation = bare_observation(guard, "missing-control")
    observation.require_prepare_ledger("before")
    for _ in range(2):
        with pytest.raises(PermissionError):
            guard.deny("read_outside_admitted_sources")
    with pytest.raises(RuntimeError, match="prepare_cumulative_refusal_mismatch"):
        observation.require_prepare_ledger("before")
    observation.require_prepare_ledger("after")
    with pytest.raises(PermissionError):
        guard.deny("read_outside_admitted_sources")
    with pytest.raises(RuntimeError, match="prepare_cumulative_refusal_mismatch"):
        observation.require_prepare_ledger("after")
    assert guard.violations == ["read_outside_admitted_sources"] * 3
