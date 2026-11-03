"""scripts/demos/ui_demo.py: the local UI demo cannot spend a key or touch outputs/.

The served demo runs in a child interpreter, as it does for a person, so the
import order is the real one (blanks before api.main, api.main before the
first request) and nothing it sets leaks into this test process. Audit hooks
in the child record and block every non-loopback connection, every new
process and every file access under outputs/ while it serves.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.demos import ui_demo

ROOT = Path(__file__).resolve().parents[1]

_CHILD = r'''
import io, ipaddress, json, os, sys, time, urllib.error, urllib.request

ROOT = os.getcwd()
OUTPUTS = os.path.join(ROOT, "outputs")
network, spawned, outputs = [], [], []
_FILE_EVENTS = {
    "open", "os.mkdir", "os.remove", "os.rmdir", "os.rename", "os.link", "os.symlink", "os.truncate",
    "os.chmod", "os.utime", "os.listdir", "os.scandir", "shutil.rmtree", "shutil.copyfile", "shutil.move",
    "sqlite3.connect",
}
_SPAWN_EVENTS = {"subprocess.Popen", "os.posix_spawn", "os.spawn", "os.exec", "os.system", "os.fork", "os.startfile"}
# Python 3.11's platform module reads the Windows version by running these
# through cmd.exe (3.12 asks WMI instead): a local probe, not a worker.
_PLATFORM_VER_PROBES = ('/c "ver"', '/c "command /c ver"', '/c "cmd /c ver"')


def _loopback(host):
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False


def _under_outputs(path):
    if isinstance(path, int) or path is None:
        return False
    try:
        path = os.fsdecode(path)
    except TypeError:
        return False
    # A bare relative name ("outputs") is opened relative to some dir_fd, as
    # shutil.rmtree does while it removes the demo's own temporary directory;
    # the audit event does not say which directory, so it cannot be placed.
    if not os.path.isabs(path) and not any(sep and sep in path for sep in (os.sep, os.altsep)):
        return False
    path = os.path.abspath(path)
    return path == OUTPUTS or path.startswith(OUTPUTS + os.sep)


def audit(event, args):
    if event in ("socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr") and not _loopback(args[0]):
        network.append(f"{event} {args[0]!r}")
        raise ConnectionRefusedError("ui demo test: no external network")
    if event == "socket.connect" and isinstance(args[1], tuple) and not _loopback(args[1][0]):
        network.append(f"{event} {args[1]!r}")
        raise ConnectionRefusedError("ui demo test: no external network")
    if event in _SPAWN_EVENTS:
        if (sys.platform == "win32" and event == "subprocess.Popen" and isinstance(args[1], str)
                and args[1].endswith(_PLATFORM_VER_PROBES)):
            return
        spawned.append(f"{event} {str(args[:2])[:200]}")
        raise PermissionError("ui demo test: no new processes")
    if event in _FILE_EVENTS and any(_under_outputs(arg) for arg in args[:2] if isinstance(arg, (str, bytes, os.PathLike))):
        outputs.append(f"{event} {args[0]!r}")
        raise PermissionError("ui demo test: nothing under outputs/")


sys.addaudithook(audit)

from scripts.demos import ui_demo

crewai_at_import = "crewai" in sys.modules
import dotenv, dotenv.main, signal
dotenv_calls = []


def developer_dotenv(*args, override=False, **kwargs):
    """A developer's .env holding every provider key, loaded the way load_dotenv does."""
    dotenv_calls.append(override)
    for name in ui_demo.PROVIDER_KEYS:
        if override or name not in os.environ:
            os.environ[name] = "sk-from-a-dotenv-file"
    return True


# Before anything imports it: api/main.py and crewai both do `from dotenv import load_dotenv`.
dotenv.load_dotenv = dotenv.main.load_dotenv = developer_dotenv

scenario = sys.argv[1]
seen = {}
configure = ui_demo._configure_app


def configured(output_root):
    app, access = configure(output_root)
    from api import accounts, main, papers
    seen["temp_dir"] = str(output_root.parent)
    seen["accounts_off"] = accounts.database_path() is None
    seen["papers_root_in_temp"] = papers.PAPERS_ROOT.is_relative_to(output_root)
    seen["source_locator_off"] = main._source_locator is None
    main._REAP_INTERVAL_SECONDS = 0.05  # run every maintenance stage while the test watches
    if scenario == "late_key":
        os.environ["TAVILY_API_KEY"] = "tvly-ui-demo-late-sentinel"  # as if an import had loaded .env
    return app, access


