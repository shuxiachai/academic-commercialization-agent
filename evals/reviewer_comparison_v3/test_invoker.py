"""Fixed offline test bootstrap, NOT a native runner or a general Python sandbox.

Run only with python -B -E -S. Full production-model imports may initialize real
vendor code in a fresh test-owned profile; the native loader's cold audit does
not inherit these shims or gain permission to use any vendor configuration.
"""

# ruff: noqa: E402
# Executable startup must restrict the stdlib path before further imports.

import sys


def _fixed_invocation(argv, no_site, no_bytecode, ignore_environment):
    return len(argv) == 1 and bool(no_site) and bool(no_bytecode) and bool(ignore_environment)


def _stdlib_bootstrap():
    # sys is built in and os is frozen on the admitted CPython versions. Remove
    # ambient PYTHONPATH before importing even ordinary path/helper libraries.
    import os

    if (sys.implementation.name != "cpython" or sys.version_info[:2] not in {(3, 11), (3, 12)}
            or not _fixed_invocation(sys.argv, sys.flags.no_site, sys.flags.dont_write_bytecode,
                                     sys.flags.ignore_environment)
            or os.__spec__.origin != "frozen"):
        raise SystemExit("fixed_test_bootstrap_required")
    executable = os.path.abspath(sys.executable)
    parent = os.path.dirname(executable)
    if os.path.basename(parent).casefold() not in {"scripts", "bin"}:
        raise SystemExit("venv_executable_required")
    with open(os.path.join(os.path.dirname(parent), "pyvenv.cfg"), encoding="utf-8") as handle:
        fields = dict(line.rstrip("\r\n").split(" = ", 1) for line in handle if " = " in line)
    home = fields.get("home")

    def physical(path):
        return os.path.normcase(os.path.realpath(path))

    if (not home or fields.get("include-system-site-packages", "").casefold() != "false"
            or physical(home) != os.path.dirname(physical(sys._base_executable))):
        raise SystemExit("venv_base_identity_mismatch")
    expected_base = home if sys.platform == "win32" else os.path.dirname(home)
    if physical(sys.base_prefix) != physical(expected_base):
        raise SystemExit("base_prefix_drift")
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    if sys.platform == "win32":
        paths = [os.path.join(sys.base_prefix, "Lib"), os.path.join(sys.base_prefix, "DLLs"),
                 os.path.join(sys.base_prefix, f"python{sys.version_info.major}{sys.version_info.minor}.zip")]
    elif sys.platform == "linux":
        paths = [os.path.join(sys.base_prefix, "lib", version),
                 os.path.join(sys.base_exec_prefix, "lib", version, "lib-dynload"),
                 os.path.join(sys.base_prefix, "lib", f"python{sys.version_info.major}{sys.version_info.minor}.zip")]
    else:
        raise SystemExit("unsupported_test_platform")
    sys.path[:] = paths
    return tuple(paths)


_STDLIB_PATHS = _stdlib_bootstrap() if __name__ == "__main__" else ()

import ast
import atexit
from collections import Counter
from contextlib import contextmanager
import glob
import hashlib
from io import StringIO
import json
import ntpath
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import uuid

__test__ = False
ROOT = Path(__file__).absolute().parents[2]
CHECK_FILES = ("tests/reviewer_comparison_v3_checks.py", "tests/reviewer_output_contract_checks.py")
ENTRY = "evals/reviewer_comparison_v3/test_invoker.py"
PROFILE_BASE = ROOT / "outputs" / "reviewer_v3_test_isolation"
_REAL_LSTAT = os.lstat
NORMAL_MODEL_FLAGS = frozenset({"PYTHON_DOTENV_DISABLED", "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
                               "CREWAI_TRACING_ENABLED", "OTEL_SDK_DISABLED", "DO_NOT_TRACK",
                               "UNIXCONFDIR", "UNIXUSRLIBDIR"})
# Only normal-model startup may read this locked public dependency resource
# through the vendor's original utilities/../ spelling. Never a native grant.
I18N_VERSION = "1.14.7"
I18N_SOURCE_SHA256 = "aba9f6145b700c89d6dc21c4c6bc079671bf2ae1c89f2c079f30348e3e3536a8"
I18N_ASSET_SHA256 = "2262aad4bcb403c03ee6a3184936d32775aa7fb0ce513384d5e913876b96a1e0"
URLLIB3_CONNECTION_SHA256 = "2633bbdb69731e5ccb5cf4e4afd65605d86c7979cc5633126f50c92d5ad74a74"
PYTEST_PATHLIB_SHA256 = "c9fe77dccbf52afa1196ff92870ed919e09f254c082710a86ed417fd3ca90329"
APPDIRS_VERSION = "1.4.4"
APPDIRS_SOURCE_SHA256 = "83df6cdac5e19ef4c49bbf688f86d62344e86a973efd298a28d5ef3971e45627"
APPDIRS_METADATA_SHA256 = "9394d57d730d2861d37e9db09ba109293b86c0636ea104794ea4201fc8b01bc3"
# Independently measured installed Windows wheels, not portable native hashes.
# No pythonwin, .pth, bootstrap/post-install execution or ambient PATH change.
WINDOWS_NORMAL_BINDINGS = {
    "cp312": {
        "pywin32-312.dist-info/METADATA": "77f53e90408dd3bdcf5f73a20d6548504313dee2ad34f8b3794b2202583a84b1",
        "pywin32-312.dist-info/WHEEL": "ad1e507ec59c665de6adae409920fb15dd1dcd0c59de51c2a43a3bd0891f0cae",
        "win32/lib/pywintypes.py": "7d75c04bc69db49bcf69f58bf27fcdcd0942b326f8a21ed937530e31c2be4a41",
        "win32/lib/win32con.py": "9f5fd728d5fde234a3d9c0bac893d77958efeb37864b4441ad28c0422a67dad6",
        "win32/lib/winerror.py": "10b9d4cebf06f2ca75762cdd82b3ddf2d3a2d99e2343b528b9ecb4db56f62e55",
        "win32/_win32sysloader.pyd": "db277aae2b8417dbd01435a8691cc74707f6699ae3199e1b205f609cefa5ad24",
        "win32/win32file.pyd": "359ef2dc11546f619a9ac53c01a399d621c093b7cfc843fb9d7b211d0b15e103",
        "pywin32_system32/pywintypes312.dll": "9bd7f8c39a84d7b1ea43bfcd33c04631c60f4ff28167e82bb21987cc1c353766"
    },
    "cp311": {
        "pywin32-312.dist-info/METADATA": "77f53e90408dd3bdcf5f73a20d6548504313dee2ad34f8b3794b2202583a84b1",
        "pywin32-312.dist-info/WHEEL": "5c75cc289537ca8561d596a70574c9e5b0c66faee8118b45d52e9b77c6b88b32",
        "win32/lib/pywintypes.py": "7d75c04bc69db49bcf69f58bf27fcdcd0942b326f8a21ed937530e31c2be4a41",
        "win32/lib/win32con.py": "9f5fd728d5fde234a3d9c0bac893d77958efeb37864b4441ad28c0422a67dad6",
        "win32/lib/winerror.py": "10b9d4cebf06f2ca75762cdd82b3ddf2d3a2d99e2343b528b9ecb4db56f62e55",
        "win32/_win32sysloader.pyd": "8ad2e21cd1a627fa36f082ce0b71f81c91f9d3825908a520072245a2545e1be1",
        "win32/win32file.pyd": "cdc61a990c12853733460a01a79bbe1e741c312db1b90cc2d99775c26c5f241b",
        "pywin32_system32/pywintypes311.dll": "dcc14a7ed85a324e357eab7db970d8db61387c8b5d6baa23283aabd8300c4e09"
    }
}


def _key(path, *, windows=False):
    module = ntpath if windows else os.path
    result = module.normpath(module.abspath(os.fsdecode(path)))
    return result.casefold() if windows else result


def _inside(path, root, *, windows=False):
    sep = "\\" if windows else os.sep
    return path == root or path.startswith(root.rstrip(sep) + sep)


class Guard:
    """Cumulative Python I/O policy; rejected attempts cannot become a green exit."""

    def __init__(self, owned, readonly, real_private, *, windows=False, discovery=(), normal_i18n_site=None):
        self.windows = windows
        self.owned = _key(owned, windows=windows)
        self.readonly = tuple(_key(path, windows=windows) for path in readonly)
        self.real_private = tuple(_key(path, windows=windows) for path in real_private)
        self.discovery = frozenset(_key(path, windows=windows) for path in discovery)
        self.normal_i18n_site = os.fsdecode(normal_i18n_site) if normal_i18n_site is not None else None
        self.violations = []

    def deny(self, category):
        self.violations.append(category)
        raise PermissionError(category)

    def path(self, path, operation="read", *, resource_open=False):
        if isinstance(path, int):
            return  # fdopen uses a descriptor obtained through an audited open.
        raw = os.fsdecode(path)
        # Preserve parent components BEFORE normpath erases them. A lexical
        # ROOT/link/.. is not physical ROOT when link redirects elsewhere.
        raw_parts = (raw.replace("\\", "/") if self.windows else raw).split("/")
        has_parent = ".." in raw_parts
        # Compare the ORIGINAL absolute components, not normpath/resolve. This
        # pure comparison precedes normalization; all private denials still
        # precede the first physical check or content read for the exception.
        resource_match = False
        if self.normal_i18n_site is not None and resource_open and operation == "read":
            module = ntpath if self.windows else os.path
            expected = module.join(self.normal_i18n_site, "crewai", "utilities", "..", "translations", "en.json")
            expected_parts = (expected.replace("\\", "/") if self.windows else expected).split("/")
            resource_match = module.isabs(raw) and raw_parts == expected_parts
        value = _key(path, windows=self.windows)
        def within(root):
            return _inside(value, root, windows=self.windows)
        # Real stores are refused BEFORE even an overlapping cache allowance.
        if any(within(root) for root in self.real_private):
            self.deny("real_private_path")
        owned = within(self.owned)
        parts = value.replace("\\", "/").split("/")
        name = parts[-1]
        if name.startswith(".env") and (not owned or operation != "probe"):
            self.deny("dotenv_file_access")
        private_names = {"secret.key", "tokens.enc", "settings.json", "crewai_settings.json",
                         ".crewai_settings.json", ".crewai_user.json", ".crewai_write_test"}
        if not owned and (name in private_names or "credentials" in parts
                          or any(parts[i:i + 2] == [".config", "crewai"] for i in range(len(parts) - 1))):
            self.deny("vendor_private_path")
        if name in {"sitecustomize.py", "usercustomize.py"} or name.endswith(".pth"):
            self.deny("startup_hook_access")
        if has_parent:
            if not resource_match:
                self.deny("noncanonical_parent_component_forbidden")
            if _key(self.normal_i18n_site, windows=self.windows) not in self.readonly:
                self.deny("read_outside_admitted_sources")
            try:
                _validate_i18n_resource(raw, self.normal_i18n_site, windows=self.windows)
            except OSError:
                self.deny("i18n_resource_not_physical")
            except ValueError:
                self.deny("i18n_resource_identity_mismatch")
        # FileFinder enumerates namespace parents and swallows PermissionError
        # as an empty directory. Admit only these exact directory operations,
        # never descendant content, and reject links before granting discovery.
        if operation in {"list", "probe"} and value in self.discovery:
            try:
                _no_discovery_links(value, windows=self.windows)
            except OSError:
                self.deny("discovery_directory_not_physical")
            return
        if owned:
            return
        if operation == "write":
            self.deny("write_outside_owned_profile")
        if any(within(root) for root in self.readonly):
            return
        # Import machinery probes ancestors; probing is not directory listing
        # or reading their files. Private-path checks above still take priority.
        if operation == "probe" and any(_inside(root, value, windows=self.windows)
                                         for root in (*self.readonly, self.owned)):
            return
        self.deny("read_outside_admitted_sources")

    def finish_status(self, pytest_status):
        return int(pytest_status) or (1 if self.violations else 0)


def _i18n_physical_path(raw, *, windows=False):
    """Inspect original prefixes before crossing '..'; never normalize first.

    Even the trusted anchor and the directory cancelled by '..' must be real
    directories. Captured lstat avoids recursive probe hooks. This is not an
    atomic open or protection against concurrent filesystem replacement.
    """
    module = ntpath if windows else os.path
    drive, tail = module.splitdrive(raw)
    parts = (tail.replace("\\", "/") if windows else tail).split("/")
    if not module.isabs(raw) or parts[0] != "" or any(part in {"", "."} for part in parts[1:]):
        raise PermissionError("i18n_original_absolute_path_required")
    current = drive + module.sep
    prefixes = [current]
    for part in parts[1:]:
        current = module.join(current, part)
        prefixes.append(current)
    for index, candidate in enumerate(prefixes):
        info = _REAL_LSTAT(candidate)
        mode = getattr(info, "st_mode", None)
        attributes = getattr(info, "st_file_attributes", None)
        if (not isinstance(mode, int) or stat.S_ISLNK(mode)
                or (windows and not isinstance(attributes, int))
                or (attributes is not None and attributes & 0x400)
                or not (stat.S_ISREG(mode) if index == len(prefixes) - 1 else stat.S_ISDIR(mode))):
            raise PermissionError("i18n_original_path_not_physical")


def _validate_i18n_resource(raw, site, *, windows=False):
    """Bind just CrewAI 1.14.7's default asset; no custom prompt or directory grant."""
    module = ntpath if windows else os.path
    _i18n_physical_path(raw, windows=windows)
    asset = module.join(site, "crewai", "translations", "en.json")
    # Normalization is only a final target assertion AFTER original inspection.
    if module.normpath(raw) != asset:
        raise ValueError("i18n_bound_target_drift")
    source = module.join(site, "crewai", "utilities", "i18n.py")
    metadata = module.join(site, f"crewai-{I18N_VERSION}.dist-info", "METADATA")
    for filename, expected in ((source, I18N_SOURCE_SHA256), (asset, I18N_ASSET_SHA256), (metadata, None)):
        _i18n_physical_path(filename, windows=windows)
        # These canonical public reads remain subject to the enclosing I/O
        # guard. No recursive parent exception or cached approval is needed.
        with open(filename, "rb") as handle:
            data = handle.read(256 * 1024 + 1)
        if len(data) > 256 * 1024:
            raise ValueError("i18n_binding_oversize")
        if expected is not None:
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError("i18n_binding_hash_drift")
        elif [line for line in data.decode("utf-8").splitlines() if line.startswith(("Name: ", "Version: "))] != [
                "Name: crewai", f"Version: {I18N_VERSION}"]:
            raise ValueError("i18n_distribution_identity_drift")


