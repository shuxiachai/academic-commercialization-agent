"""Source-locked extraction, NOT an import of the full production module.

Only five frozen top-level nodes are omitted. All other AST nodes, including
model validators and serializers, retain their order and source locations.
The private execution dictionaries have explicit derived names; they are not
registered as modules and supply no TaskOutput or other annotation stand-in.
This is a bounded measurement loader, not a sandbox for arbitrary Python.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
from types import CodeType, FunctionType, MappingProxyType, ModuleType

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCE_LOCKS = {
    "evidence": "8e9eda3126dc1b81ec5a97e23ecfce8ba64c59a0d77c9a3fb3aec259f07b38c5",
    "run_spec": "8f6cd3f3b936d4045efaf42cc1314191bdfb4c693047be1d5460f8461f460c38",
}
OMISSIONS = (
    ("ImportFrom", "crewai", 14, 14),
    ("FunctionDef", "make_scoring_guardrail", 600, 800),
    ("FunctionDef", "make_evidence_guardrail", 992, 1040),
    ("FunctionDef", "make_final_report_guardrail", 1929, 1962),
    ("FunctionDef", "make_reviewer_guardrail", 2063, 2234),
)
OMITTED_NAMES = frozenset({"TaskOutput", *(item[1] for item in OMISSIONS[1:])})
IMPORTS = {
    "evidence": {"ipaddress", "re", "socket", "datetime", "functools", "typing",
                 "collections.abc", "urllib.error", "urllib.parse", "urllib.request", "pydantic"},
    "run_spec": {"__future__", "json", "os", "pathlib", "typing", "uuid", "pydantic"},
}
EXPORTS = {
    "evidence": ("EvidenceSource", "EvidenceFinding", "EvidenceReport", "ReviewerCorrection",
                 "ReviewerCorrectionPlan", "_apply_reviewer_corrections", "validate_final_report",
                 "parse_citation_ids"),
    "run_spec": ("DecisionContext",),
}
PACKAGES = {"pydantic": "2.12.5", "pydantic-core": "2.41.5"}
_CACHE = {}


class SourceFault(Exception):
    """Fixed local categories only; no configuration or exception detail."""


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _ast_value(node):
    """AST-v1 encoding, qualified by CPython minor, with all source locations.

    3.12 adds empty type_params to these pre-PEP-695 definitions. Only that
    known empty field is excluded; nonempty parameters are not admitted.
    This does NOT make located ASTs portable: 3.11/3.12 f-string locations
    differ. Each interpreter has its own measured manifest descriptor; never
    discard positions or select whichever alternate hash happens to match.
    Runtime bytecode identity is recorded separately with its interpreter.
    """
    if isinstance(node, ast.AST):
        result = {"kind": type(node).__name__}
        for field, value in ast.iter_fields(node):
            if field == "type_params":
                if value:
                    raise SourceFault("unsupported_ast_shape")
                continue
            result[field] = _ast_value(value)
        for field in node._attributes:
            if hasattr(node, field):
                result[field] = getattr(node, field)
        return result
    if isinstance(node, list):
        return [_ast_value(value) for value in node]
    if node is Ellipsis:
        return {"literal": "ellipsis"}
    return node


def _ast_sha(node):
    return _sha(_json(_ast_value(node)))


def _derive(name, raw):
    if name not in SOURCE_LOCKS:
        raise SourceFault("unexpected_helper")
    normalized = raw.replace(b"\r\n", b"\n")
    if _sha(normalized) != SOURCE_LOCKS[name]:
        raise SourceFault("helper_source_drift")
    tree = ast.parse(normalized, filename=f"<v2-source:{name}>")
    before = [_ast_sha(node) for node in tree.body]
    removed, retained = [], []
    for node in tree.body:
        key = (type(node).__name__, getattr(node, "name", getattr(node, "module", None)),
               node.lineno, node.end_lineno)
        if name == "evidence" and key in OMISSIONS:
            if isinstance(node, ast.ImportFrom):
                if node.level != 0 or [(a.name, a.asname) for a in node.names] != [("TaskOutput", None)]:
                    raise SourceFault("omission_shape_drift")
            elif node.decorator_list:
                raise SourceFault("omission_shape_drift")
            removed.append({"node": list(key), "ast_sha256": _ast_sha(node)})
        else:
            retained.append(node)
    expected = [list(item) for item in OMISSIONS] if name == "evidence" else []
    if [item["node"] for item in removed] != expected:
        raise SourceFault("omission_set_drift")
    if name == "evidence" and (len(tree.body), len(retained)) != (97, 92):
        raise SourceFault("retained_node_drift")
    derived = ast.Module(body=retained, type_ignores=tree.type_ignores)
    # Do not reparse unparse() output, fix locations or rewrite annotations.
    if [_ast_sha(n) for n in retained] != [value for n, value in zip(tree.body, before, strict=True)
                                          if n in retained]:
        raise SourceFault("retained_node_drift")
    for node in ast.walk(derived):
        if isinstance(node, ast.Name) and node.id in OMITTED_NAMES:
            raise SourceFault("omitted_name_reference")
        if isinstance(node, ast.Import):
            if any(item.name not in IMPORTS[name] for item in node.names):
                raise SourceFault("unexpected_helper_import")
        if isinstance(node, ast.ImportFrom):
            if node.level or node.module not in IMPORTS[name] or any(a.name == "*" for a in node.names):
                raise SourceFault("unexpected_helper_import")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"eval", "exec", "__import__"}:
                raise SourceFault("unexpected_dynamic_execution")
    descriptor = {"source_path": f"src/academic_agent/{name}.py",
                  "normalized_source_sha256": SOURCE_LOCKS[name], "omissions": removed,
                  "original_top_nodes": len(tree.body), "retained_top_nodes": len(retained),
                  "derived_ast_sha256": _ast_sha(derived), "exports": list(EXPORTS[name])}
    return derived, descriptor


def _interpreter_key():
    """Select only the current supported parser, never a compatibility fallback."""
    if sys.implementation.name != "cpython" or sys.version_info[:2] not in {(3, 11), (3, 12)}:
        raise SourceFault("unsupported_interpreter")
    return f"cpython-{sys.version_info[0]}.{sys.version_info[1]}"


def describe():
    """Describe this actual parser only; freeze each supported interpreter separately."""
    interpreter = _interpreter_key()
    return {"method": "source_locked_extracted_namespace_v2", "ast_encoding": "located_ast_v1_version_qualified",
            "interpreter": interpreter,
            "compile": {"dont_inherit": True, "optimize": 0},
            "bytecode_encoding": "recursive_code_fields_v1",
            "bytecode_scope": "same_interpreter_runtime_identity_not_portable_manifest_hash",
            "loader_sha256": _sha(Path(__file__).read_bytes()), "packages": PACKAGES,
            "sources": {name: _derive(name, (ROOT / f"src/academic_agent/{name}.py").read_bytes())[1]
                        for name in SOURCE_LOCKS}}


def _code_index(code):
    result = {}
    for item in code.co_consts:
        if isinstance(item, CodeType):
            result[item.co_qualname] = item
            result.update(_code_index(item))
    return result


def _code_value(value):
    """Reference-count-independent code identity, NOT marshal's object graph.

    marshal may set reference flags differently merely because a diagnostic
    holds another reference to a nested code object. Include explicit code
    fields/constants instead; adaptive interpreter caches are not source code.
    This format is still qualified by the exact interpreter in runtime_identity.
    """
    if isinstance(value, CodeType):
        fields = ("co_argcount", "co_posonlyargcount", "co_kwonlyargcount", "co_nlocals",
                  "co_stacksize", "co_flags", "co_code", "co_consts", "co_names", "co_varnames",
                  "co_filename", "co_name", "co_qualname", "co_firstlineno", "co_linetable",
                  "co_exceptiontable", "co_freevars", "co_cellvars")
        return ["code", {name: _code_value(getattr(value, name)) for name in fields}]
    if value is None:
        return ["none"]
    if value is Ellipsis:
        return ["ellipsis"]
    if type(value) in (str, int, bool):
        return [type(value).__name__, value]
    if type(value) is bytes:
        return ["bytes", value.hex()]
    if type(value) is float:
        return ["float", value.hex()]
    if type(value) is complex:
        return ["complex", value.real.hex(), value.imag.hex()]
    if type(value) is tuple:
        return ["tuple", [_code_value(item) for item in value]]
    if type(value) is frozenset:
        return ["frozenset", sorted((_code_value(item) for item in value), key=_json)]
    raise SourceFault("unsupported_code_constant")


def _code_sha(code):
    return _sha(_json(_code_value(code)))


def _dependencies():
    for package, version in PACKAGES.items():
        if importlib.metadata.version(package) != version:
            raise SourceFault("helper_dependency_drift")
    # Never disable plugins by environment or silently treat an unknown cache
    # as empty. Check installed entries even if plugin discovery is cached.
    if tuple(importlib.metadata.entry_points(group="pydantic")):
        raise SourceFault("pydantic_plugins_not_empty")
    module = sys.modules.get("pydantic.plugin._loader")
    if module is None:
        return
    if type(module) is not ModuleType:
        raise SourceFault("unknown_pydantic_plugin_cache")
    values = vars(module)
    path = Path(importlib.metadata.distribution("pydantic").locate_file("pydantic/plugin/_loader.py")).resolve()
    spec = values.get("__spec__")
    if (values.get("__file__") != str(path) or spec is None or spec.origin != str(path)
            or values.get("_loading_plugins") is not False
            or "_plugins" not in values
            or not (values["_plugins"] is None or type(values["_plugins"]) is dict and not values["_plugins"])):
        raise SourceFault("unknown_pydantic_plugin_cache")
    function = values.get("get_plugins")
    expected = _code_index(compile(path.read_bytes(), str(path), "exec", dont_inherit=True, optimize=0))["get_plugins"]
    if (type(function) is not FunctionType or function.__globals__ is not values
            or function.__code__ != expected or function.__code__.co_filename != str(path)):
        raise SourceFault("unknown_pydantic_plugin_cache")


def _verify(record):
    namespace, bindings, code, exports = record
    if set(namespace) != set(bindings) or any(namespace[key] is not value for key, value in bindings.items()):
        raise SourceFault("derived_binding_drift")
    expected = _code_index(code)

    def function_check(function):
        if type(function) is not FunctionType or function.__globals__ is not namespace:
            raise SourceFault("derived_function_drift")
        original = expected.get(function.__qualname__)
        if (original is None or function.__code__ != original
                or function.__code__.co_filename != code.co_filename):
            raise SourceFault("derived_code_drift")

    for value in namespace.values():
        if isinstance(value, type) and value.__module__ == namespace["__name__"]:
            for member in vars(value).values():
                if isinstance(member, (classmethod, staticmethod)):
                    member = member.__func__
                if isinstance(member, property):
                    member = member.fget
                if type(member) is FunctionType and member.__module__ == namespace["__name__"]:
                    function_check(member)
        elif type(value) is FunctionType and value.__module__ == namespace["__name__"]:
            function_check(value)
        elif callable(value) and type(getattr(value, "__wrapped__", None)) is FunctionType:
            if value.__wrapped__.__module__ == namespace["__name__"]:
                function_check(value.__wrapped__)
    if any(exports[key] is not namespace[key] for key in exports):
        raise SourceFault("derived_export_drift")


def load(name="evidence"):
    """Return only measured authentic implementations, not a module lookalike."""
    if name not in SOURCE_LOCKS:
        raise SourceFault("unexpected_helper")
    descriptor = describe()
    manifest = json.loads((HERE / "manifest.json").read_bytes())
    variants = manifest.get("source_loader")
    if (type(variants) is not dict or set(variants) != {"cpython-3.11", "cpython-3.12"}
            or variants.get(_interpreter_key()) != descriptor):
        raise SourceFault("derived_manifest_drift")
    _dependencies()
    if name not in _CACHE:
        tree, source = _derive(name, (ROOT / descriptor["sources"][name]["source_path"]).read_bytes())
        if source != descriptor["sources"][name] or _ast_sha(tree) != source["derived_ast_sha256"]:
            raise SourceFault("derived_tree_drift")
        label = f"reviewer_comparison_v2.source_locked_{name}_{source['derived_ast_sha256']}"
        filename = f"<{label}>"
        code = compile(tree, filename, "exec", dont_inherit=True, optimize=0)
        namespace = {"__name__": label}
        exec(code, namespace)  # noqa: S102 -- only the exact hash/AST-locked project source above
        _dependencies()
        # run_spec retains its own postponed annotations. There is deliberately
        # no sys.modules impersonation to resolve them through. Let the REAL
        # Pydantic models finish their schema using these exact source globals;
        # never substitute annotations, fields, validators or serializers.
        base_model = namespace["BaseModel"]
        for value in tuple(namespace.values()):
            if (isinstance(value, type) and issubclass(value, base_model)
                    and value.__module__ == label and not value.__pydantic_complete__):
                value.model_rebuild(_types_namespace=namespace)
                if not value.__pydantic_complete__:
                    raise SourceFault("derived_schema_incomplete")
        _dependencies()
        exports = MappingProxyType({key: namespace[key] for key in EXPORTS[name]})
        record = (namespace, dict(namespace), code, exports)
        _verify(record)
        _CACHE[name] = record
    _verify(_CACHE[name])
    return _CACHE[name][3]


def runtime_identity():
    """Actual compiled identities, qualified by this exact Python interpreter.

    The manifest binds version-qualified ASTs and shared source/loader bytes. These code hashes
    additionally enter execution identity (and its post-key comparison); they
    are intentionally not asserted equal across Python 3.11/3.12 or builds.
    """
    for name in SOURCE_LOCKS:
        load(name)
    return {"implementation": sys.implementation.name, "python": sys.version,
            "cache_tag": sys.implementation.cache_tag,
            "code_encoding": "recursive_code_fields_v1",
            "code_sha256": {name: _code_sha(record[2]) for name, record in sorted(_CACHE.items())}}