ui_demo._configure_app = configured


def call(url, method="GET", body=None, headers=None):
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


if scenario == "late_key":
    try:
        with ui_demo.ui_demo():
            print(json.dumps({"served": True}))
    except ui_demo.DemoRefused as exc:
        print(json.dumps({"refused": str(exc), "served": False, "temp_removed": not os.path.exists(seen["temp_dir"])}))
    raise SystemExit(0)

statuses, refused = {}, {}
with ui_demo.ui_demo() as (url, code):
    from api import main, runs
    from fastapi.routing import APIRoute

    auth = {"X-Access-Code": code}
    run_ids = [item["run_id"] for item in json.loads(call(url + "/api/runs", headers=auth)[2])["runs"]]
    full_run = next(run_id for run_id in run_ids if (runs.DEFAULT_OUTPUT_ROOT / run_id / "commercialization_scores.json").is_file())
    slug = json.loads(call(url + "/api/samples")[2])[0]["slug"]
    class Fill(dict):
        def __missing__(self, key):  # a parameter of a route this walk does not know yet
            return "ui-demo"

    fill = Fill(run_id=full_run, slug=slug)
    for route in main.app.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = route.methods - {"HEAD"}
        names = runs.artifact_names() if "{artifact}" in route.path else [None]
        for artifact in names:
            path = route.path.format_map(Fill(fill, artifact=artifact) if artifact else fill)
            for method in sorted(methods):
                status, headers, _ = call(url + path, method=method, headers=auth,
                                          body=None if method in ("GET", "OPTIONS") else b"{}")
                key = f"{method} {route.path}" + (f" [{artifact}]" if artifact else "")
                if method in ("GET", "OPTIONS"):
                    statuses[key] = status
                else:
                    refused[key] = [status, headers.get("x-error-code")]
    for page in ("/", "/history", f"/run/{full_run}", "/samples", f"/samples/{slug}"):
        statuses[f"page {page}"] = call(url + page)[0]
    static_root = os.path.join(ROOT, "web", "static")
    for folder, _, files in os.walk(static_root):
        for name in sorted(files):
            relative = os.path.relpath(os.path.join(folder, name), static_root).replace(os.sep, "/")
            statuses["static " + relative] = call(url + "/static/" + relative)[0]
    # What the UI sends to spend a visitor's own key: complete enough that,
    # without the guard, the upload calls the model and the run starts a worker.
    from reportlab.pdfgen import canvas
    pdf = io.BytesIO()
    page = canvas.Canvas(pdf)
    page.drawString(60, 750, "Recycling sulfide solid-state electrolytes by solvent extraction")
    page.showPage()
    page.save()
    boundary = "uidemo"
    fields = {"llm_provider": "deepseek", "llm_api_key": "sk-ui-demo-byok", "llm_model": "deepseek-chat"}
    form = b"".join(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode()
                    for key, value in fields.items())
    form += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"paper.pdf\"\r\n"
             f"Content-Type: application/pdf\r\n\r\n").encode() + pdf.getvalue() + f"\r\n--{boundary}--\r\n".encode()
    refused["byok upload"] = list(call(url + "/api/papers", "POST", form,
                                       {"Content-Type": f"multipart/form-data; boundary={boundary}"})[:1])
    byok_run = json.dumps({"topic": "Recycling sulfide solid-state electrolytes", **fields,
                           "serper_api_key": "ui-demo-serper"}).encode()
    refused["byok run"] = list(call(url + "/api/runs", "POST", byok_run, {"Content-Type": "application/json"})[:1])
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and any(
            value == "not_checked" for value in main._maintenance_checks.values()):
        time.sleep(0.05)
    maintenance = dict(main._maintenance_checks)
    dotenv_keys = ui_demo.provider_keys_set()
    sigint_default = signal.getsignal(signal.SIGINT) is signal.default_int_handler

