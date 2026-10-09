"""One cold sysconfig import in the normal Linux TEST capability profile.

The exact optional executable-realpath call receives an explicit OSError;
the genuine stdlib fallback returns its argument before the owned project
override. No executable realpath/lstat is moved before Guard. This does not
promise host-realpath semantics, arbitrary concurrent reflection equivalence,
or a sandbox against hostile in-process Python. Runtime metadata and the
bootstrap's public stdlib root are trusted; private data gets no new read root.
"""

from contextlib import contextmanager
import hashlib
from importlib.machinery import PathFinder, SourceFileLoader
import os
from pathlib import Path
import sys
from threading import get_ident
from types import CodeType


# Finite reviewed source candidates, NOT claims about CI's installed bytes.
# Values: bytes, interpreter version, initial-call line, public provenance.
CANDIDATES = {
    "e21755a918f488db1bd21d23120ee36ad09382c553b79735a121ee1fbdbcc08d":
        (32768, (3, 12, 3), 221, "observed_local_ubuntu_24_04"),
    "c16887bf792dc21f27fe5d2ca4ee271f131b7f6a88593def43be52cfbc846759":
        (30315, (3, 11, 17), 192, "public_cpython_v3_11_17_candidate"),
    "11422a6dbcaa7e46effe3b3bc2e1ae3386fe7177d8f182558ad137f3a7fae1c1":
        (30999, (3, 12, 3), 197, "public_cpython_v3_12_3_candidate"),
}
UNAVAILABLE = "normal_test_profile_optional_executable_realpath_unavailable"
_EXEC_MODULE = SourceFileLoader.exec_module
_GET_CODE = SourceFileLoader.get_code
_RUNTIME_NAMES = ("executable", "prefix", "base_prefix", "exec_prefix", "base_exec_prefix", "_home")


def _runtime():
    return tuple(getattr(sys, name, None) for name in _RUNTIME_NAMES)


def _environment_absent():
    return not any(name.upper() == "_PYTHON_PROJECT_BASE" for name in os.environ)


def _source_binding(source, version):
    with source.open("rb") as handle:
        raw = handle.read(65537)
    digest = hashlib.sha256(raw).hexdigest()
    candidate = CANDIDATES.get(digest)
    if candidate is None or (len(raw), version) != candidate[:2]:
        raise RuntimeError("linux_sysconfig_source_not_approved")
    return compile(raw, str(source), "exec", dont_inherit=True, optimize=0), candidate[2], {
        "source_sha256": digest, "source_bytes": len(raw), "source_candidate": candidate[3],
        "interpreter": list(version), "scope": "normal_test_capability_not_host_realpath"}


class _ImportScope:
    def __init__(self, profile, delegate):
        self.profile, self.delegate = profile, delegate

    def create_module(self, spec):
        return self.delegate.create_module(spec)

    def exec_module(self, module):
        try:
            self.profile._exec(module, self.delegate)
        finally:
            sys.meta_path[:] = [item for item in sys.meta_path if item is not self.profile]
            self.profile.facts["finder_restored"] = True


