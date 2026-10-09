"""Pure H4 regression: one actual entry and fail-closed sealed-H2 selection.

No invoker normal startup, pytest child, framework, or credential is executed.
The contract control reuses the complete, byte-bound original assertion body.
"""
import ast
import builtins
import copy
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from evals.reviewer_comparison_v3 import test_invoker as invoker


def test_complete_original_contract_detects_reinjected_second_pytest_call():
    """The historical second H2 call must turn the same passing full contract red."""
    selected = invoker.ROOT / "tests/reviewer_comparison_v3_checks.py"
    selected_raw = selected.read_bytes()
    assert hashlib.sha256(selected_raw).hexdigest() == "426c0bc5aaa44758effe59d2c2ff776b60c908cfdaf7324719a93a8be7812677"
    original = next(node for node in ast.parse(selected_raw).body if isinstance(node, ast.FunctionDef)
                    and node.name == "_assert_fixed_invoker_contract")
    namespace = {"ast": ast, "Path": Path, "r": SimpleNamespace(ROOT=invoker.ROOT)}
    # Execute only the exact original checker definition in a scratch namespace;
    # no original module startup, runner, credential, or mutant code is executed.
    checker = ast.Module(body=[copy.deepcopy(original)], type_ignores=[])
    exec(compile(checker, str(selected), "exec", dont_inherit=True, optimize=0), namespace)
    check = namespace["_assert_fixed_invoker_contract"]
    raw = (invoker.ROOT / invoker.ENTRY).read_bytes()
    check(raw=raw)
    tree = ast.parse(raw)
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    extra = ast.parse("if False:\n    pytest.main(_pytest_arguments(paths), plugins=[receipt, _h2_pytest_plugin(locator, pytest)])").body[0]
    main.body.insert(-1, copy.deepcopy(extra))
    ast.fix_missing_locations(tree)
    mutant = ast.unparse(tree)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and isinstance(node.func.value, ast.Name) and node.func.value.id == "pytest" and node.func.attr == "main"]
    assert len(calls) == 2
    count_assertion = next(node for node in ast.walk(original) if isinstance(node, ast.Assert) and ast.unparse(node.test) == "len(calls) == 1")
    with pytest.raises(AssertionError) as failure:
        check(raw=mutant)
    trace = failure.value.__traceback__
    hits = []
    while trace is not None:
        if trace.tb_frame.f_code is check.__code__:
            hits.append(trace.tb_lineno)
        trace = trace.tb_next
    assert hits == [count_assertion.lineno] and failure.value.args == ()


def test_valid_sealed_h2_exits_before_environment_home_profile_prepare_or_pytest(monkeypatch):
    """A valid consumed H2 selector must close before any normal startup side effect."""
    environment = dict(zip(invoker._H2_INPUTS, (invoker._H2_CASE, "a" * 64), strict=True))
    runtime = SimpleNamespace(argv=["invoker"], version_info=(3, 11, 9), implementation=SimpleNamespace(name="cpython"),
                              flags=SimpleNamespace(no_site=1, dont_write_bytecode=1, ignore_environment=1))
    monkeypatch.setattr(invoker, "sys", runtime)
    monkeypatch.setattr(invoker, "os", SimpleNamespace(name="nt", environ=environment))
    # The actual parser accepts this complete binding; closure is a distinct gate.
    assert invoker._h2_configuration(environment)["diagnostic_binding"] == "explicit_h2"
    reached = []

    def forbidden(label):
        def reject(*args, **kwargs):
            reached.append(label)
            raise AssertionError("sealed_h2_crossed_startup_boundary")
        return reject

    for name in ("_verified_environment", "_owned_profile", "_test_environment", "_preload_canonical", "_normal_dependency_startup"):
        monkeypatch.setattr(invoker, name, forbidden(name))
    monkeypatch.setattr(Path, "home", forbidden("Path.home"))
    monkeypatch.setattr(pytest, "main", forbidden("pytest.main"))
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "evals.reviewer_comparison_v3" and "runner" in fromlist:
            forbidden("runner_import_before_prepare")()
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    with pytest.raises(SystemExit) as failure:
        invoker.main()
    assert type(failure.value) is SystemExit and failure.value.args == ("h2_diagnostic_case_closed",)
    assert reached == []
