"""In-memory observer lifetime regressions, outside the frozen invocation.

Actual constructor, path wrapper, safe catch and frame walker use private
function globals and synthetic reference code. No real guard installation,
audit hook, atexit callback, main, preparation, provider or child is run.
"""

import ast
import copy
from pathlib import Path
import sys
from types import FunctionType, MethodType, ModuleType, SimpleNamespace

import pytest

from evals.reviewer_comparison_v3 import test_invoker as invoker


FIELD = "ff_first_observer_fault"
PHASES = ("prepare", "prepare_scope_exit")


def private_function(function, namespace):
    """Retain actual code and share only the fixture's private module globals."""
    result = FunctionType(function.__code__, namespace, function.__name__,
                          function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def reinjected_late_filename_lookup():
    """Restore the exact old expression in one function, never the source file."""
    function = invoker._SysconfigObservation._path_observation
    tree = ast.parse(Path(invoker.__file__).read_bytes())
    matches = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
               and node.name == function.__name__
               and node.lineno == function.__code__.co_firstlineno]
    assert len(matches) == 1, "lifetime_mutation_function_site_drift"
    target = copy.deepcopy(matches[0])
    comparisons = [node for node in ast.walk(target) if isinstance(node, ast.Compare)
                   and isinstance(node.left, ast.Attribute) and node.left.attr == "co_filename"
                   and len(node.comparators) == 1
                   and isinstance(node.comparators[0], ast.Attribute)
                   and isinstance(node.comparators[0].value, ast.Name)
                   and node.comparators[0].value.id == "self"
                   and node.comparators[0].attr == "invoker_filename"]
    assert len(comparisons) == 1, "lifetime_mutation_expression_site_drift"
    comparison = comparisons[0]
    comparison.comparators[0] = ast.copy_location(
        ast.Name(id="__file__", ctx=ast.Load()), comparison.comparators[0])
    code = compile(ast.fix_missing_locations(ast.Module(body=[target], type_ignores=[])),
                   invoker.__file__, "exec", dont_inherit=True)
    namespace = dict(function.__globals__)
    exec(code, namespace)
    return namespace[function.__name__]


def exercise_lifetime(tmp_path, *, phase, missing_file, refused, marker, reinjected=False):
    """Construct once, then remove one private global before a real frame walk."""
    original_module_filename = invoker.__file__
    original_sysconfig = sys.modules.get("sysconfig")
    guard = invoker.Guard(tmp_path, [], [])
    admitted, original_errors, original_calls, hooks = object(), [], [], []

    def original(raw, operation="read", *, resource_open=False):
        original_calls.append((raw, operation, resource_open))
        if refused:
            try:
                guard.deny("read_outside_admitted_sources")
            except PermissionError as error:
                original_errors.append(error)
                raise
        return admitted

    def guarded_isfile(raw):
        return guard.path(raw, "probe")

    def is_python_build(raw, checker):
        return checker(raw)

    def synthetic_execute_child():
        raise AssertionError("synthetic_subprocess_reference_must_not_execute")

    def forbidden_reference_read(*args, **kwargs):
        raise AssertionError("supplied_reference_codes_require_no_source_read")

    marker_module = ModuleType("synthetic_sysconfig_lifetime")
    marker_module._PROJECT_BASE = str(tmp_path / "synthetic-project")
    build = FunctionType(is_python_build.__code__, marker_module.__dict__, "is_python_build")
    references = {"sysconfig": {("is_python_build", 1): build.__code__},
                  "subprocess": {("_execute_child", 1438): synthetic_execute_child.__code__}}
    shadow_sys = SimpleNamespace(**{name: str(tmp_path) for name in (
        "prefix", "base_prefix", "exec_prefix", "base_exec_prefix", "executable")},
        modules={"sysconfig": marker_module}, _getframe=sys._getframe, addaudithook=hooks.append)
    namespace = {**vars(invoker), "sys": shadow_sys,
                 "subprocess": SimpleNamespace(
                     Popen=SimpleNamespace(_execute_child=synthetic_execute_child),
                     __file__=str(tmp_path / "Lib/subprocess.py")),
                 "_nt312_isfile_identity": lambda wrapper: guarded_isfile.__code__,
                 "_sysconfig_reference_codes": forbidden_reference_read}
    guard.path = original
    observer = object.__new__(invoker._SysconfigObservation)
    private_function(invoker._SysconfigObservation.__init__, namespace)(
        observer, guard, tmp_path, "synthetic-script-not-executed",
        {"diagnostic_binding": "explicit_ff", "case_id": "synthetic-lifetime-unit-only",
         "mode": "missing-control"}, profile_sources=references, guarded_isfile=guarded_isfile)
    # The genuine constructor owns the captured identity; the fixture never
    # populates invoker_filename. Missing or incorrect initialization must fail.
    assert len(hooks) == 1 and hooks[0].__self__ is observer
    assert observer.data["refusal_windows"] == [
        {"stage": "guard_registration", "count": 0, "categories": {}}]
    observer.phase, observer.watch_markers = phase, True
    path_function = (reinjected_late_filename_lookup() if reinjected
                     else invoker._SysconfigObservation._path_observation)
    observer._path_observation = MethodType(private_function(path_function, namespace), observer)
    before_removal = dict(namespace)
    if missing_file:
        del namespace["__file__"]
    assert namespace == {name: value for name, value in before_removal.items()
                         if not missing_file or name != "__file__"}

    raw = invoker.os.path.join(marker_module._PROJECT_BASE, "Modules", marker)
    if refused:
        with pytest.raises(PermissionError) as caught:
            build(raw, guarded_isfile)
        assert len(original_errors) == 1 and caught.value is original_errors[0], \
            "original_permission_error_identity_preserved"
    else:
        assert build(raw, guarded_isfile) is admitted, "original_return_identity_preserved"
        assert original_errors == []
    assert original_calls == [(raw, "probe", False)], "original_guard_called_once"
    assert guard.violations == (["read_outside_admitted_sources"] if refused else []), \
        "original_guard_ledger_preserved"
    assert guard.finish_status(0) == int(refused)
    assert invoker.__file__ is original_module_filename, "live_module_filename_preserved"
    assert sys.modules.get("sysconfig") is original_sysconfig, "live_sysconfig_module_preserved"
    assert ("__file__" not in namespace) is missing_file
    return observer