class _Profile:
    def __init__(self, owned, stdlib_paths):
        if (sys.implementation.name != "cpython" or sys.flags.optimize
                or "sysconfig" in sys.modules or not _environment_absent()
                or type(sys.executable) is not str or not os.path.isabs(sys.executable)):
            raise RuntimeError("linux_sysconfig_requires_cold_clean_runtime")
        self.source = Path(sys.base_prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "sysconfig.py"
        if str(self.source.parent) not in stdlib_paths:
            raise RuntimeError("linux_sysconfig_source_outside_verified_stdlib")
        self.reference, self.call_line, self.facts = _source_binding(self.source, sys.version_info[:3])
        self.project = Path(owned) / "linux-sysconfig-project"
        self.project.mkdir()
        if self.project.resolve() != self.project or any(self.project.iterdir()):
            raise RuntimeError("linux_sysconfig_project_not_empty_physical_directory")
        self.runtime, self.thread = _runtime(), get_ident()
        self.facts.update({"applicable": True, "declined_optional_resolution": 0,
                           "loader_code_verified": False, "completed": False, "fault": False})
        self.selected = self.active = False
        self.module = self.spec = self.module_code = self.safe_code = None

    def find_spec(self, fullname, path=None, target=None):
        if fullname != "sysconfig":
            return None
        if self.selected or target is not None or get_ident() != self.thread:
            self.facts["fault"] = True
            raise RuntimeError("linux_sysconfig_import_scope_mismatch")
        self.selected = True
        spec = PathFinder.find_spec(fullname, [str(self.source.parent)])
        if (spec is None or spec.origin != str(self.source) or type(spec.loader) is not SourceFileLoader
                or spec.loader.path != str(self.source) or spec.loader.name != fullname):
            self.facts["fault"] = True
            raise RuntimeError("linux_sysconfig_loader_origin_mismatch")
        self.spec = spec
        spec.loader = _ImportScope(self, spec.loader)
        return spec

    def _authorized(self, frame, raw, args, kwargs):
        parent = frame.f_back
        namespace = None if self.module is None else self.module.__dict__
        return (self.active and get_ident() == self.thread and _runtime() == self.runtime
                and self.facts["declined_optional_resolution"] == 0
                and type(raw) is str and raw == self.runtime[0] and not args and not kwargs
                and os.environ.get("_PYTHON_PROJECT_BASE") == str(self.project)
                and sys.modules.get("sysconfig") is self.module
                and self.module.__spec__ is self.spec and self.spec.name == "sysconfig"
                and self.spec.origin == str(self.source) and getattr(self.spec, "_initializing", False)
                and self.spec.loader is self.delegate and self.module.__loader__ is self.delegate
                and frame.f_code is self.safe_code and frame.f_globals is namespace
                and parent is not None and parent.f_code is self.module_code
                and parent.f_globals is namespace and parent.f_lineno == self.call_line
                and namespace.get("realpath") is self.adapter and os.path.realpath is self.adapter)

    def _realpath(self, raw, *args, **kwargs):
        if self._authorized(sys._getframe(1), raw, args, kwargs):
            self.facts["declined_optional_resolution"] += 1
            raise OSError(UNAVAILABLE)
        return self.original_realpath(raw, *args, **kwargs)

    def _exec(self, module, delegate):
        if (self.active or self.module is not None or get_ident() != self.thread
                or sys.modules.get("sysconfig") is not module or module.__spec__ is not self.spec
                or _runtime() != self.runtime or not _environment_absent()
                or type(delegate) is not SourceFileLoader or "get_code" in vars(delegate)
                or delegate.exec_module.__func__ is not _EXEC_MODULE or delegate.get_code.__func__ is not _GET_CODE):
            self.facts["fault"] = True
            raise RuntimeError("linux_sysconfig_exec_scope_mismatch")
        self.module, self.delegate = module, delegate
        module.__loader__ = self.spec.loader = delegate
        self.original_realpath = os.path.realpath
        self.adapter = self._realpath

        def checked_code(name):
            code = _GET_CODE(delegate, name)
            if name != "sysconfig" or self.module_code is not None or code != self.reference:
                raise RuntimeError("linux_sysconfig_loaded_code_mismatch")
            candidates = [item for item in code.co_consts if type(item) is CodeType and item.co_name == "_safe_realpath"]
            if len(candidates) != 1:
                raise RuntimeError("linux_sysconfig_safe_code_missing")
            self.module_code, self.safe_code = code, candidates[0]
            self.facts["loader_code_verified"] = True
            return code  # The original loader's actual code object, never a replacement.

        failed = True
        try:
            delegate.get_code = checked_code
            os.environ["_PYTHON_PROJECT_BASE"] = str(self.project)
            self.active = True
            os.path.realpath = self.adapter
            _EXEC_MODULE(delegate, module)
            if (self.facts["declined_optional_resolution"] != 1 or module._PROJECT_BASE != str(self.project)
                    or module._PYTHON_BUILD is not False or module._safe_realpath.__code__ is not self.safe_code
                    or module._safe_realpath.__globals__ is not module.__dict__ or _runtime() != self.runtime):
                raise RuntimeError("linux_sysconfig_completed_profile_mismatch")
            self.facts["completed"] = True
            failed = False
        finally:
            # Restore only our own bindings. Foreign mutation is a failing
            # profile, not permission to overwrite another thread's update.
            self.active = False
            if os.path.realpath is self.adapter:
                os.path.realpath = self.original_realpath
            if module.__dict__.get("realpath") is self.adapter:
                module.realpath = self.original_realpath
            if delegate.__dict__.get("get_code") is checked_code:
                del delegate.get_code
            if os.environ.get("_PYTHON_PROJECT_BASE") == str(self.project):
                del os.environ["_PYTHON_PROJECT_BASE"]
            restored = (os.path.realpath is self.original_realpath and _environment_absent()
                        and ("realpath" not in module.__dict__ or module.realpath is self.original_realpath)
                        and "get_code" not in vars(delegate))
            self.facts.update({"bindings_restored": restored, "fault": failed or not restored})
            if not failed and not restored:
                raise RuntimeError("linux_sysconfig_restore_failed")


@contextmanager
def install(owned, stdlib_paths):
    """Wait for one natural import; the real loader owns the shorter mutation scope."""
    if sys.platform != "linux":
        yield {"applicable": False}
        return
    profile = _Profile(owned, stdlib_paths)
    sys.meta_path.insert(0, profile)
    failed = True
    try:
        yield profile.facts
        failed = False
    finally:
        sys.meta_path[:] = [item for item in sys.meta_path if item is not profile]
        profile.facts["finder_restored"] = True
        if not failed and (profile.facts["fault"] or not profile.facts["completed"]):
            raise RuntimeError("linux_sysconfig_import_not_completed")