def _no_discovery_links(path, *, windows=False):
    """Inspect every lexical ancestor before granting exact directory discovery.

    Use the captured lstat, not resolve or a guarded probe that recurses. This
    refuses symlinks and Windows reparse points; it is not a race-proof OS jail.
    """
    module = ntpath if windows else os.path
    candidate = path
    while True:
        info = _REAL_LSTAT(candidate)
        if (not stat.S_ISDIR(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & 0x400):
            raise PermissionError("discovery_directory_not_physical")
        parent = module.dirname(candidate)
        if parent == candidate:
            return
        candidate = parent


def _no_owned_links(path, owned):
    """Reject test-created symlink/junction escape without recursive guard calls."""
    absolute = Path(os.path.abspath(path))
    if not absolute.is_relative_to(owned):
        return
    for candidate in (absolute, *absolute.parents):
        if not candidate.is_relative_to(owned):
            break
        try:
            info = _REAL_LSTAT(candidate)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise PermissionError("owned_profile_link_forbidden")


def _verified_environment():
    # -S on 3.11 may leave sys.prefix at the base installation. Locate the
    # environment through the ACTUAL executable and pyvenv.cfg, never by
    # overwriting prefix or trusting VIRTUAL_ENV/UV_PROJECT_ENVIRONMENT.
    executable = Path(os.path.abspath(sys.executable))
    if executable.parent.name.casefold() not in {"scripts", "bin"}:
        raise RuntimeError("venv_executable_required")
    environment = executable.parent.parent
    raw = (environment / "pyvenv.cfg").read_text(encoding="utf-8")
    fields = dict(line.split(" = ", 1) for line in raw.splitlines() if " = " in line)
    if fields.get("include-system-site-packages", "").casefold() != "false":
        raise RuntimeError("system_site_packages_not_admitted")
    home = fields.get("home")
    if not home or Path(home).resolve() != Path(sys._base_executable).resolve().parent:
        raise RuntimeError("venv_base_identity_mismatch")
    site = (environment / "Lib" / "site-packages" if sys.platform == "win32" else
            environment / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages")
    if not site.is_dir() or not executable.is_file():
        raise RuntimeError("venv_site_packages_unavailable")
    return environment, site.resolve(), hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _preload_canonical():
    """Import the real test module before probes change, with separate globals.

    Aliasing __main__ would let local fault-injection patches alter the outer
    guard. Only verified namespace parents and this source may load here;
    third-party initialization remains behind the subsequently installed guard.
    """
    import importlib
    from importlib.machinery import PathFinder, SourceFileLoader

    name = "evals.reviewer_comparison_v3.test_invoker"
    if not _STDLIB_PATHS or any(key in sys.modules for key in (
            "evals", "evals.reviewer_comparison_v3", name)):
        raise RuntimeError("canonical_preload_requires_clean_bootstrap")
    original_path = sys.path[:]
    source = ROOT / ENTRY
    try:
        sys.path[:] = [*_STDLIB_PATHS, str(ROOT)]
        search = [str(ROOT)]
        for parent, directory in (("evals", ROOT / "evals"),
                                  ("evals.reviewer_comparison_v3", source.parent)):
            _no_discovery_links(str(directory), windows=sys.platform == "win32")
            spec = PathFinder.find_spec(parent, search)
            if (spec is None or spec.loader is not None
                    or list(spec.submodule_search_locations or ()) != [str(directory)]):
                raise RuntimeError("canonical_namespace_drift")
            importlib.import_module(parent)
            search = [str(directory)]
        _i18n_physical_path(str(source), windows=sys.platform == "win32")
        spec = PathFinder.find_spec(name, search)
        raw = source.read_bytes()
        if (spec is None or type(spec.loader) is not SourceFileLoader or spec.origin != str(source)
                or spec.loader.get_code(name) != compile(raw, str(source), "exec", dont_inherit=True)):
            raise RuntimeError("canonical_source_drift")
        module = importlib.import_module(name)
        if (module.__file__ != str(source) or module.__spec__.origin != str(source)
                or module.__dict__ is globals() or module._REAL_LSTAT is not _REAL_LSTAT
                or module._REAL_LSTAT is not os.lstat
                or [key for key, value in sys.modules.items() if value is module] != [name]):
            raise RuntimeError("canonical_original_capture_drift")
        return {"module": name, "source_sha256": hashlib.sha256(raw).hexdigest(),
                "scope": "authentic_pre_guard_import_separate_globals"}
    finally:
        sys.path[:] = original_path


def _owned_profile():
    # Only a new random child is reusable as this invocation's runtime state;
    # no caller can select an old output/profile or supply an alternate cwd.
    if (ROOT / "outputs").resolve() != ROOT / "outputs":
        raise RuntimeError("output_parent_link_forbidden")
    PROFILE_BASE.mkdir(exist_ok=True)
    if PROFILE_BASE.resolve() != PROFILE_BASE:
        raise RuntimeError("profile_parent_link_forbidden")
    owned = PROFILE_BASE / uuid.uuid4().hex
    owned.mkdir()
    paths = {name: owned / name for name in ("home", "local", "roaming", "tmp", "work", "xdg-config", "xdg-data", "xdg-cache")}
    for path in paths.values():
        path.mkdir()
    if _distro_profile_target():
        # Keep the established eight-key helper interface. These two dedicated
        # siblings are derived from the owned work path, never caller env paths.
        for path in _distro_profile_dirs(paths).values():
            path.mkdir()
            _no_owned_links(path, owned)
            _no_discovery_links(str(path), windows=sys.platform == "win32")
            if any(path.iterdir()):
                raise RuntimeError("distro_profile_directory_not_empty")
    return owned, paths


def _environment_values(original, paths):
    # A small OS-process allowlist avoids copying provider/auth/tracing/storage,
    # Redis, Python startup or pytest injection values. Never log their values.
    keep = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "NUMBER_OF_PROCESSORS",
            "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER", "TZ"}
    retained = {name: value for name, value in original.items() if name.upper() in keep}
    # Deterministic untranslated TEST diagnostics, including derived cold children.
    # C.UTF-8 is not equivalent: CPython gettext expands it to en_US.UTF-8 and
    # probes base/share/locale outside the source allowance. Do not grant that
    # read or prewarm gettext. The allowlist drops mixed-case and extra LC_* keys.
    retained.update({"HOME": str(paths["home"]), "USERPROFILE": str(paths["home"]),
                       "LANGUAGE": "C", "LC_ALL": "C", "LC_MESSAGES": "C", "LANG": "C",
                       "LOCALAPPDATA": str(paths["local"]), "APPDATA": str(paths["roaming"]),
                       "TEMP": str(paths["tmp"]), "TMP": str(paths["tmp"]), "TMPDIR": str(paths["tmp"]),
                       "XDG_CONFIG_HOME": str(paths["xdg-config"]), "XDG_DATA_HOME": str(paths["xdg-data"]),
                       "XDG_CACHE_HOME": str(paths["xdg-cache"]), "PYTHON_DOTENV_DISABLED": "1",
                       "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "GIT_CONFIG_NOSYSTEM": "1",
                       "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0", "GIT_NO_LAZY_FETCH": "1"})
    if _distro_profile_target():
        retained.update({name: str(path) for name, path in _distro_profile_dirs(paths).items()})
    return retained


def _test_environment(paths):
    selected = _environment_values(os.environ, paths)
    os.environ.clear()
    os.environ.update(selected)
    # This affects pytest discovery only, NOT Pydantic's unchanged plugin gate.
    tempfile.tempdir = None
    os.chdir(paths["work"])


def _cold_script_and_names():
    raw = (ROOT / CHECK_FILES[0]).read_text(encoding="utf-8")
    tree = ast.parse(raw)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "identity_process")
    script = next(node.value.value for node in function.body if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "script" for target in node.targets)
                  and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str))
    inherited = ast.parse(raw.split("# These checks are additive.", 1)[0])
    names = {node.name for node in inherited.body if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")}
    if len(names) != 43:
        raise RuntimeError("inherited_function_set_drift")
    return script, names


def _io_callbacks(guard, owned, cold_script):
    def path(raw, operation="read", *, resource_open=False):
        guard.path(raw, operation, resource_open=resource_open)
        if isinstance(raw, (str, bytes, os.PathLike)):
            try:
                _no_owned_links(raw, owned)
            except PermissionError:
                guard.deny("owned_profile_link_forbidden")

    def glob_pattern(raw):
        # A pattern is policy input, not an lstat-able Windows filename. Check
        # its literal directory prefix now; each actual scan is still audited.
        guard.path(raw)
        prefix = os.fsdecode(raw)
        while glob.has_magic(prefix):
            parent = os.path.dirname(prefix)
            if parent == prefix:
                guard.deny("glob_literal_root_unavailable")
            prefix = parent
        path(prefix or os.curdir)

    def audit(event, args):
        if event.startswith("socket."):
            guard.deny("network_forbidden")
        if event == "open":
            filename, mode, flags = args
            writing = (mode and any(char in mode for char in "wax+")) or flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            path(filename, "write" if writing else "read", resource_open=not writing)
        elif event in {"os.listdir", "os.scandir"}:
            path(args[0] if args[0] is not None else os.getcwd(), "list")
        elif event in {"pathlib.Path.glob", "pathlib.Path.rglob"}:
            path(args[0] if args[0] is not None else os.getcwd())
        elif event == "glob.glob":
            # Absolute patterns already identify their effective root. Relative
            # ones need glob.glob/2's root_dir; neither event enumerates yet.
            if os.path.isabs(args[0]):
                glob_pattern(args[0])
        elif event == "glob.glob/2":
            pattern, _recursive, root_dir, dir_fd = args
            if dir_fd is not None:
                guard.deny("glob_directory_descriptor_forbidden")
            glob_pattern(os.path.join(root_dir, pattern) if root_dir is not None else pattern)
        elif event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.truncate"}:
            path(args[0], "write")
        elif event == "os.rename":
            path(args[0], "write")
            path(args[1], "write")
        elif event == "sqlite3.connect" and args[0] != ":memory:":
            if not args[0] or str(args[0]).startswith("file:"):
                guard.deny("sqlite_uri_or_temporary_database_forbidden")
            path(args[0], "write")
        elif event in {"os.symlink", "os.link"}:
            guard.deny("link_creation_forbidden")
        elif event == "import" and args[0] in {"sitecustomize", "usercustomize"}:
            guard.deny("startup_hook_import")
        elif event == "subprocess.Popen":
            executable, arguments, cwd, _environment = args
            permitted, runtime = _subprocess_policy(executable, arguments, cwd, cold_script)
            if not permitted:
                guard.deny("unexpected_subprocess")
            if runtime is not None:
                if (not isinstance(_environment, dict)
                        or any(name.upper() in NORMAL_MODEL_FLAGS for name in _environment)):
                    guard.deny("normal_model_flag_in_cold_child")
                path(runtime, "write")
        elif event in {"os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.startfile"}:
            guard.deny("unexpected_process_execution")

    return path, audit


def _install_io_guard(guard, owned, cold_script):
    path, audit = _io_callbacks(guard, owned, cold_script)
    sys.addaudithook(audit)
    for name in ("stat", "lstat", "access"):
        original = getattr(os, name)

        def probe(raw, *args, _original=original, **kwargs):
            path(raw, "probe")
            return _original(raw, *args, **kwargs)

        setattr(os, name, probe)
    return _install_nt312_path_guard(path)


def _nt312_path_argument(path):
    """Freeze one native path conversion, preserving NT path_converter precedence.

    Read real type dictionaries rather than instance attributes: an instance
    __index__ or a spoofed __class__ is not the C index protocol. A PathLike's
    returned integer must remain TypeError, not become a second fd conversion.
    """
    import operator

    real_mro = type.__dict__["__mro__"].__get__(type(path))
    real_dict = type.__dict__["__dict__"]
    if not any(base is str for base in real_mro) and not any(base is bytes for base in real_mro):
        if any("__index__" in real_dict.__get__(base) for base in real_mro):
            native = operator.index(path)
            if not -(1 << 31) <= native < (1 << 31):
                raise OverflowError("nt312_path_fd_outside_c_int")
            return native, native
        path = os.fspath(path)
        real_mro = type.__dict__["__mro__"].__get__(type(path))
    # Invoke base descriptors directly so hostile subclass overrides cannot
    # change the value between the policy check and the native predicate.
    native = str.__str__(path) if any(base is str for base in real_mro) else bytes.__bytes__(path)
    decoded = os.fsdecode(native)
    if "\x00" in decoded or len(decoded.encode("utf-16-le", "surrogatepass")) // 2 > 32767:
        raise ValueError("nt312_path_invalid_windows_string")
    return native, decoded


def _nt312_path_predicate(path, original, check):
    """Only converter ValueError is False; Guard and native failures propagate."""
    try:
        native, decoded = _nt312_path_argument(path)
    except ValueError:  # Includes UnicodeError, as in the native suppress_value_error converter.
        return False
    check(decoded, "probe")
    return original(native)


def _install_nt312_path_guard(check):
    """Guard two NT312 native predicates without changing their query semantics.

    The default route covers CPython 3.12 on Windows; measured runtime evidence
    remains specific to the separately recorded patch version. Integer inputs
    keep the existing Guard int rule: this adds no descriptor-origin guarantee.
    """
    if os.name != "nt" or sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 12):
        return None
    import nt
    from types import BuiltinFunctionType, ModuleType

    if sys.platform != "win32" or os.path is not ntpath or type(ntpath) is not ModuleType or type(nt) is not ModuleType:
        raise RuntimeError("nt312_path_guard_interface_drift")
    original_isfile, original_exists = getattr(nt, "_path_isfile", None), getattr(nt, "_path_exists", None)

    def guarded_isfile(path):
        return _nt312_path_predicate(path, original_isfile, check)

    def guarded_exists(path):
        return _nt312_path_predicate(path, original_exists, check)

    if (getattr(getattr(ntpath, "isfile", None), "__code__", None) is guarded_isfile.__code__
            or getattr(getattr(ntpath, "exists", None), "__code__", None) is guarded_exists.__code__):
        raise RuntimeError("nt312_path_guard_already_installed")
    for name, original in (("isfile", original_isfile), ("exists", original_exists)):
        if (getattr(ntpath, name, None) is not original or type(original) is not BuiltinFunctionType
                or original.__self__ is not nt or original.__module__ != "nt"
                or original.__name__ != "_path_" + name or original.__text_signature__ != "($module, /, path)"):
            raise RuntimeError("nt312_path_guard_interface_drift")
    if not callable(check):
        raise RuntimeError("nt312_path_guard_check_required")
    # Both entries already exist in an exact module dictionary. One builtin
    # dict update installs both after all validation, without user callbacks.
    ntpath.__dict__.update({"isfile": guarded_isfile, "exists": guarded_exists})
    return guarded_isfile, guarded_exists


def _subprocess_policy(executable, arguments, cwd, cold_script):
    """Only local Git HEAD identity and the unchanged frozen cold audit child.

    Windows audits the serialized command line, whereas POSIX audits argv.
    Compare the actual serializer and reconstruct the bounded three-argument
    tail; never parse the embedded audit program as a shell command.
    """
    if cwd is None or Path(cwd) != ROOT:
        return False, None
    git = ["git", "--no-optional-locks", "rev-parse", "HEAD"]
    if executable in (None, "git") and arguments in (git, subprocess.list2cmdline(git)):
        return True, None
    prefix = [sys.executable, "-B", "-c", cold_script]
    if isinstance(arguments, str):
        serialized = subprocess.list2cmdline(prefix) + " "
        if not arguments.startswith(serialized):
            return False, None
        import re

        match = re.fullmatch(r'(\w+) ("[^"]+"|\S+) ([\w-]+)', arguments[len(serialized):])
        if match is None:
            return False, None
        tail = [match[1], match[2].strip('"'), match[3]]
        if arguments != subprocess.list2cmdline([*prefix, *tail]):
            return False, None
        arguments = [*prefix, *tail]
    probes = {"none", "mkdir", "os-mkdir", "write", "os-open", "client", "credential",
              "dependency-credential", "credential-storage", "settings", "settings-probe",
              "consent", "tokens", "framework-import", "socket", "dns"}
    if (isinstance(arguments, list) and len(arguments) == 7 and arguments[:4] == prefix
            and arguments[4] in {"import", "identity", "production", "prepare", "repeat"}
            and arguments[6] in probes and executable in (None, sys.executable)):
        return True, arguments[5]
    return False, None