def assert_lifetime_delivery(observer, *, phase, refused, marker):
    """Assert delivered counts, witnesses and fault state, not a cached field."""
    assert observer.data["observer_fault"] is False, "observer_completed_without_late_global_lookup"
    assert observer.data[FIELD] == {"status": "not_observed", "first": None}, \
        "successful_observation_keeps_first_fault_unclaimed"
    expected = {name: {"admitted": 0, "refused": 0} for name in ("Setup", "Setup.local")}
    expected[marker]["refused" if refused else "admitted"] = 1
    assert observer.data["marker_intents"] == expected, "actual_marker_intent_delivered"
    witnesses = observer.data["refusal_witnesses"]
    if refused:
        assert len(witnesses) == 1, "actual_refusal_witness_delivered"
        witness = witnesses[0]
        assert set(witness) == {"stage", "frames", "operation"}
        assert witness["stage"] == phase and witness["operation"] == "probe"
        assert witness["frames"][:4] == [
            "invoker_other", "observer_path", "guarded_isfile", "sysconfig_is_python_build"], \
            "constructor_filename_preserves_real_frame_labels"
        assert 4 <= len(witness["frames"]) <= 8
        assert all(label == "other" for label in witness["frames"][4:])
    else:
        assert witnesses == [], "admission_cannot_fabricate_a_refusal_witness"
    assert observer.data["saturated"] is False
    assert observer.phase == phase and observer.watch_markers is True


@pytest.mark.parametrize("phase", PHASES, ids=["prepare", "scope-exit"])
@pytest.mark.parametrize("missing_file", [False, True], ids=["global-present", "global-removed"])
@pytest.mark.parametrize("refused", [False, True], ids=["return", "refusal"])
@pytest.mark.parametrize("marker", ["Setup", "Setup.local"], ids=["setup", "setup-local"])
def test_actual_observer_survives_private_module_filename_removal(tmp_path, phase, missing_file, refused, marker):
    """Late globals loss must not erase real marker/witness delivery or claim a first fault."""
    observer = exercise_lifetime(tmp_path, phase=phase, missing_file=missing_file, refused=refused, marker=marker)
    assert_lifetime_delivery(observer, phase=phase, refused=refused, marker=marker)


@pytest.mark.parametrize("phase", PHASES, ids=["prepare", "scope-exit"])
@pytest.mark.parametrize("refused", [False, True], ids=["return", "refusal"])
def test_reinjected_old_lookup_fails_same_lifetime_delivery_assertion(tmp_path, phase, refused):
    """The old expression must cause the common oracle to reject an actual caught NameError."""
    positive = exercise_lifetime(tmp_path, phase=phase, missing_file=True, refused=refused, marker="Setup")
    assert_lifetime_delivery(positive, phase=phase, refused=refused, marker="Setup")
    damaged = exercise_lifetime(tmp_path, phase=phase, missing_file=True, refused=refused,
                                marker="Setup", reinjected=True)
    assert damaged.data["observer_fault"] is True
    assert damaged.data[FIELD] == {"status": "captured", "first": {
        "component": "sysconfig_path", "phase": phase, "exception": "name_error"}}
    assert damaged.data["marker_intents"] == {
        name: {"admitted": 0, "refused": 0} for name in ("Setup", "Setup.local")}
    assert damaged.data["refusal_witnesses"] == []
    with pytest.raises(AssertionError, match="observer_completed_without_late_global_lookup"):
        assert_lifetime_delivery(damaged, phase=phase, refused=refused, marker="Setup")