print(json.dumps({
    "network": network, "spawned": spawned, "outputs": outputs, "statuses": statuses, "refused": refused,
    "maintenance": maintenance, "dotenv_keys": dotenv_keys, "dotenv_calls": len(dotenv_calls),
    "crewai_at_import": crewai_at_import, "sigint_default": sigint_default,
    "playwright_loaded": "playwright" in sys.modules,
    "temp_removed": not os.path.exists(seen["temp_dir"]),
    **{key: value for key, value in seen.items() if key != "temp_dir"},
}))
'''


def _run_child(scenario: str) -> dict:
    env = {name: value for name, value in os.environ.items() if name not in ui_demo.PROVIDER_KEYS}
    # Would put the accounts database under outputs/ if the demo let it through.
    env["ACCOUNTS_DB"] = str(ROOT / "outputs" / "ui-demo-accounts-probe.db")
    env["SOURCE_LOCATOR_ENABLED"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", _CHILD, scenario], cwd=ROOT, env=env,
        capture_output=True, text=True, encoding="utf-8", timeout=300, check=False,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_served_demo_makes_no_external_request_and_leaves_outputs_alone():
    result = _run_child("serve")

    assert result["network"] == []
    assert result["spawned"] == []
    assert result["outputs"] == []
    assert result["temp_removed"]
    assert result["papers_root_in_temp"] and result["source_locator_off"] and result["accounts_off"]
    # A .env holding every provider key was loaded, and none of them got in.
    assert result["dotenv_calls"] >= 1 and result["dotenv_keys"] == []
    # crewai is imported only after the demo has set what it reads on import;
    # otherwise its telemetry starts and replaces the Ctrl+C handler.
    assert result["crewai_at_import"] is False and result["sigint_default"] is True
    # It runs without the opt-in e2e group.
    assert result["playwright_loaded"] is False
    # Every maintenance stage ran at least once against the temporary root.
    assert result["maintenance"] and "not_checked" not in result["maintenance"].values()
    # Every route that is not a read was refused by the demo, not by its handler.
    assert result["refused"]["byok upload"] == [405] and result["refused"]["byok run"] == [405]
    route_refusals = {key: value for key, value in result["refused"].items() if not key.startswith("byok")}
    assert route_refusals, "the app has write routes; the walk found none"
    assert all(value == [405, "ui_demo_read_only"] for value in route_refusals.values()), route_refusals
    # The reads a UI change needs still work.
    pages = {key: status for key, status in result["statuses"].items() if key.startswith(("page ", "static "))}
    assert pages and set(pages.values()) == {200}, pages
    for read in ("GET /api/runs", "GET /api/runs/{run_id}", "GET /api/runs/{run_id}/report", "GET /api/samples"):
        assert result["statuses"][read] == 200, read
    # Readiness answers 503 because no provider is configured, which is the point.
    server_errors = {key: status for key, status in result["statuses"].items()
                     if status >= 500 and key != "GET /health/ready" and "report.pdf" not in key}
    assert server_errors == {}


def test_key_loaded_while_importing_the_app_stops_the_demo_before_it_serves():
    result = _run_child("late_key")

    assert result["served"] is False
    assert "TAVILY_API_KEY" in result["refused"] and "sentinel" not in result["refused"]
    assert result["temp_removed"]


@pytest.mark.parametrize("name", ui_demo.PROVIDER_KEYS)
def test_refuses_to_start_while_a_provider_key_is_set(monkeypatch, capsys, name):
    for key in ui_demo.PROVIDER_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv(name, "sk-ui-demo-sentinel")

    def must_not_start(output_root):
        raise AssertionError("the app was configured despite a provider key")

    monkeypatch.setattr(ui_demo, "_configure_app", must_not_start)

    assert ui_demo.main([]) == 2
    err = capsys.readouterr().err
    assert name in err and "sk-ui-demo-sentinel" not in err


def test_blank_values_are_not_keys(monkeypatch):
    for key in ui_demo.PROVIDER_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "  ")
    assert ui_demo.provider_keys_set() == []


#: Names that look like provider keys but are not ones the demo must refuse.
_NOT_PROVIDER_KEYS = {
    "PROVIDER_API_KEY",  # placeholder in a comment in api/runs.py
    "PHOENIX_API_KEY",   # trace collector; the isolated app turns telemetry off before any import
}


def test_provider_key_list_covers_every_key_the_code_reads():
    sources = [*ROOT.glob("*.py"), *(ROOT / "api").rglob("*.py"), *(ROOT / "src").rglob("*.py"),
               *(ROOT / "ui").rglob("*.py"), ROOT / ".env.example"]
    read = set()
    for path in sources:
        read |= set(re.findall(r"\b[A-Z][A-Z0-9_]*_API_KEY\b", path.read_text(encoding="utf-8")))
    assert read, "found no provider key names to compare"
    assert read - _NOT_PROVIDER_KEYS <= set(ui_demo.PROVIDER_KEYS), sorted(read - _NOT_PROVIDER_KEYS - set(ui_demo.PROVIDER_KEYS))