def _windows_resolver(paths, guard):
    def resolve(selector):
        if selector == "CSIDL_LOCAL_APPDATA":
            return str(paths["local"])
        if selector == "CSIDL_APPDATA":
            return str(paths["roaming"])
        guard.deny("unrequested_windows_folder")
    return resolve


def _cold_environment(original):
    # These flags must never hide a new dotenv/framework regression from the
    # frozen child's own cumulative audit. Profile paths remain test-owned.
    # Keep the explicit C TEST locale: neither lane validates the host locale.
    # Removing it here would reintroduce an unspecified diagnostic language.
    return {name: value for name, value in original.items() if name.upper() not in NORMAL_MODEL_FLAGS}


def _install_cold_envelope(cold_script, guard):
    original = subprocess.Popen

    class ColdEnvelope(original):
        def __init__(self, arguments, *args, **kwargs):
            admitted, runtime = _subprocess_policy(kwargs.get("executable"), arguments,
                                                   kwargs.get("cwd"), cold_script)
            if admitted and runtime is not None:
                if args or kwargs.get("env") is not None:
                    guard.deny("unexpected_cold_environment_override")
                kwargs["env"] = _cold_environment(os.environ)
            super().__init__(arguments, *args, **kwargs)

    subprocess.Popen = ColdEnvelope


def _appdirs_require_cold(names, guard):
    if any(name == root or name.startswith(root + ".")
           for name in names for root in ("appdirs", "pythoncom", "win32com")):
        guard.deny("normal_appdirs_requires_cold_modules")


def _validated_appdirs(site, guard):
    """Bind actual executable/ABI and physical source, without reprobing the exe.

    The outer bootstrap already verified executable/config/base identity BEFORE
    installing the guard. Repeating that physical probe afterward was a prior
    diagnostic defect. Here the selected site must still derive from that actual
    executable, not sys.prefix, an environment hint, or a caller-selected root.
    """
    import struct

    try:
        abi = _windows_normal_abi(sys.implementation.name, sys.version_info[:2],
                                  sys.implementation.cache_tag, struct.calcsize("P"))
    except ValueError:
        guard.deny("normal_appdirs_runtime_identity")
    executable = Path(os.path.abspath(sys.executable))
    if (sys.platform != "win32" or sys.flags.optimize or executable.parent.name.casefold() != "scripts"
            or site != executable.parent.parent / "Lib/site-packages"
            or _key(site, windows=True) not in guard.readonly
            or guard.normal_i18n_site is None
            or _key(site, windows=True) != _key(guard.normal_i18n_site, windows=True)):
        guard.deny("normal_appdirs_runtime_identity")
    source = site / "appdirs.py"
    metadata = site / f"appdirs-{APPDIRS_VERSION}.dist-info/METADATA"
    try:
        for path in (source, metadata):
            _i18n_physical_path(str(path), windows=True)
        with source.open("rb") as handle:
            raw = handle.read(64 * 1024 + 1)
        with metadata.open("rb") as handle:
            distribution = handle.read(64 * 1024 + 1)
    except OSError:
        guard.deny("normal_appdirs_not_physical")
    if (hashlib.sha256(raw).hexdigest() != APPDIRS_SOURCE_SHA256
            or hashlib.sha256(distribution).hexdigest() != APPDIRS_METADATA_SHA256):
        guard.deny("normal_appdirs_source_identity")
    if [line for line in distribution.decode("utf-8").splitlines()
            if line.startswith(("Name: ", "Version: "))] != ["Name: appdirs", "Version: " + APPDIRS_VERSION]:
        guard.deny("normal_appdirs_distribution_identity")
    return source, raw, abi


class _AppdirsImportGate:
    """One exact optional import in one genuine executing module, never a fake COM.

    Code and globals are captured by the REAL SourceFileLoader immediately before
    it executes the unchanged bound source. Filename/name equality alone, a copy
    of the code object, or forged __import__ globals never acquire the exception.
    """

    def __init__(self, original, guard):
        self.original, self.guard = original, guard
        self.code = self.namespace = None
        self.hits = 0

    def __call__(self, name, globals=None, locals=None, fromlist=(), level=0):
        sensitive = isinstance(name, str) and any(
            str.__eq__(name, root) is True or str.startswith(name, root + ".")
            for root in ("win32com", "pythoncom"))
        if not sensitive:
            return self.original(name, globals, locals, fromlist, level)
        caller = sys._getframe(1)
        if (self.code is None or self.namespace is None or caller.f_code is not self.code
                or caller.f_globals is not self.namespace
                or globals is not self.namespace or locals is not self.namespace):
            self.guard.deny("normal_appdirs_optional_import_origin")
        if (type(name) is not str or name != "win32com.shell" or fromlist is not None
                or type(level) is not int or level != 0):
            self.guard.deny("normal_appdirs_optional_import_shape")
        if self.hits:
            self.guard.deny("normal_appdirs_optional_import_repeated")
        self.hits += 1
        # This deliberate TEST capability profile chooses appdirs' own fallback;
        # it says nothing about COM availability/functionality on the actual host.
        raise ImportError("optional_win32com_shell_unavailable_in_normal_test_profile")


@contextmanager
def _appdirs_import_scope(spec, expected_code, resolver, guard):
    """Observe the authentic loader, restoring every temporary hook on BaseException."""
    import builtins

    loader = spec.loader
    if any(name in vars(loader) for name in ("get_code", "exec_module")):
        guard.deny("normal_appdirs_loader_shadowed")
    original_import = builtins.__import__
    original_meta = sys.meta_path[:]
    original_get_code, original_exec = loader.get_code, loader.exec_module
    gate = _AppdirsImportGate(original_import, guard)
    executions = []

    def get_code(fullname):
        code = original_get_code(fullname)
        if fullname != "appdirs" or gate.code is not None or code != expected_code:
            guard.deny("normal_appdirs_executing_code_identity")
        gate.code = code  # Identity of the object the real exec_module will execute.
        return code

    def exec_module(module):
        if (executions or sys.modules.get("appdirs") is not module or module.__name__ != "appdirs"
                or module.__spec__ is not spec or module.__loader__ is not loader
                or module.__file__ != spec.origin or module.__package__ != ""):
            guard.deny("normal_appdirs_module_identity")
        executions.append(module)
        gate.namespace = module.__dict__
        original_exec(module)  # Standard loader, genuine unmodified source/globals.
        if gate.hits != 1 or module.__version__ != APPDIRS_VERSION:
            guard.deny("normal_appdirs_optional_import_not_observed")
        # Install before importlib returns, dotenv import, or any caller can use
        # the selected fallback. NEVER read/capture/call a native original resolver.
        module._get_win_folder = resolver

    class Finder:
        def find_spec(self, fullname, path=None, target=None):
            if fullname != "appdirs":
                return None
            if path is not None or target is not None or executions:
                guard.deny("normal_appdirs_unexpected_reload")
            return spec

    try:
        loader.get_code, loader.exec_module = get_code, exec_module
        sys.meta_path.insert(0, Finder())
        builtins.__import__ = gate
        yield gate
    finally:
        # Keep restoration independent of success checks and exception classes.
        builtins.__import__ = original_import
        sys.meta_path[:] = original_meta
        for name in ("get_code", "exec_module"):
            if name in vars(loader):
                delattr(loader, name)


def _normal_appdirs(paths, guard):
    """Explicit optional-COM-unavailable profile for the one Windows test import."""
    import importlib
    from importlib.machinery import PathFinder, SourceFileLoader

    _appdirs_require_cold(tuple(sys.modules), guard)
    site = Path(os.path.abspath(sys.executable)).parent.parent / "Lib/site-packages"
    source, raw, abi = _validated_appdirs(site, guard)
    spec = PathFinder.find_spec("appdirs", sys.path)
    if (spec is None or type(spec.loader) is not SourceFileLoader or spec.name != "appdirs"
            or spec.origin != str(source) or spec.submodule_search_locations is not None):
        guard.deny("normal_appdirs_selected_loader_identity")
    expected = compile(raw, str(source), "exec", dont_inherit=True, optimize=0)
    _appdirs_require_cold(tuple(sys.modules), guard)
    with _appdirs_import_scope(spec, expected, _windows_resolver(paths, guard), guard) as gate:
        module = importlib.import_module("appdirs")
        if (module.__dict__ is not gate.namespace or sys.modules.get("appdirs") is not module
                or module.__spec__ is not spec or module.__file__ != str(source) or gate.hits != 1):
            guard.deny("normal_appdirs_completed_import_identity")
    return module, {"profile": "normal_test_optional_win32com_shell_unavailable",
                    "optional_COM_validated": False, "synthetic_import_error_hits": gate.hits,
                    "abi": abi, "version": APPDIRS_VERSION, "source": str(source),
                    "source_sha256": APPDIRS_SOURCE_SHA256,
                    "scope": "one_cold_authentic_appdirs_import_not_native_COM_or_113_refusal_attribution"}


def _normal_model_shims(paths, guard):
    if sys.platform == "win32":
        _appdirs, appdirs_profile = _normal_appdirs(paths, guard)
    else:
        import appdirs  # noqa: F401 - retain the ordinary non-Windows import.
        appdirs_profile = {"profile": "normal_test_non_windows_appdirs", "optional_COM_validated": False}

    import dotenv.main  # The owned Windows resolver is already installed.

    @contextmanager
    def empty_dotenv(self):
        target = self.dotenv_path
        if (self.stream is not None or not isinstance(target, (str, os.PathLike))
                or _key(target, windows=guard.windows) not in {
                    _key(ROOT / ".env", windows=guard.windows),
                    _key(paths["work"] / ".env", windows=guard.windows)}):
            guard.deny("unexpected_dotenv_target")
        with StringIO("") as stream:
            yield stream

    dotenv.main.DotEnv._get_stream = empty_dotenv
    return appdirs_profile


@contextmanager
def _normal_ipv6_unavailable():
    """Force an unsupported-IPv6 TEST profile; do not claim host IPv6 coverage.

    Only an in-process capability object changes, and it is always restored.
    Socket APIs and the cumulative deny-all-socket guard remain untouched.
    Nothing propagates through environment/sitecustomize to native cold children.
    """
    import socket

    original = socket.has_ipv6
    socket.has_ipv6 = False
    try:
        yield
    finally:
        socket.has_ipv6 = original


def _normal_urllib3(site, guard):
    import importlib

    source = site / "urllib3/util/connection.py"
    if "urllib3" in sys.modules:
        guard.deny("normal_urllib3_must_be_cold")
    try:
        _i18n_physical_path(str(source), windows=guard.windows)
    except OSError:
        guard.deny("normal_urllib3_not_physical")
    if hashlib.sha256(source.read_bytes()).hexdigest() != URLLIB3_CONNECTION_SHA256:
        guard.deny("normal_urllib3_source_drift")
    with _normal_ipv6_unavailable():
        module = importlib.import_module("urllib3")
    if (module.__version__ != "2.7.0" or Path(module.__file__) != site / "urllib3/__init__.py"
            or Path(module.util.connection.__file__) != source or module.util.connection.HAS_IPV6 is not False):
        guard.deny("normal_urllib3_profile_drift")
    return {"profile": "normal_test_ipv6_unavailable_not_host_coverage", "HAS_IPV6": False}


def _windows_normal_abi(implementation, version, cache_tag, pointer_bytes):
    if (implementation != "cpython" or version not in {(3, 11), (3, 12)} or pointer_bytes != 8
            or cache_tag != f"cpython-{version[0]}{version[1]}"):
        raise ValueError("unsupported_normal_windows_abi")
    return f"cp{version[0]}{version[1]}"


def _validated_pywin32(site, abi, guard):
    """Admit exactly the measured wheel files, before any native load or new path."""
    if abi not in WINDOWS_NORMAL_BINDINGS or _key(site, windows=True) not in guard.readonly:
        guard.deny("normal_pywin32_abi_or_site")
    bindings = WINDOWS_NORMAL_BINDINGS[abi]
    for relative, expected in bindings.items():
        filename = site / relative
        try:
            _i18n_physical_path(str(filename), windows=True)
            with filename.open("rb") as handle:
                data = handle.read(1024 * 1024 + 1)
        except OSError:
            guard.deny("normal_pywin32_not_physical")
        if hashlib.sha256(data).hexdigest() != expected:
            guard.deny("normal_pywin32_hash_drift")
        if relative.endswith("/WHEEL") and f"Tag: {abi}-{abi}-win_amd64" not in data.decode("ascii").splitlines():
            guard.deny("normal_pywin32_wheel_abi")
        if relative.endswith("/METADATA") and [line for line in data.decode("utf-8").splitlines()
                if line.startswith(("Name: ", "Version: "))] != ["Name: pywin32", "Version: 312"]:
            guard.deny("normal_pywin32_version")
        if relative.endswith((".pyd", ".dll")):
            offset = int.from_bytes(data[60:64], "little")
            if (data[:2] != b"MZ" or data[offset:offset + 4] != b"PE\0\0"
                    or int.from_bytes(data[offset + 4:offset + 6], "little") != 0x8664):
                guard.deny("normal_pywin32_machine_abi")
    return {"dll": site / f"pywin32_system32/pywintypes{abi[2:]}.dll",
            "loader": site / "win32/_win32sysloader.pyd", "file": site / "win32/win32file.pyd"}


class _PyWin32SystemApi:
    """Only loaded-module identity and one absolute, restricted preload reference."""

    def __init__(self):
        import ctypes

        self.ctypes = ctypes
        # ctypes itself binds the OS kernel APIs. Restrict this explicit binding
        # to System32; no user directory or pywin32 basename search occurs here.
        self.kernel = ctypes.WinDLL("kernel32.dll", winmode=0x800, use_last_error=True)
        self.kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        self.kernel.GetModuleHandleW.restype = ctypes.c_void_p
        self.kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32]
        self.kernel.GetModuleFileNameW.restype = ctypes.c_uint32
        self.kernel.LoadLibraryExW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint32]
        self.kernel.LoadLibraryExW.restype = ctypes.c_void_p
        self.kernel.FreeLibrary.argtypes = [ctypes.c_void_p]
        self.kernel.FreeLibrary.restype = ctypes.c_int

    def loaded_path(self, basename):
        handle = self.kernel.GetModuleHandleW(basename)
        if not handle:
            return None
        buffer = self.ctypes.create_unicode_buffer(32768)
        count = self.kernel.GetModuleFileNameW(handle, buffer, len(buffer))
        if not count or count >= len(buffer):
            raise OSError("loaded_module_identity_unavailable")
        return buffer.value

    def preload(self, absolute):
        # Only this bound DLL directory and System32 may resolve dependencies;
        # no default/user/ambient directory search is requested by this load.
        handle = self.kernel.LoadLibraryExW(str(absolute), None, 0x100 | 0x800)
        if not handle:
            raise OSError("bound_pywin32_preload_failed")
        return handle

    def release(self, handle):
        if not self.kernel.FreeLibrary(handle):
            raise OSError("bound_pywin32_release_failed")


def _refuse_foreign_pywin32(paths, api, guard):
    for expected in paths.values():
        loaded = api.loaded_path(expected.name)
        if loaded is not None and _key(loaded, windows=True) != _key(expected, windows=True):
            guard.deny("foreign_pywin32_already_loaded")


class _PyWin32Lease:
    """Retain our preload and AddDllDirectory handles until explicit close/exit.

    Closing releases only OUR load reference, not the references owned by real
    imported extension modules. It is not a forced DLL unload or an OS jail.
    """

    def __init__(self, api, guard):
        self.api, self.guard = api, guard
        self.dll_handle = self.directory_handle = None
        self.added_paths = []
        self.facts = {}

    def close(self):
        try:
            if self.dll_handle is not None:
                self.api.release(self.dll_handle)
                self.dll_handle = None
            if self.directory_handle is not None:
                self.directory_handle.close()
                self.directory_handle = None
            for path in self.added_paths:
                sys.path.remove(path)
            self.added_paths.clear()
        except (OSError, ValueError):
            self.guard.deny("normal_pywin32_cleanup_failed")


def _normal_pywin32(site, guard):
    import importlib
    import struct

    abi = _windows_normal_abi(sys.implementation.name, sys.version_info[:2],
                              sys.implementation.cache_tag, struct.calcsize("P"))
    paths = _validated_pywin32(site, abi, guard)
    if any(name in sys.modules for name in ("pywintypes", "_win32sysloader", "win32file", "win32con", "winerror")):
        guard.deny("normal_pywin32_python_modules_not_cold")
    api = _PyWin32SystemApi()
    _refuse_foreign_pywin32(paths, api, guard)  # BEFORE preload or AddDllDirectory.
    lease = _PyWin32Lease(api, guard)
    atexit.register(lease.close)  # Later dependency shutdown runs before release.
    try:
        lease.directory_handle = os.add_dll_directory(str(paths["dll"].parent))
        lease.dll_handle = api.preload(paths["dll"])
        _refuse_foreign_pywin32(paths, api, guard)
        if api.loaded_path(paths["dll"].name) is None:
            guard.deny("bound_pywin32_not_loaded")
        additions = [str(site / "win32"), str(site / "win32/lib")]
        if any(path in sys.path for path in additions):
            guard.deny("normal_pywin32_paths_not_cold")
        sys.path[:0] = additions
        lease.added_paths = additions
        loader = importlib.import_module("_win32sysloader")
        if (Path(loader.__file__) != paths["loader"]
                or _key(loader.GetModuleFilename(paths["dll"].name), windows=True) != _key(paths["dll"], windows=True)):
            guard.deny("bound_pywin32_loader_identity")
        wrapper = str(site / "win32/lib/pywintypes.py")
        previous_profile = sys.getprofile()
        existing_calls = []

        def observe_existing_branch(frame, event, function):
            if (event == "c_call" and frame.f_code.co_filename == wrapper
                    and frame.f_code.co_name == "__import_pywin32_system_module__"):
                if function is loader.LoadModule:
                    guard.deny("pywin32_naked_load_fallback_forbidden")
                if function is loader.GetModuleFilename:
                    existing_calls.append(True)
            if previous_profile is not None:
                previous_profile(frame, event, function)

        sys.setprofile(observe_existing_branch)
        try:
            types = importlib.import_module("pywintypes")
        finally:
            sys.setprofile(previous_profile)
        file = importlib.import_module("win32file")
        locks = importlib.import_module("portalocker")
        _refuse_foreign_pywin32(paths, api, guard)
        if (existing_calls != [True] or Path(types.__file__) != paths["dll"]
                or Path(file.__file__) != paths["file"] or Path(locks.__file__) != site / "portalocker/__init__.py"):
            guard.deny("normal_pywin32_origin_or_branch_drift")
        lease.facts = {"abi": abi, "pywintypes": types.__file__, "win32file": file.__file__,
                       "portalocker": locks.__file__, "existing_loaded_branch_calls": len(existing_calls),
                       "dll_search_directory": str(paths["dll"].parent), "python_paths": list(additions)}
        return lease
    except BaseException:  # Cleanup cannot turn a failed bootstrap into a pass.
        lease.close()
        raise


def _normal_dependency_startup(site, guard):
    profile = _normal_urllib3(site, guard)
    lease = _normal_pywin32(site, guard) if sys.platform == "win32" else None
    return profile, lease


def _pytest_bookmark_callback(paths, guard, facts):
    """Validate the original bookmark arguments before any optional link action."""
    base = os.fspath(paths["tmp"]) + os.sep + "pytest"

    def raw_parts(value):
        raw = os.fsdecode(value)
        module = ntpath if guard.windows else os.path
        drive, tail = module.splitdrive(raw)
        parts = (tail.replace("\\", "/") if guard.windows else tail).split("/")
        if (not module.isabs(raw) or parts[0] != ""
                or any(part in {"", ".", ".."} for part in parts[1:])):
            guard.deny("unexpected_pytest_bookmark")
        return drive, parts

    # Validate before Path/normpath can discard original dot components.
    raw_parts(base)
    if not _inside(_key(base, windows=guard.windows), guard.owned, windows=guard.windows):
        guard.deny("unexpected_pytest_bookmark")

    def omit(root, target, link_to):
        if raw_parts(root) != raw_parts(base):
            guard.deny("unexpected_pytest_bookmark")
        target = os.fsdecode(target)
        if (not target.endswith("current") or any(char in target for char in "/\\:")
                or target in {".", ".."}):
            guard.deny("unexpected_pytest_bookmark")
        prefix = target[:-len("current")]
        drive, parts = raw_parts(link_to)
        base_drive, base_parts = raw_parts(base)
        leaf = parts[-1]
        number = leaf[len(prefix):] if leaf.startswith(prefix) else ""
        if (drive != base_drive or parts[:-1] != base_parts or not number
                or any(char not in "0123456789" for char in number)
                or (len(number) > 1 and number.startswith("0"))):
            guard.deny("unexpected_pytest_bookmark")
        guard.path(root, "probe")
        guard.path(link_to, "probe")
        try:
            _no_discovery_links(os.fsdecode(link_to), windows=guard.windows)
        except OSError:
            guard.deny("pytest_bookmark_not_physical")
        facts["omitted"] += 1

    return omit


@contextmanager
def _pytest_bookmarks(paths, site, guard):
    """Omit only pytest's optional owned current bookmark, never allow links.

    Real numbered-directory creation and fixture/cleanup code stay unchanged.
    Replacing the narrow helper BEFORE it unlinks/links avoids swallowed audit
    faults; it does not filter them. This process-local adapter is restored even
    on an exception and is never installed in cold children.
    """
    from _pytest import pathlib as pytest_pathlib

    source = site / "_pytest/pathlib.py"
    original = pytest_pathlib._force_symlink
    if (Path(pytest_pathlib.__file__) != source
            or hashlib.sha256(source.read_bytes()).hexdigest() != PYTEST_PATHLIB_SHA256
            or original.__module__ != "_pytest.pathlib"
            or original.__code__.co_filename != str(source)
            or original.__code__.co_firstlineno != 204):
        guard.deny("pytest_bookmark_implementation_drift")
    facts = {"scope": "optional_pytest_current_bookmarks_omitted_not_link_support", "omitted": 0}
    pytest_pathlib._force_symlink = _pytest_bookmark_callback(paths, guard, facts)
    try:
        yield facts
    finally:
        pytest_pathlib._force_symlink = original


def _pytest_arguments(paths):
    # The fixed checks use capsys, not capfd. Default fd capture opens devnull
    # before collection; memory-backed sys capture needs no device exception.
    return ["-q", "-x", "--tb=short", "--capture=sys", "-p", "no:cacheprovider", "-c", str(ROOT / "pyproject.toml"),
            # Preserve tests/conftest.py without probing unadmitted ancestors.
            f"--confcutdir={ROOT / 'tests'}",
            # Keep the real logging plugin off devnull and outside basetemp,
            # whose pytest cleanup must not unlink the active owned log file.
            f"--log-file={paths['tmp'] / 'pytest.log'}",
            "--basetemp", str(paths["tmp"] / "pytest"), *(str(ROOT / item) for item in CHECK_FILES)]


# H1 changes only the normal Windows CP311 test configuration. The temporary
# environment override is restored, but sysconfig's projectbase/srcdir cache is
# deliberately retained; successful tests do not validate the old environment.
_SYSCONFIG_INPUTS = ("REVIEWER_V3_SYSCONFIG_MODE", "REVIEWER_V3_SYSCONFIG_CASE",
                     "REVIEWER_V3_SYSCONFIG_CONTROL_SHA256")
_SYSCONFIG_CASES = {"isolated": "fc7cbaa4-5792-405b-93db-af23b8b0a30e",
                    "missing-control": "d2641d46-78e5-49a4-afc4-d86ebf91ed69"}
_SYSCONFIG_SOURCES = {
    "sysconfig.py": (31166, "7a4778f7124f839c2314e2ece29b867b190ede5a1d4c3a571f0dae722b596ae3"),
    "subprocess.py": (90941, "4f08d583a95b415762d888fff499c19103040d4b7027e25a73d46c7e3d777d04"),
}
_SYSCONFIG_NT_SCHEME = {
    "stdlib": "{installed_base}/Lib", "platstdlib": "{base}/Lib",
    "purelib": "{base}/Lib/site-packages", "platlib": "{base}/Lib/site-packages",
    "include": "{installed_base}/Include", "platinclude": "{installed_base}/Include",
    "scripts": "{base}/Scripts", "data": "{base}",
}
_SYSCONFIG_POLICY = {
    "schema": "reviewer-v3-normal-sysconfig-policy-v1",
    "default_mode": "isolated", "default_scope": "nt_cpython_3_11_only",
    "inputs": _SYSCONFIG_INPUTS, "explicit_cases": _SYSCONFIG_CASES,
    "sources": _SYSCONFIG_SOURCES, "nt_scheme": _SYSCONFIG_NT_SCHEME,
    "prepare_override": "owned_empty_project_then_restore_absence_in_finally",
    "cached_state": "projectbase_and_nt_srcdir_remain_owned",
    "other_platforms": "unchanged_prepare_environment_not_evaluated",
    "cold_evidence": "real_popen_explicit_environment_not_child_self_report",
}

# Default configuration eligibility is a series policy, not a claim that every
# patch version was measured. Exact locks belong to explicit diagnostics.
_NT312_DEFAULT_POLICY = {
    "schema": "reviewer-v3-normal-nt312-profile-policy-v1",
    "default_mode": "isolated", "default_scope": "nt_cpython_3_12_series",
    "prepare_override": "owned_empty_project_then_restore_absence_in_finally",
    "cached_state": "projectbase_and_nt_srcdir_remain_owned",
    "distro_environment": ["UNIXCONFDIR", "UNIXUSRLIBDIR"],
    "distro_directories": ["distro-etc", "distro-usr-lib"],
    "cold_evidence": "original_NORMAL_MODEL_FLAGS_filter_and_audit",
    "platform_validation": "not_evaluated", "patch_version_validation": "separate_observed_records_only",
}


def _sysconfig_configuration(original, *, platform=None):
    """Capture optional diagnostic binding once, before the original clean-env."""
    platform = (os.name, sys.implementation.name, sys.version_info[:2]) if platform is None else platform
    legacy_target = platform == ("nt", "cpython", (3, 11))
    nt312 = _nt312_profile_target(platform=platform)
    applicable = legacy_target or nt312
    found = {name: value for name, value in original.items() if name.upper() in _SYSCONFIG_INPUTS}
    mode, case, control = "isolated", None, None
    if found:
        if set(found) != set(_SYSCONFIG_INPUTS) or not legacy_target:
            raise RuntimeError("sysconfig_diagnostic_binding_incomplete_or_unsupported")
        mode, case, control = (found[name] for name in _SYSCONFIG_INPUTS)
        if (mode not in _SYSCONFIG_CASES or case != _SYSCONFIG_CASES[mode]
                or type(control) is not str or len(control) != 64
                or any(char not in "0123456789abcdef" for char in control)):
            raise RuntimeError("sysconfig_diagnostic_binding_invalid")
    policy_wire = json.dumps(_NT312_DEFAULT_POLICY if nt312 else _SYSCONFIG_POLICY, ensure_ascii=True, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
    return {"mode": mode, "diagnostic_binding": "explicit_h1" if found else "not_requested",
            "case_id": case, "control_sha256": control, "policy_sha256": hashlib.sha256(policy_wire).hexdigest(),
            "policy_applicable": applicable, "platform_validation": "not_evaluated"}


@contextmanager
def _normal_sysconfig_scope(project, configuration):
    if configuration["policy_applicable"]:
        with _sysconfig_prepare_scope(project, configuration["mode"]):
            yield
    else:
        # Other normal profiles have separate policies; H1 cannot enter here.
        yield


def _sysconfig_project(owned):
    """Create one empty physical child; never accept a caller-selected base."""
    project = owned / "sysconfig-project"
    project.mkdir()
    _no_owned_links(project, owned)
    _no_discovery_links(str(project), windows=sys.platform == "win32")
    if not stat.S_ISDIR(_REAL_LSTAT(project).st_mode) or any(project.iterdir()):
        raise RuntimeError("sysconfig_project_not_empty_physical_directory")
    return project


def _sysconfig_environment_absent(environ):
    return not any(name.upper() == "_PYTHON_PROJECT_BASE" for name in environ)


@contextmanager
def _sysconfig_prepare_scope(project, mode, *, environ=None, modules=None):
    """Limit the override to the actual prepare, including BaseException exits.

    Injectable mappings support isolated regressions without importing sysconfig
    or changing the interpreter's real module cache during the ordinary suite.
    """
    environ = os.environ if environ is None else environ
    modules = sys.modules if modules is None else modules
    if mode not in {"isolated", "missing-control"}:
        raise RuntimeError("sysconfig_mode_invalid")
    if "sysconfig" in modules or not _sysconfig_environment_absent(environ):
        raise RuntimeError("sysconfig_prepare_requires_cold_absent_environment")
    if mode == "isolated":
        environ["_PYTHON_PROJECT_BASE"] = str(project)
    try:
        yield
    finally:
        # The precondition proves the previous state was missing. Remove even
        # mixed-case additions made while prepare failed, then check before any
        # original ColdEnvelope can copy the process environment.
        for name in tuple(environ):
            if name.upper() == "_PYTHON_PROJECT_BASE":
                del environ[name]


def _sysconfig_nt_expectations(prefixes):
    """Independent fixed NT scheme, not values obtained from sysconfig itself."""
    variables = {"base": ntpath.normpath(prefixes["prefix"]),
                 "installed_base": ntpath.normpath(prefixes["base_prefix"])}
    return {name: ntpath.normpath(template.format(**variables))
            for name, template in _SYSCONFIG_NT_SCHEME.items()}


def _sysconfig_reference_codes(source, size, digest):
    """Bounded read/compile only; compilation never imports or executes source."""
    with source.open("rb") as handle:
        raw = handle.read(size + 1)
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
        raise RuntimeError("sysconfig_observer_source_identity_drift")
    code = compile(raw, str(source), "exec", dont_inherit=True, optimize=0)
    pending, result = [code], {}
    while pending:
        current = pending.pop()
        result[(current.co_name, current.co_firstlineno)] = current
        pending.extend(item for item in current.co_consts if type(item) is type(code))
    return result


class _SysconfigObservation:
    """Bounded evidence after original Guard decisions; no new I/O permission.

    Marker counts describe real guarded stat intents, not successful native
    stats. Popen audit delivery is not a child-side environment self-report or
    proof that all descendants exited. The original latch still runs last.
    """

    def __init__(self, guard, owned, cold_script, configuration, *, profile_sources=None, guarded_isfile=None):
        from importlib.machinery import SourceFileLoader

        self.guard, self.owned, self.cold_script = guard, owned, cold_script
        # Late callbacks must not depend on the script's transient __file__ global.
        self.invoker_filename = __file__
        self.loader_type = SourceFileLoader
        self.source = Path(sys.base_prefix) / "Lib/sysconfig.py"
        self.h6 = configuration["diagnostic_binding"] == "explicit_h6"
        self.ff = configuration["diagnostic_binding"] == "explicit_ff"
        self.nt312 = _nt312_observer_family(configuration)
        if self.nt312 and profile_sources is None:
            raise RuntimeError("nt312_profile_sources_required")
        self.source_bindings = _NT312_SYSCONFIG_SOURCES if self.nt312 else _SYSCONFIG_SOURCES
        self.codes = (profile_sources["sysconfig"] if self.nt312 else
                      _sysconfig_reference_codes(self.source, *self.source_bindings["sysconfig.py"]))
        self.build_code = next(code for (name, _line), code in self.codes.items() if name == "is_python_build")
        process_source = Path(sys.base_prefix) / "Lib/subprocess.py"
        process_codes = (profile_sources["subprocess"] if self.nt312 else
                         _sysconfig_reference_codes(process_source, *self.source_bindings["subprocess.py"]))
        self.execute_child = subprocess.Popen._execute_child.__code__
        if (self.execute_child != process_codes[("_execute_child", 1438 if self.nt312 else 1436)]
                or Path(subprocess.__file__) != process_source):
            raise RuntimeError("sysconfig_observer_subprocess_identity_drift")
        self.isfile_code = _nt312_isfile_identity(guarded_isfile) if self.nt312 else os.path.isfile.__code__
        self.phase, self.watch_markers = "guard_registration", False
        self.prefixes = {name: getattr(sys, name) for name in (
            "prefix", "base_prefix", "exec_prefix", "base_exec_prefix", "executable")}
        self.data = {
            "schema": "reviewer-v3-sysconfig-observation-v1", "configuration": configuration,
            "executed_entry": None, "refusal_windows": [],
            "marker_intents": {name: {"admitted": 0, "refused": 0} for name in ("Setup", "Setup.local")},
            "cold_launches": {"actual_audit_events": 0, "explicit_environment": 0,
                              "project_base_absent": 0, "normal_flags_absent": 0,
                              "child_self_reported_absent": None},
            "prepare_returned": False, "preparation": None, "env_absent_before_pytest": None,
            "sysconfig_facts": None, "refusal_witnesses": [], "saturated": False,
            "observer_fault": False,
            "pytest_started": False, "receipt_written": False,
            "tail_after_snapshot": "unobserved_original_latch_follows",
        }
        if self.h6:
            self.data["h6_profile"] = _H6_CASES[configuration["case_id"]]
        self.first_fault = _FirstObserverFault(self.data) if self.ff else None
        if self.ff:
            self.data["schema"] = "reviewer-v3-first-observer-fault-observation-v1"
            self.data["ff_prepare_outcome"] = "not_reached"
        if self.nt312:
            self.data["prepare_scope_exited"] = False
            self.data["env_absent_after_prepare_exit"] = None
            self.data["negative_stopped_before_pytest"] = False
            self.data["isfile_observer"] = "installed_guarded_isfile_identity"
        guard.path = self._wrap_path(guard.path)
        sys.addaudithook(self._audit)
        self.window("guard_registration")

    def _wrap_path(self, original):
        def observed_path(raw, operation="read", *, resource_open=False):
            try:
                answer = original(raw, operation, resource_open=resource_open)
            except PermissionError:
                self._observe_path_safely(raw, operation, refused=True)
                raise
            self._observe_path_safely(raw, operation, refused=False)
            return answer

        return observed_path

    def _observe_path_safely(self, raw, operation, *, refused):
        try:
            self._path_observation(raw, operation, refused=refused)
        except BaseException as exc:  # Diagnostics cannot replace a real Guard return or exception.
            # The explicit prepare gates and parent acceptance require False.
            # Preserve the original ledger; an observation fault is not a
            # fabricated Guard denial or evidence of a successful observation.
            self.data["observer_fault"] = True
            _capture_first_observer_fault(self, "sysconfig_path", None, exc)

    def _path_observation(self, raw, operation, *, refused):
        profile = getattr(self, "h3_profile", None)
        if profile is not None:
            if getattr(self, "first_fault", None) is None:
                profile.record_probe(raw, operation, refused=refused)
            else:
                profile.record_probe(raw, operation, refused=refused, phase=self.phase)
            if profile.data["observer_fault"]:
                self.data["observer_fault"] = True
        locator = getattr(self, "h2_locator", None)
        if refused and locator is not None:
            locator.record_refusal(operation)
            if locator.data["observer_fault"]:
                self.data["observer_fault"] = True
        if not refused and not self.watch_markers:
            return
        frame = marker_frame = None
        try:
            frame = sys._getframe(1)
            labels, isfile_seen = [], False
            for _ in range(8):
                if frame is None:
                    break
                label = "other"
                module = sys.modules.get("sysconfig")
                if (module is not None and frame.f_globals is module.__dict__
                        and frame.f_code == self.build_code):
                    marker_frame, label = frame, "sysconfig_is_python_build"
                elif frame.f_code is self.isfile_code:
                    isfile_seen, label = True, "guarded_isfile" if self.nt312 else "genericpath_isfile"
                elif frame.f_code.co_filename == self.invoker_filename:
                    label = {"observed_path": "observer_path", "path": "guard_path_callback",
                             "probe": "guard_probe"}.get(frame.f_code.co_name, "invoker_other")
                labels.append(label)
                frame = frame.f_back
            if marker_frame is not None and isfile_seen and operation == "probe" and type(raw) is str:
                base = marker_frame.f_globals.get("_PROJECT_BASE")
                if type(base) is str:
                    for marker in ("Setup", "Setup.local"):
                        if raw == os.path.join(base, "Modules", marker):
                            self.data["marker_intents"][marker]["refused" if refused else "admitted"] += 1
            if refused:
                witnesses = self.data["refusal_witnesses"]
                if len(witnesses) < 4:
                    witnesses.append({"stage": self.phase,
                                      "frames": labels, "operation": operation if operation in {
                                          "probe", "read", "write", "list"} else "other"})
                else:
                    self.data["saturated"] = True
        finally:
            # Do not retain executing frames through a diagnostic exception.
            del frame, marker_frame

    def _audit(self, event, args):
        if event != "subprocess.Popen" or sys._getframe(1).f_code is not self.execute_child:
            return
        executable, arguments, cwd, environment = args
        admitted, runtime = _subprocess_policy(executable, arguments, cwd, self.cold_script)
        if not admitted or runtime is None:
            return
        facts = self.data["cold_launches"]
        facts["actual_audit_events"] += 1
        explicit = type(environment) is dict
        absent = explicit and _sysconfig_environment_absent(environment)
        flags_absent = explicit and not any(name.upper() in NORMAL_MODEL_FLAGS for name in environment)
        facts["explicit_environment"] += int(explicit)
        facts["project_base_absent"] += int(absent)
        facts["normal_flags_absent"] += int(flags_absent)
        if not explicit or not absent or not flags_absent:
            raise RuntimeError("sysconfig_observer_cold_environment_leak")

    def window(self, stage):
        self.data["refusal_windows"].append({"stage": stage, "count": len(self.guard.violations),
                                             "categories": dict(Counter(self.guard.violations))})

    def require_prepare_ledger(self, stage):
        if stage not in {"before", "after"}:
            raise RuntimeError("sysconfig_prepare_ledger_stage_invalid")
        mode = self.data["configuration"]["mode"]
        expected = 2 if stage == "after" and mode == "missing-control" else 0
        if self.data["observer_fault"]:
            raise RuntimeError("sysconfig_observer_fault_before_pytest")
        if len(self.guard.violations) != expected:
            # sysconfig may swallow PermissionError as a missing build marker.
            # Any unrelated earlier refusal still stops before pytest; only the
            # original latch turns actual denials into the final native87.
            raise RuntimeError("sysconfig_prepare_cumulative_refusal_mismatch")

    def prepared(self, prepared, runner, project, startup):
        import struct
        from importlib.machinery import EXTENSION_SUFFIXES

        self.watch_markers = False
        module = sys.modules.get("sysconfig")
        if (module is None or Path(module.__file__) != self.source
                or module.__spec__.origin != str(self.source)
                or type(module.__spec__.loader) is not self.loader_type):
            raise RuntimeError("sysconfig_completed_module_identity_drift")
        for name in ("is_python_build", "get_paths", "get_config_vars", "_expand_vars", "_init_non_posix"):
            function = getattr(module, name)
            if (function.__globals__ is not module.__dict__
                    or function.__code__ != self.codes[(name, function.__code__.co_firstlineno)]):
                raise RuntimeError("sysconfig_completed_function_identity_drift")
        unchanged = self.prefixes == {name: getattr(sys, name) for name in self.prefixes}
        paths = module.get_paths("nt")  # One real API call; all eight independently checked.
        cache = module._CONFIG_VARS
        owned_cache = (module._PROJECT_BASE == str(project) and cache["projectbase"] == str(project)
                       and cache["srcdir"] == str(project))
        mode = self.data["configuration"]["mode"]
        isolated = mode == "isolated"
        abi = _windows_normal_abi(sys.implementation.name, sys.version_info[:2],
                                  sys.implementation.cache_tag, struct.calcsize("P"))
        facts = {"cold_before_prepare": True, "authentic_import_observed": True,
                 "python_build_false": module._PYTHON_BUILD is False, "prefixes_unchanged": unchanged,
                 "nt_scheme_matches": paths == _sysconfig_nt_expectations(self.prefixes),
                 "nt_path_count": len(paths), "owned_projectbase_srcdir": owned_cache,
                 "abi": abi, "extension_suffixes": list(EXTENSION_SUFFIXES),
                 "extension_suffix_cache_matches": cache.get("EXT_SUFFIX") == EXTENSION_SUFFIXES[0],
                 "source_sha256": self.source_bindings["sysconfig.py"][1],
                 "cached_state": "owned_projectbase_srcdir_retained" if isolated else "original_projectbase_srcdir"}
        if self.h6:
            # get_paths above initializes the real cache. Never write this flag
            # or infer initialization merely from a populated _CONFIG_VARS dict.
            facts["config_vars_initialized"] = getattr(module, "_CONFIG_VARS_INITIALIZED", None) is True
        self.data["sysconfig_facts"] = facts
        self.data["env_absent_before_pytest"] = _sysconfig_environment_absent(os.environ)
        expected_markers = {name: {"admitted": int(isolated), "refused": int(not isolated)}
                            for name in ("Setup", "Setup.local")}
        if (not facts["python_build_false"] or not unchanged or not facts["nt_scheme_matches"]
                or abi != ("cp312" if self.h6 else "cp311")
                or list(EXTENSION_SUFFIXES) != ([".cp312-win_amd64.pyd", ".pyd"] if self.h6 else [".cp311-win_amd64.pyd", ".pyd"])
                or (self.h6 and not facts["config_vars_initialized"])
                or not facts["extension_suffix_cache_matches"]
                or (isolated and not owned_cache) or not self.data["env_absent_before_pytest"]
                or self.data["marker_intents"] != expected_markers):
            raise RuntimeError("sysconfig_prepared_configuration_mismatch")
        if (prepared["identity"] != runner.sha(runner.wire(prepared["facts"]))
                or prepared["facts"]["manifest_sha256"] != startup["manifest_sha256"]
                or prepared["facts"]["sources"][ENTRY] != startup["invoker_sha256"]):
            raise RuntimeError("sysconfig_prepared_identity_mismatch")
        self.data["prepare_returned"] = True
        self.data["preparation"] = {"identity": prepared["identity"], "facts": prepared["facts"],
                                     "case_ids": [case["id"] for case in prepared["cases"]],
                                     "request_sha256": [runner.sha(body) for body in prepared["requests"]]}

    def snapshot(self):
        return json.loads(json.dumps(self.data, ensure_ascii=True))

    def finish(self):
        self.phase = "shutdown"
        self.window("shutdown")
        raw = (json.dumps(self.data, ensure_ascii=True, indent=2) + "\n").encode("utf-8")
        if len(raw) > 65536:
            raise RuntimeError("sysconfig_observation_capacity_exceeded")
        with (self.owned / "sysconfig-observation.json").open("xb") as handle:
            handle.write(raw)


_H2_CASE = "79dbf145-52ff-40ea-9988-cbd651993aea"
_H2_INPUTS = ("REVIEWER_V3_H2_CASE", "REVIEWER_V3_H2_CONTROL_SHA256")
_H2_POLICY = {
    "schema": "h2-first-refusal-policy-v1", "case_id": _H2_CASE,
    "normal_sysconfig_policy": _SYSCONFIG_POLICY,
    "refusal_limit": 4, "frame_limit": 12, "metadata_probe_limit": 768,
    "code_serialization_limit": 262144, "relative_source_limit": 512, "node_limit": 1024, "sidecar_limit": 65536,
    "code_digest": "sha256(marshal.dumps(code,4))",
    "text_digest": "sha256(text.encode('utf-8','surrogatepass'))",
    "source_identity": "declared_unverified",
    "public_roots": ["project_tests", "project_evals", "project_src", "stdlib", "site"],
    "stop": "collection_exit_or_session_shouldstop_with_original_current_test_teardown",
    "scope": "first_refusal_diagnostic_not_acceptance",
}


def _h2_configuration(original, *, platform=None):
    found = {name: value for name, value in original.items() if name.upper() in _H2_INPUTS}
    if not found:
        return None
    if (set(found) != set(_H2_INPUTS)
            or any(name.upper() in _SYSCONFIG_INPUTS for name in original)
            or found[_H2_INPUTS[0]] != _H2_CASE):
        raise RuntimeError("h2_configuration_binding_invalid")
    platform = (os.name, sys.implementation.name, sys.version_info[:2]) if platform is None else platform
    base = _sysconfig_configuration({}, platform=platform)
    control = found[_H2_INPUTS[1]]
    if (platform != ("nt", "cpython", (3, 11)) or type(control) is not str or len(control) != 64
            or any(char not in "0123456789abcdef" for char in control)):
        raise RuntimeError("h2_configuration_binding_invalid")
    wire = json.dumps(_H2_POLICY, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    return {**base, "diagnostic_binding": "explicit_h2", "case_id": _H2_CASE,
            "control_sha256": control, "policy_sha256": hashlib.sha256(wire).hexdigest()}


def _h2_text_digest(value):
    if type(value) is not str or len(value) > 8192:
        return None
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()


class _FirstRefusalLocator:
    """One bounded, opt-in observation. Source positions remain declarations.

    No source text, frame locals, target paths or exception messages are saved.
    Physical metadata checks reject links but are not an OS lock against races.
    A shouldstop request is not proof of teardown or session completion.
    """

    def __init__(self, guard, owned, site, configuration):
        self.guard, self.owned = guard, owned
        self.roots = (("project_tests", ROOT / "tests"),
                      ("project_evals", ROOT / "evals/reviewer_comparison_v3"),
                      ("project_src", ROOT / "src/academic_agent"),
                      ("site", site), ("stdlib", Path(sys.base_prefix) / "Lib"))
        self.session, self.node = None, (None, None)
        self.phase, self.node_index = "bootstrap", {}
        self.isfile_code = os.path.isfile.__code__
        self.data = {
            "schema": "h2-first-refusal-v1", "configuration": configuration,
            "executed_entry": None, "manifest_sha256": None, "observer_fault": False,
            "saturated": False, "metadata_probe_count": 0, "stop_requested": False,
            "stop_reason": None, "stop_phase": None, "stop_node_ordinal": None,
            "stop_node_sha256": None, "stop_boundary": None,
            "session_started": False, "collection_started": False, "collection_finished": False,
            "session_finished": False, "unconfigure_seen": False, "unconfigure_dispatch_completed": False,
            "pytest_main_returned": False,
            "receipt_written": False, "collected_count": None, "test_protocols_started": 0,
            "test_protocols_finished": 0, "teardown_reports": 0, "pytest_status": None,
            "refusals": [], "final_refusal_count": 0,
            "scope": "first_refusal_diagnostic_not_acceptance", "source_identity": "declared_unverified",
            "all_descendants_gone": "unavailable",
        }

    def request_stop(self, reason):
        if not self.data["stop_requested"]:
            self.data.update(stop_requested=True, stop_reason=reason, stop_phase=self.phase,
                             stop_node_ordinal=self.node[0], stop_node_sha256=self.node[1])
        if self.session is not None and self.phase in {"test_protocol", "setup", "call", "teardown"}:
            self.session.shouldstop = "h2_first_refusal_diagnostic_stop"
            self.data["stop_boundary"] = "session_shouldstop"

    def fault(self):
        self.data["observer_fault"] = True
        self.request_stop("observer_fault")

    def require_healthy(self):
        if self.data["observer_fault"]:
            raise RuntimeError("h2_observer_fault")

    def public_position(self, filename):
        if type(filename) is not str or len(filename) > 8192:
            return "unknown", None
        candidate = Path(filename)
        for kind, root in self.roots:
            try:
                relative = candidate.relative_to(root)
            except ValueError:
                continue
            parts = relative.parts
            if (not parts or not parts[-1].endswith(".py") or str(root / relative) != filename
                    or len(relative.as_posix()) > _H2_POLICY["relative_source_limit"]
                    or any(not part or part.startswith(".") or part in {".", ".."}
                           or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for char in part)
                           for part in parts)):
                return "unknown", None
            try:
                for path in reversed((candidate, *candidate.parents)):
                    if self.data["metadata_probe_count"] >= _H2_POLICY["metadata_probe_limit"]:
                        return "unknown", None
                    self.data["metadata_probe_count"] += 1
                    info = _REAL_LSTAT(path)
                    attributes = getattr(info, "st_file_attributes", None)
                    if ((sys.platform == "win32" and type(attributes) is not int)
                            or stat.S_ISLNK(info.st_mode) or (attributes is not None and attributes & 0x400)
                            or not (stat.S_ISREG(info.st_mode) if path == candidate else stat.S_ISDIR(info.st_mode))):
                        return "unknown", None
            except OSError:
                return "unknown", None
            return kind, relative.as_posix()
        return "unknown", None

    def frame_record(self, frame, index):
        import marshal

        code = frame.f_code
        kind, relative = self.public_position(code.co_filename)
        serialized = marshal.dumps(code, 4)
        digest = hashlib.sha256(serialized).hexdigest() if len(serialized) <= _H2_POLICY["code_serialization_limit"] else None
        return {"index": index, "source_kind": kind, "relative_source": relative,
                "filename_sha256": _h2_text_digest(code.co_filename),
                "function_sha256": _h2_text_digest(code.co_name), "firstlineno": code.co_firstlineno,
                "line": frame.f_lineno, "code_sha256": digest,
                "source_status": "declared_public_unverified" if relative is not None else "unknown"}

    def record_refusal(self, operation):
        frame = None
        try:
            self.request_stop("first_refusal")
            if len(self.data["refusals"]) >= _H2_POLICY["refusal_limit"]:
                self.data["saturated"] = True
                return
            frame, frames, caller = sys._getframe(1), [], None
            for index in range(_H2_POLICY["frame_limit"]):
                if frame is None:
                    break
                frames.append(self.frame_record(frame, index))
                if frame.f_code is self.isfile_code:
                    caller = index + 1
                frame = frame.f_back
            category = self.guard.violations[-1] if self.guard.violations else None
            if category not in {"read_outside_admitted_sources", "noncanonical_parent_component_forbidden",
                                "real_private_path", "vendor_private_path", "dotenv_file_access",
                                "startup_hook_access", "network_forbidden", "unexpected_subprocess",
                                "owned_profile_link_forbidden", "write_outside_owned_profile"}:
                category = "unknown"
            self.data["refusals"].append({"ordinal": len(self.guard.violations), "category": category,
                "operation": operation if operation in {"probe", "read", "write", "list"} else "other",
                "phase": self.phase, "node_ordinal": self.node[0], "node_sha256": self.node[1],
                "frames": frames, "isfile_caller_frame": caller if caller is not None and caller < len(frames) else None,
                "frame_limit_reached": frame is not None})
        except BaseException:  # Metadata diagnostics must preserve the original Guard exception.
            self.fault()
        finally:
            del frame

    @contextmanager
    def during(self, phase, item=None):
        previous = self.phase, self.node
        try:
            self.phase = phase
            self.node = self.node_index.get(id(item), (None, _h2_text_digest(item.nodeid))) if item is not None else (None, None)
            yield
        finally:
            self.phase, self.node = previous

    def finish(self):
        self.phase = "shutdown"
        self.data["final_refusal_count"] = len(self.guard.violations)
        raw = (json.dumps(self.data, ensure_ascii=True, indent=2) + "\n").encode()
        if len(raw) > _H2_POLICY["sidecar_limit"]:
            raise RuntimeError("h2_sidecar_capacity_exceeded")
        with (self.owned / "first-refusal-observation.json").open("xb") as handle:
            handle.write(raw)


def _h2_pytest_plugin(locator, pytest):
    """Observe the actual lifecycle; requests never replace current teardown."""
    class Plugin:
        def pytest_sessionstart(self, session):
            locator.session = session
            locator.data["session_started"] = True

        @pytest.hookimpl(wrapper=True, tryfirst=True)
        def pytest_collection(self, session):
            locator.data["collection_started"] = True
            with locator.during("collection"):
                if locator.data["stop_requested"]:
                    locator.data["stop_boundary"] = "before_collection_exit"
                    pytest.exit("h2_first_refusal_diagnostic_stop", returncode=2)
                return (yield)

        @pytest.hookimpl(trylast=True)
        def pytest_collection_modifyitems(self, items):
            locator.data["collected_count"] = len(items)
            if len(items) > _H2_POLICY["node_limit"]:
                locator.fault()
                return
            locator.node_index = {id(item): (index, _h2_text_digest(item.nodeid))
                                  for index, item in enumerate(items, 1)}

        @pytest.hookimpl(trylast=True)
        def pytest_collection_finish(self):
            locator.data["collection_finished"] = True
            if locator.data["stop_requested"]:
                locator.data["stop_boundary"] = "collection_finish_exit"
                pytest.exit("h2_first_refusal_diagnostic_stop", returncode=2)

        @pytest.hookimpl(wrapper=True, tryfirst=True)
        def pytest_runtest_protocol(self, item, nextitem):
            locator.data["test_protocols_started"] += 1
            with locator.during("test_protocol", item):
                result = yield
                locator.data["test_protocols_finished"] += 1
                return result

        @pytest.hookimpl(wrapper=True, tryfirst=True)
        def pytest_runtest_setup(self, item):
            with locator.during("setup", item):
                return (yield)

        @pytest.hookimpl(wrapper=True, tryfirst=True)
        def pytest_runtest_call(self, item):
            with locator.during("call", item):
                return (yield)

        @pytest.hookimpl(wrapper=True, tryfirst=True)
        def pytest_runtest_teardown(self, item, nextitem):
            with locator.during("teardown", item):
                return (yield)

        def pytest_runtest_logreport(self, report):
            if report.when == "teardown":
                locator.data["teardown_reports"] += 1

        @pytest.hookimpl(wrapper=True, tryfirst=True)
        def pytest_sessionfinish(self, session, exitstatus):
            with locator.during("session_finish"):
                result = yield
                locator.data["session_finished"] = True
                return result

        @pytest.hookimpl(wrapper=True, tryfirst=True)
        def pytest_unconfigure(self):
            # Enter before later-registered ordinary hooks, including logging.
            # Keep this phase after dispatch: Config closes its cleanup stack
            # afterward, before main takes ownership of receipt finalization.
            locator.phase = "unconfigure"
            locator.data["unconfigure_seen"] = True
            result = yield
            locator.data["unconfigure_dispatch_completed"] = True
            return result

    return Plugin()


_H3_INPUTS = ("REVIEWER_V3_H3_CASE", "REVIEWER_V3_H3_CONTROL_SHA256")
_H3_CASES = {"10c852e8-dcf8-4f9e-b162-79460ab6e48f": "missing-distro",
             "b7e072d8-2e5b-4aff-be32-47652f6166ef": "isolated-distro"}
_DISTRO_SOURCES = {
    "package": ("__init__.py", 981, "d9f1e317e49f80fbe3c8d67588787fc23a96751fd8a393831f0642d232c13e17"),
    "module": ("distro.py", 49430, "5ea6de7da7008434f8cebfedae76c0d79798f2f74ae064e08609af506ac433fe"),
}
_H3_POLICY = {"schema": "h3-distro-profile-policy-v1", "normal_sysconfig_policy": _SYSCONFIG_POLICY,
              "cases": _H3_CASES, "sysconfig_mode": "isolated", "distro_sources": _DISTRO_SOURCES,
              "environment_keys": ["UNIXCONFDIR", "UNIXUSRLIBDIR"],
              "directory_leaves": ["distro-etc", "distro-usr-lib"], "platform": "nt_cpython_3_11_only",
              "sidecar_cap": 8192, "probe_stack_limit": 8,
              "scope": "normal_test_distro_profile_not_host_accuracy"}


def _distro_profile_target():
    return (os.name == "nt" or sys.platform == "linux") and sys.implementation.name == "cpython" and sys.version_info[:2] in {(3, 11), (3, 12)}


def _distro_profile_dirs(paths):
    base = paths["work"].parent
    return {"UNIXCONFDIR": base / "distro-etc", "UNIXUSRLIBDIR": base / "distro-usr-lib"}


def _distro_require_cold(modules):
    if any(name == "distro" or name.startswith("distro.") for name in modules):
        raise RuntimeError("distro_profile_requires_cold_package_and_submodules")


def _h3_configuration(original, *, platform=None):
    found = {name: value for name, value in original.items() if name.upper() in _H3_INPUTS}
    if not found:
        return None
    platform = (os.name, sys.implementation.name, sys.version_info[:2]) if platform is None else platform
    if (set(found) != set(_H3_INPUTS) or platform != ("nt", "cpython", (3, 11))
            or any(name.upper() in (*_SYSCONFIG_INPUTS, *_H2_INPUTS) for name in original)
            or found[_H3_INPUTS[0]] not in _H3_CASES):
        raise RuntimeError("h3_configuration_binding_invalid")
    control = found[_H3_INPUTS[1]]
    if type(control) is not str or len(control) != 64 or any(char not in "0123456789abcdef" for char in control):
        raise RuntimeError("h3_configuration_binding_invalid")
    base = _sysconfig_configuration({}, platform=platform)
    wire = json.dumps(_H3_POLICY, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    return {**base, "mode": "isolated", "diagnostic_binding": "explicit_h3", "case_id": found[_H3_INPUTS[0]],
            "control_sha256": control, "policy_sha256": hashlib.sha256(wire).hexdigest()}


_NT312_SYSCONFIG_SOURCES = {
    "sysconfig.py": (32561, "695bd1c5e8579d7ff822ee08ff52a3a9f6734579ae6eda65826756a3f8cd1329"),
    "subprocess.py": (91441, "f11c63146e12e6317225de2a3cdeaa75fd51d2751c2530390ffefcb0f2bf9a61"),
}
_NT312_DISTRO_SOURCES = {
    "package": ("__init__.py", 981, "d9f1e317e49f80fbe3c8d67588787fc23a96751fd8a393831f0642d232c13e17"),
    "module": ("distro.py", 49430, "5ea6de7da7008434f8cebfedae76c0d79798f2f74ae064e08609af506ac433fe"),
}
_NT312_PROFILE = {
    "runtime": "nt_cpython_3_12_9", "cache_tag": "cpython-312", "pointer_bytes": 8,
    "abi": "cp312", "extension_suffixes": [".cp312-win_amd64.pyd", ".pyd"],
    "sysconfig_sources": _NT312_SYSCONFIG_SOURCES, "distro_sources": _NT312_DISTRO_SOURCES,
    "execute_child_firstline": 1438, "isfile": "installed_guarded_isfile_identity",
    "config_vars_initialized": "observe_true_after_real_get_paths_never_set",
}
_H6_INPUTS = ("REVIEWER_V3_H6_CASE", "REVIEWER_V3_H6_CONTROL_SHA256")
_H6_CASES = {"8788c0ac-3e50-4e99-8a0e-3e6767ad97d0": "missing-project",
             "b0d14827-1950-4e42-8e84-c98a954bf28f": "missing-usr-lib",
             "4933db77-a42f-4e76-b6ce-bb9d71ff7a9e": "isolated-distro"}
_H6_POLICY = {
    "schema": "h6-nt312-profile-policy-v1", "normal_policy": _NT312_DEFAULT_POLICY,
    "inputs": _H6_INPUTS, "cases": _H6_CASES, "diagnostic_profile": _NT312_PROFILE,
    "probe_stack_limit": 8, "distro_sidecar_cap": 8192, "sysconfig_sidecar_cap": 65536,
    "negative_project": "first_genuine_Setup_refusal_aborts_prepare_finally_restores_environment",
    "negative_distro": "owned_etc_admitted_then_missing_usr_lib_refused_aborts_import",
    "exit_ownership": "unchanged_original_cumulative_latch", "pytest": "one_original_fixed_529_call",
    "scope": "normal_test_profiles_not_host_configuration_or_cold_privacy_acceptance",
}


def _nt312_profile_target(*, platform=None):
    platform = (os.name, sys.implementation.name, sys.version_info[:2]) if platform is None else platform
    return platform == ("nt", "cpython", (3, 12))


def _nt312_observer_family(configuration):
    return configuration["diagnostic_binding"] in {"explicit_h6", "explicit_ff"}


_FF_INPUTS = ("REVIEWER_V3_FF_CASE", "REVIEWER_V3_FF_CONTROL_SHA256")
_FF_CASE = "e0591d8f-bb7d-4ba6-a41a-fd62d30c87e3"
_FF_PHASES = ("guard_registration", "dependency_startup", "prepare", "prepare_scope_exit", "pytest_import",
              "distro_import", "pytest_main", "receipt_finalization", "shutdown")
_FF_EXCEPTIONS = ((AttributeError, "attribute_error"), (TypeError, "type_error"),
    (KeyError, "key_error"), (IndexError, "index_error"), (ValueError, "value_error"),
    (RuntimeError, "runtime_error"), (RecursionError, "recursion_error"),
    (PermissionError, "permission_error"), (OSError, "os_error"), (MemoryError, "memory_error"),
    (ImportError, "import_error"), (NameError, "name_error"),
    (SystemExit, "system_exit"), (KeyboardInterrupt, "keyboard_interrupt"))
_FF_POLICY = {
    "schema": "first-observer-fault-policy-v1", "case_id": _FF_CASE, "inputs": _FF_INPUTS,
    "diagnostic_profile": _NT312_PROFILE, "mode": "missing-control",
    "components": ["sysconfig_path", "distro_probe"], "phases": _FF_PHASES,
    "exceptions": [label for _cls, label in _FF_EXCEPTIONS] + ["other"],
    "capture": "one_exact_dict_pop_first_arrival_unavailable_then_complete_publish_no_retry",
    "privacy": "fixed_enums_only_no_exception_representation_or_retained_exception",
    "prepare": "original_call_bare_reraise_unconditional_return_stop_before_pytest",
    "probe_stack_limit": 8, "distro_sidecar_cap": 8192, "sysconfig_sidecar_cap": 65536,
    "scope": "diagnostic_fault_evidence_not_root_cause_fix_or_negative_acceptance",
}


def _ff_configuration(original, *, platform=None):
    found = {name: value for name, value in original.items() if name.upper() in _FF_INPUTS}
    if not found:
        return None
    if (set(found) != set(_FF_INPUTS) or not _nt312_profile_target(platform=platform)
            or any(name.upper() in (*_SYSCONFIG_INPUTS, *_H2_INPUTS, *_H3_INPUTS, *_H6_INPUTS)
                   for name in original)
            or type(found[_FF_INPUTS[0]]) is not str or found[_FF_INPUTS[0]] != _FF_CASE):
        raise RuntimeError("ff_configuration_binding_invalid")
    control = found[_FF_INPUTS[1]]
    if type(control) is not str or len(control) != 64 or any(char not in "0123456789abcdef" for char in control):
        raise RuntimeError("ff_configuration_binding_invalid")
    base = _sysconfig_configuration({}, platform=platform)
    wire = json.dumps(_FF_POLICY, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    return {**base, "mode": "missing-control", "diagnostic_binding": "explicit_ff", "case_id": _FF_CASE,
            "control_sha256": control, "policy_sha256": hashlib.sha256(wire).hexdigest()}


def _ff_fault_record(component, phase, exc):
    if (type(component) is not str or component not in {"sysconfig_path", "distro_probe"}
            or type(phase) is not str or phase not in _FF_PHASES):
        raise ValueError("ff_capture_enum_invalid")
    label = next((label for cls, label in _FF_EXCEPTIONS if type(exc) is cls), "other")
    return {"status": "captured", "first": {"component": component, "phase": phase, "exception": label}}


class _FirstObserverFault:
    """First arrival at the capture point, never global exception occurrence time."""

    def __init__(self, data):
        if type(data) is not dict:
            raise TypeError("ff_builtin_record_owner_required")
        self.data, self._claim = data, {"first": True}
        data["ff_first_observer_fault"] = {"status": "not_observed", "first": None}

    def capture(self, component, phase, exc):
        # Exact builtin pop claims once before fallible classification. A failed
        # first attempt is permanently unavailable, never repaired by a later one.
        if not dict.pop(self._claim, "first", False):
            return
        self.data["ff_first_observer_fault"] = {"status": "unavailable", "first": None}
        try:
            record = _ff_fault_record(component, phase, exc)
            self.data["ff_first_observer_fault"] = record
        except BaseException:  # Capture must never replace the original Guard result.
            pass


def _capture_first_observer_fault(observer, component, phase, exc):
    try:
        slot = getattr(observer, "first_fault", None)
        if slot is not None:
            if component == "sysconfig_path":
                phase = getattr(observer, "phase", None)
            slot.capture(component, phase, exc)
    except BaseException:  # Preserve the admitted return or identical original refusal.
        pass


def _h6_configuration(original, *, platform=None):
    found = {name: value for name, value in original.items() if name.upper() in _H6_INPUTS}
    if not found:
        return None
    if (set(found) != set(_H6_INPUTS) or not _nt312_profile_target(platform=platform)
            or any(name.upper() in (*_SYSCONFIG_INPUTS, *_H2_INPUTS, *_H3_INPUTS) for name in original)
            or found[_H6_INPUTS[0]] not in _H6_CASES):
        raise RuntimeError("h6_configuration_binding_invalid")
    control = found[_H6_INPUTS[1]]
    if type(control) is not str or len(control) != 64 or any(char not in "0123456789abcdef" for char in control):
        raise RuntimeError("h6_configuration_binding_invalid")
    base = _sysconfig_configuration({}, platform=platform)
    wire = json.dumps(_H6_POLICY, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    mode = "missing-control" if _H6_CASES[found[_H6_INPUTS[0]]] == "missing-project" else "isolated"
    return {**base, "mode": mode, "diagnostic_binding": "explicit_h6", "case_id": found[_H6_INPUTS[0]],
            "control_sha256": control, "policy_sha256": hashlib.sha256(wire).hexdigest()}


def _nt312_profile_runtime(version, cache_tag, pointer_bytes, extension_suffixes, *, platform=None):
    """Exact diagnostic target only; the default series policy does not use it."""
    if (not _nt312_profile_target(platform=platform) or version != (3, 12, 9)
            or cache_tag != _NT312_PROFILE["cache_tag"] or pointer_bytes != _NT312_PROFILE["pointer_bytes"]
            or extension_suffixes != _NT312_PROFILE["extension_suffixes"]):
        raise RuntimeError("nt312_profile_runtime_identity_drift")
    return _NT312_PROFILE["abi"]


def _nt312_isfile_identity(guarded_isfile):
    """Bind the object returned by the real installer, not a builtin's __code__."""
    from types import FunctionType

    codes = [code for code in _install_nt312_path_guard.__code__.co_consts
             if type(code) is type(_install_nt312_path_guard.__code__) and code.co_name == "guarded_isfile"]
    if (len(codes) != 1 or type(guarded_isfile) is not FunctionType
            or os.path.isfile is not guarded_isfile or guarded_isfile.__globals__ is not globals()
            or guarded_isfile.__code__ is not codes[0]):
        raise RuntimeError("nt312_profile_isfile_identity_drift")
    return guarded_isfile.__code__


def _nt312_profile_sources(site, guarded_isfile):
    """Compile four hash-bound public references without executing vendor source."""
    import struct
    from importlib.machinery import EXTENSION_SUFFIXES

    abi = _nt312_profile_runtime(sys.version_info[:3], sys.implementation.cache_tag,
                                 struct.calcsize("P"), list(EXTENSION_SUFFIXES))
    if sys.platform != "win32" or sys.flags.optimize:
        raise RuntimeError("nt312_profile_runtime_identity_drift")
    _nt312_isfile_identity(guarded_isfile)
    result = {"abi": abi, "distro": {}}
    for filename, binding in _NT312_SYSCONFIG_SOURCES.items():
        source = Path(sys.base_prefix) / "Lib" / filename
        _i18n_physical_path(str(source), windows=True)
        result[filename.removesuffix(".py")] = _sysconfig_reference_codes(source, *binding)
    for name, (filename, size, digest) in _NT312_DISTRO_SOURCES.items():
        source = site / "distro" / filename
        _i18n_physical_path(str(source), windows=True)
        result["distro"][name] = _sysconfig_reference_codes(source, size, digest)
    return result


class _DistroProfileObservation:
    """Observe one real cold import; empty owned release dirs are not host data.

    The reference source is compiled, never executed or imported here. Original
    Guard decisions run first; two isfile intents do not claim successful stats.
    Cold children retain their original environment filter and audit methods.
    """

    def __init__(self, guard, owned, paths, site, configuration, *, profile_sources=None, guarded_isfile=None,
                 first_fault=None):
        from importlib.machinery import SourceFileLoader

        self.guard, self.owned, self.configuration = guard, owned, configuration
        self.h6 = configuration["diagnostic_binding"] == "explicit_h6"
        self.ff = configuration["diagnostic_binding"] == "explicit_ff"
        self.nt312 = _nt312_observer_family(configuration)
        self.first_fault = first_fault if self.ff else None
        self.profile = "missing-project" if self.ff else (_H6_CASES if self.h6 else _H3_CASES)[configuration["case_id"]]
        bindings = _NT312_DISTRO_SOURCES if self.nt312 else _DISTRO_SOURCES
        self.dirs = _distro_profile_dirs(paths)
        self.source_paths = {name: site / "distro" / binding[0] for name, binding in bindings.items()}
        self.loader_type = SourceFileLoader
        self.isfile_code = _nt312_isfile_identity(guarded_isfile) if self.nt312 else os.path.isfile.__code__
        _distro_require_cold(sys.modules)
        if self.nt312:
            if profile_sources is None:
                raise RuntimeError("nt312_profile_sources_required")
            references = profile_sources["distro"]
        else:
            references = {}
            for name, (_relative, size, digest) in bindings.items():
                _i18n_physical_path(str(self.source_paths[name]), windows=True)
                references[name] = _sysconfig_reference_codes(self.source_paths[name], size, digest)
        self.module_code = references["module"][("<module>", 1)]
        self.constructor_code = references["module"][("__init__", 667)]
        for path in self.dirs.values():
            _no_owned_links(path, owned)
            _no_discovery_links(str(path), windows=True)
            if any(path.iterdir()):
                raise RuntimeError("distro_profile_directory_not_empty")
        configured = {key: value for key, value in os.environ.items() if key.upper() in self.dirs}
        expected = {} if self.profile == "missing-distro" else {name: str(path) for name, path in self.dirs.items()}
        if self.profile == "missing-usr-lib":
            del expected["UNIXUSRLIBDIR"]
        if configured != expected:
            raise RuntimeError("distro_environment_does_not_match_case")
        self.data = {"schema": "h6-distro-profile-v1" if self.h6 else "h3-distro-profile-v1", "configuration": configuration, "profile": self.profile,
            "executed_entry": None, "manifest_sha256": None,
            "source_bindings": {name: {"bytes": binding[1], "sha256": binding[2]} for name, binding in bindings.items()},
            "directories_empty_initial": True, "environment_matches_case": True,
            "cold_before_prepare": False, "cold_before_dispatch": False,
            "module_body_code_observed": False, "constructor_code_observed": False,
            "import_verified": False, "import_globals_match_case": False, "instance_paths_match_case": False,
            "probe_intents": {name: {"admitted": 0, "refused": 0} for name in ("etc", "usr_lib")},
            "observer_fault": False, "pytest_started": False, "receipt_written": False,
            "negative_stopped_before_pytest": False, "final_refusal_count": 0,
            "scope": "normal_test_distro_profile_not_host_accuracy",
            "cold_delivery": "original_NORMAL_MODEL_FLAGS_audit", "child_self_reported_environment": None}
        if self.ff:
            self.data["schema"] = "ff-distro-profile-v1"
        if self.nt312:
            self.data["isfile_observer"] = "installed_guarded_isfile_identity"

    def require_cold(self, stage):
        if stage not in {"before_prepare", "before_dispatch"}:
            raise RuntimeError("distro_cold_stage_invalid")
        _distro_require_cold(sys.modules)
        self.data["cold_" + stage] = True

    def module_identity(self, name, kind):
        module = sys.modules.get(name)
        if (type(module) is not type(sys) or module.__file__ != str(self.source_paths[kind])
                or module.__spec__.origin != str(self.source_paths[kind])
                or module.__spec__.name != name or type(module.__spec__.loader) is not self.loader_type):
            raise RuntimeError("distro_loaded_module_origin_mismatch")
        return module

    def record_probe(self, raw, operation, *, refused, phase=None):
        frame = None
        try:
            module = sys.modules.get("distro.distro")
            if operation != "probe" or type(raw) is not str or module is None or "_distro" in vars(module):
                return
            frame, constructor, module_body, isfile = sys._getframe(1), False, False, False
            for _ in range(_H3_POLICY["probe_stack_limit"]):
                if frame is None:
                    break
                if frame.f_globals is module.__dict__ and frame.f_code.co_filename == str(self.source_paths["module"]):
                    constructor = constructor or frame.f_code == self.constructor_code
                    module_body = module_body or frame.f_code == self.module_code
                isfile = isfile or frame.f_code is self.isfile_code
                frame = frame.f_back
            if not (constructor and module_body and isfile):
                return
            self.module_identity("distro.distro", "module")
            for label, variable in (("etc", "_UNIXCONFDIR"), ("usr_lib", "_UNIXUSRLIBDIR")):
                base = vars(module).get(variable)
                if type(base) is str and raw == os.path.join(base, "os-release"):
                    self.data["probe_intents"][label]["refused" if refused else "admitted"] += 1
                    self.data["module_body_code_observed"] = True
                    self.data["constructor_code_observed"] = True
        except BaseException as exc:  # Observation cannot replace original Guard return/PermissionError.
            self.data["observer_fault"] = True
            _capture_first_observer_fault(self, "distro_probe", phase, exc)
        finally:
            del frame

    def verify_import(self):
        package = self.module_identity("distro", "package")
        module = self.module_identity("distro.distro", "module")
        cls = module.LinuxDistribution
        if (package.LinuxDistribution is not cls or cls.__init__.__globals__ is not module.__dict__
                or cls.__init__.__code__ != self.constructor_code or type(module._distro) is not cls):
            raise RuntimeError("distro_constructor_identity_mismatch")
        expected = ({"UNIXCONFDIR": "/etc", "UNIXUSRLIBDIR": "/usr/lib"} if self.profile == "missing-distro"
                    else {name: str(path) for name, path in self.dirs.items()})
        self.data["import_globals_match_case"] = (module._UNIXCONFDIR == expected["UNIXCONFDIR"]
                                                  and module._UNIXUSRLIBDIR == expected["UNIXUSRLIBDIR"])
        instance = module._distro
        self.data["instance_paths_match_case"] = (instance.root_dir is None and instance.etc_dir == expected["UNIXCONFDIR"]
            and instance.usr_lib_dir == expected["UNIXUSRLIBDIR"]
            and instance.os_release_file == os.path.join(expected["UNIXCONFDIR"], "os-release"))
        admitted = int(self.profile == "isolated-distro")
        if (self.data["observer_fault"] or not self.data["module_body_code_observed"]
                or not self.data["constructor_code_observed"] or not self.data["import_globals_match_case"]
                or not self.data["instance_paths_match_case"] or self.data["probe_intents"] != {
                    name: {"admitted": admitted, "refused": 1 - admitted} for name in ("etc", "usr_lib")}):
            raise RuntimeError("distro_import_profile_mismatch")
        self.data["import_verified"] = True

    def finish(self):
        self.data["final_refusal_count"] = len(self.guard.violations)
        raw = (json.dumps(self.data, ensure_ascii=True, indent=2) + "\n").encode()
        if len(raw) > _H3_POLICY["sidecar_cap"]:
            raise RuntimeError("distro_profile_sidecar_capacity")
        with (self.owned / "distro-profile-observation.json").open("xb") as handle:
            handle.write(raw)


def main():
    if not _fixed_invocation(sys.argv, sys.flags.no_site, sys.flags.dont_write_bytecode,
                             sys.flags.ignore_environment):
        raise SystemExit("fixed_test_bootstrap_required")
    ff_configuration = _ff_configuration(os.environ)
    h6_configuration = _h6_configuration(os.environ)
    sysconfig_configuration = ff_configuration or h6_configuration or _sysconfig_configuration(os.environ)
    h2_configuration = _h2_configuration(os.environ)
    if h2_configuration is not None:
        raise SystemExit("h2_diagnostic_case_closed")
    h3_configuration = _h3_configuration(os.environ)
    if h3_configuration is not None:
        sysconfig_configuration = h3_configuration
    environment, site, cfg_sha = _verified_environment()
    original_home = Path.home()
    private = [ROOT / ".env", original_home / ".config" / "crewai",
               original_home / ".local" / "share" / "crewai"]
    for name in ("LOCALAPPDATA", "APPDATA"):
        if os.environ.get(name):
            private.append(Path(os.environ[name]) / "CrewAI")
    owned, paths = _owned_profile()
    _test_environment(paths)
    if h3_configuration is not None and _H3_CASES[h3_configuration["case_id"]] == "missing-distro":
        for name in tuple(os.environ):
            if name.upper() in {"UNIXCONFDIR", "UNIXUSRLIBDIR"}:
                del os.environ[name]
    if h6_configuration is not None and _H6_CASES[h6_configuration["case_id"]] == "missing-usr-lib":
        # Keep the owned etc directory: this control must admit that first
        # genuine probe, then refuse the unconfigured usr/lib fallback.
        for name in tuple(os.environ):
            if name.upper() == "UNIXUSRLIBDIR":
                del os.environ[name]
    canonical = _preload_canonical()
    public = [ROOT / name for name in ("src", "api", "ui", "web", "tests", "docs", ".github",
                                      "evals/reviewer_comparison_v3", "evals/reviewer_output_contract_v1")]
    public += [ROOT / "pyproject.toml", ROOT / "uv.lock", site, environment / "pyvenv.cfg", *_STDLIB_PATHS]
    guard = Guard(owned, public, private, windows=sys.platform == "win32",
                  discovery=(ROOT, ROOT / "evals"), normal_i18n_site=site)
    cold_script, inherited_names = _cold_script_and_names()
    path_wrappers = _install_io_guard(guard, owned, cold_script)
    _install_cold_envelope(cold_script, guard)

    def at_exit():
        if guard.violations:
            try:
                with (owned / "shutdown-refusals.json").open("x", encoding="utf-8") as handle:
                    json.dump({"violations": guard.violations, "status": 87}, handle)
                sys.stdout.flush()
                sys.stderr.flush()
            finally:
                # Even a failed refusal-log write/flush cannot erase the fault.
                os._exit(87)

    atexit.register(at_exit)
    observation = None
    locator = None
    distro_profile = None
    observer_arguments = {}
    if h6_configuration is not None or ff_configuration is not None:
        if path_wrappers is None:
            raise RuntimeError("nt312_profile_path_guard_required")
        guarded_isfile = path_wrappers[0]
        observer_arguments = {"profile_sources": _nt312_profile_sources(site, guarded_isfile),
                              "guarded_isfile": guarded_isfile}
    if sysconfig_configuration["diagnostic_binding"] in {"explicit_h1", "explicit_h2", "explicit_h3", "explicit_h6", "explicit_ff"}:
        observation = _SysconfigObservation(guard, owned, cold_script, sysconfig_configuration, **observer_arguments)
        # Reverse atexit ordering: subsequently registered dependency cleanup,
        # then this bounded observation, then the unchanged refusal latch.
        atexit.register(observation.finish)
        if h2_configuration is not None:
            locator = _FirstRefusalLocator(guard, owned, site, h2_configuration)
            observation.h2_locator = locator
            atexit.register(locator.finish)
        if h3_configuration is not None or h6_configuration is not None or ff_configuration is not None:
            if ff_configuration is not None:
                observer_arguments["first_fault"] = observation.first_fault
            distro_profile = _DistroProfileObservation(guard, owned, paths, site,
                                                       ff_configuration or h6_configuration or h3_configuration, **observer_arguments)
            observation.h3_profile = distro_profile
            atexit.register(distro_profile.finish)
    sys.path[:] = [*_STDLIB_PATHS, str(site), str(ROOT / "src"), str(ROOT)]
    startup = {"scope": "test_only_owned_profile_not_native", "python": sys.version,
               "executable": sys.executable, "prefix": sys.prefix, "venv": str(environment),
               "site_packages": str(site), "pyvenv_cfg_sha256": cfg_sha,
               "ignore_environment": sys.flags.ignore_environment, "no_site": sys.flags.no_site,
               "dont_write_bytecode": sys.flags.dont_write_bytecode,
               "invoker_sha256": hashlib.sha256((ROOT / ENTRY).read_bytes()).hexdigest(),
               "manifest_sha256": hashlib.sha256((ROOT / "evals/reviewer_comparison_v3/manifest.json").read_bytes()).hexdigest(),
               "owned_profile": str(owned), "check_files": list(CHECK_FILES),
               "canonical_bootstrap": canonical}
    startup["sysconfig_configuration"] = sysconfig_configuration
    startup["executed_entry"] = {"bytes": (ROOT / ENTRY).stat().st_size,
                                 "sha256": startup["invoker_sha256"]}
    if observation is not None:
        observation.data["executed_entry"] = startup["executed_entry"]
    if locator is not None:
        locator.data["executed_entry"] = startup["executed_entry"]
        locator.data["manifest_sha256"] = startup["manifest_sha256"]
    if distro_profile is not None:
        distro_profile.data["executed_entry"] = startup["executed_entry"]
        distro_profile.data["manifest_sha256"] = startup["manifest_sha256"]
    with (owned / "bootstrap.json").open("x", encoding="utf-8") as handle:
        json.dump(startup, handle, ensure_ascii=True, indent=2)
    print("TEST_STARTUP " + json.dumps(startup, ensure_ascii=True), flush=True)
    if observation is not None:
        observation.phase = "dependency_startup"
    if locator is not None:
        locator.phase = "dependency_startup"
    from evals.reviewer_comparison_v3.linux_sysconfig_profile import install
    with install(owned, _STDLIB_PATHS) as linux_profile:
        normal_profile, normal_lease = _normal_dependency_startup(site, guard)
        appdirs_profile = _normal_model_shims(paths, guard)
        from evals.reviewer_comparison_v3 import runner

        if observation is not None:
            observation.window("dependency_startup")
            observation.phase, observation.watch_markers = "prepare", True
        project = _sysconfig_project(owned) if sysconfig_configuration["policy_applicable"] else None
        if locator is not None:
            locator.phase = "prepare"
        if observation is not None:
            observation.require_prepare_ledger("before")
        if distro_profile is not None:
            distro_profile.require_cold("before_prepare")
        try:
            with _normal_sysconfig_scope(project, sysconfig_configuration):
                try:
                    prepared = runner.prepare()  # Unpatched identity, never a key/native mode.
                except PermissionError:
                    if ff_configuration is not None:
                        observation.data["ff_prepare_outcome"] = "permission_error"
                    raise
                except BaseException:  # Record only the outcome; preserve the original failure.
                    if ff_configuration is not None:
                        observation.data["ff_prepare_outcome"] = "other_failure"
                    raise
                else:
                    if ff_configuration is not None:
                        observation.data["ff_prepare_outcome"] = "returned"
                        observation.data["prepare_returned"] = True
        except PermissionError:
            if ff_configuration is not None:
                observation.data["negative_stopped_before_pytest"] = True
            if h6_configuration is not None and _H6_CASES[h6_configuration["case_id"]] == "missing-project":
                observation.data["negative_stopped_before_pytest"] = (
                    guard.violations == ["read_outside_admitted_sources"] and not observation.data["observer_fault"]
                    and observation.data["marker_intents"] == {
                        "Setup": {"admitted": 0, "refused": 1}, "Setup.local": {"admitted": 0, "refused": 0}})
            # The real installed predicate propagates the original refusal. Do not
            # manufacture a missing marker, continue prepare, or synthesize exit87.
            raise
        finally:
            if ff_configuration is not None:
                observation.phase = "prepare_scope_exit"
            if h6_configuration is not None or ff_configuration is not None:
                observation.data["prepare_scope_exited"] = True
                observation.data["env_absent_after_prepare_exit"] = _sysconfig_environment_absent(os.environ)
                observation.window("prepare_scope_exit")
    if ff_configuration is not None:
        raise RuntimeError("ff_diagnostic_stop_before_pytest")
    if h6_configuration is not None and _H6_CASES[h6_configuration["case_id"]] == "missing-project":
        raise RuntimeError("nt312_missing_project_expected_refusal_not_observed")
    if sysconfig_configuration["policy_applicable"] and not _sysconfig_environment_absent(os.environ):
        raise RuntimeError("sysconfig_environment_not_restored_before_pytest")
    if observation is not None:
        observation.window("prepare")
        observation.require_prepare_ledger("after")
        observation.prepared(prepared, runner, project, startup)
        observation.require_prepare_ledger("after")
        if sysconfig_configuration["mode"] == "missing-control":
            if len(guard.violations) != 2:
                raise RuntimeError("sysconfig_missing_control_refusal_count_mismatch")
            # No pytest import or fabricated exit87. The unchanged original
            # atexit latch owns the native refusal exit after this return.
            return guard.finish_status(0)
        observation.phase = "pytest_import"
    if distro_profile is not None:
        distro_profile.require_cold("before_dispatch")
        if distro_profile.profile == "missing-usr-lib":
            import importlib

            observation.phase = "distro_import"
            try:
                importlib.import_module("distro")
            except PermissionError:
                distro_profile.data["negative_stopped_before_pytest"] = (
                    guard.violations == ["read_outside_admitted_sources"]
                    and not distro_profile.data["observer_fault"]
                    and distro_profile.data["probe_intents"] == {
                        "etc": {"admitted": 1, "refused": 0}, "usr_lib": {"admitted": 0, "refused": 1}})
                raise  # The original Guard refusal/latch remains the only exit87 authority.
            raise RuntimeError("nt312_missing_usr_lib_expected_refusal_not_observed")
        if distro_profile.profile == "missing-distro":
            import importlib

            observation.phase = "distro_import"
            importlib.import_module("distro")
            distro_profile.verify_import()
            observation.window("distro_import")
            if guard.violations != ["read_outside_admitted_sources"] * 2:
                raise RuntimeError("distro_negative_refusal_mismatch")
            distro_profile.data["negative_stopped_before_pytest"] = True
            return guard.finish_status(0)  # The unchanged original latch owns native87.
    if locator is not None:
        locator.phase = "pytest_import"
    import pytest
    if distro_profile is not None:
        distro_profile.data["pytest_started"] = True
    if observation is not None:
        observation.data["pytest_started"] = True
        observation.window("pytest_import")

    class Receipt:
        def __init__(self):
            self.collected, self.results = {}, []
            self.model_file = None

        def pytest_collection_modifyitems(self, items):
            for item in items:
                lane = ("inherited" if item.originalname in inherited_names else "new_v3") if (
                    item.path.name == "reviewer_comparison_v3_checks.py") else "common"
                self.collected[item.nodeid] = lane

        def pytest_collection_finish(self):
            module = sys.modules.get("academic_agent.evidence")
            if (module is not None and Path(module.__file__) == ROOT / "src/academic_agent/evidence.py"
                    and module.ReviewerCorrectionPlan.__module__ == "academic_agent.evidence"):
                self.model_file = str(module.__file__)

        def pytest_runtest_logreport(self, report):
            self.results.append({"nodeid": report.nodeid, "phase": report.when, "outcome": report.outcome})

    receipt = Receipt()
    if observation is not None:
        observation.phase = "pytest_main"
    with _pytest_bookmarks(paths, site, guard) as bookmarks:
        status = pytest.main(_pytest_arguments(paths), plugins=[receipt])
    if observation is not None:
        observation.window("pytest_main")
        observation.phase = "receipt_finalization"
    if locator is not None:
        locator.phase = "receipt_finalization"
    if distro_profile is not None:
        distro_profile.verify_import()
    counts = Counter((receipt.collected[item["nodeid"]], item["outcome"]) for item in receipt.results
                     if item["phase"] == "call")
    if (Counter(receipt.collected.values())["inherited"] != 278
            or Counter(receipt.collected.values())["common"] != 35 or receipt.model_file is None):
        status = int(status) or 1
    result = {"pytest_status": int(status), "status": guard.finish_status(status),
              "python": sys.version, "executable": sys.executable, "prefix": sys.prefix,
              "venv": str(environment), "site_packages": str(site), "pyvenv_cfg_sha256": cfg_sha,
              "invoker_sha256": hashlib.sha256((ROOT / ENTRY).read_bytes()).hexdigest(),
              "preparation_identity": prepared["identity"], "manifest_sha256": prepared["facts"]["manifest_sha256"],
              "normal_model_source": receipt.model_file, "extracted_runtime": prepared["facts"]["helper_runtime"],
              "collected": dict(Counter(receipt.collected.values())),
              "executed": {"|".join(key): value for key, value in counts.items()},
              "results": receipt.results, "violations": list(guard.violations),
              "scope": "owned_profile_full_model_tests_not_native_cold_privacy",
              "normal_dependency_profile": normal_profile, "pytest_bookmarks": bookmarks,
              "test_locale_profile": {"locale": "C", "scope": "normal_and_derived_cold_test_processes_not_host_locale_coverage"},
              "normal_appdirs_profile": appdirs_profile,
              "normal_windows_dependencies": normal_lease.facts if normal_lease is not None else None}
    result["sysconfig_configuration"] = sysconfig_configuration
    result["linux_sysconfig_profile"] = linux_profile
    result["executed_entry"] = startup["executed_entry"]
    result["sysconfig_observation"] = observation.snapshot() if observation is not None else None
    (owned / "receipt.json").write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "results"}, ensure_ascii=True))
    if observation is not None:
        observation.data["receipt_written"] = True
        observation.window("receipt_finalization")
    if locator is not None:
        locator.data["receipt_written"] = True
    if distro_profile is not None:
        distro_profile.data["receipt_written"] = True
    return result["status"]


if __name__ == "__main__":
    raise SystemExit(main())
