"""scripts/demos/ui_demo.py: the local UI demo cannot spend a key or touch outputs/.

The served demo runs in a child interpreter, as it does for a person, so the
import order is the real one (blanks before api.main, api.main before the
first request) and nothing it sets leaks into this test process. Audit hooks
in the child record and block every non-loopback connection, every new
process and every file access under outputs/ while it serves.
"""

from __future__ import annotations

import asyncio
import errno
import io
import json
import os
import re
import socket
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from scripts.demos import ui_demo

ROOT = Path(__file__).resolve().parents[1]

_CHILD = r'''
import http.client, io, ipaddress, json, os, sys, time, urllib.error, urllib.parse, urllib.request

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
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()
    # A reset, a timeout or a short body, also while reading an error's body:
    # name the request, or a repeat on CI cannot say which one (#319).
    except (OSError, http.client.HTTPException) as exc:
        raise RuntimeError(f"{method} {urllib.parse.urlsplit(url).path} failed: {exc!r}") from exc


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
    # A body the guard does not read is reset with the connection: urllib got
    # "Connection reset by peer" for this on Linux every time.
    # Kept out of refused, so that only the walk's routes are checked there.
    status, headers, _ = call(url + "/api/runs", "POST", b"x" * (8 * 1024 * 1024), {"Content-Type": "application/json"})
    large_body = [status, headers.get("x-error-code")]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and any(
            value == "not_checked" for value in main._maintenance_checks.values()):
        time.sleep(0.05)
    maintenance = dict(main._maintenance_checks)
    dotenv_keys = ui_demo.provider_keys_set()
    sigint_default = signal.getsignal(signal.SIGINT) is signal.default_int_handler

print(json.dumps({
    "network": network, "spawned": spawned, "outputs": outputs, "statuses": statuses, "refused": refused,
    "large_body": large_body, "maintenance": maintenance,
    "dotenv_keys": dotenv_keys, "dotenv_calls": len(dotenv_calls),
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
    # An 8 MB body is read before the 405, so the answer arrives instead of a reset.
    assert result["large_body"] == [405, "ui_demo_read_only"]
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


# ReadOnly on its own: a scripted ASGI receive, so these run the same on every OS.

def _guard(messages, *, body_limit=1024, idle_seconds=5.0):
    """Run ReadOnly on one POST; return (log of receive/send/app events, messages sent)."""
    log, sent = [], []
    queue = iter(messages)

    async def receive():
        log.append("receive")
        message = next(queue, None)
        if message is None:  # nothing more is coming: wait like a stalled client
            await asyncio.Event().wait()
        return message

    async def send(message):
        log.append("send")
        sent.append(message)

    async def app(scope, receive, send):
        log.append("app")

    guard = ui_demo.ReadOnly(app, body_limit=body_limit, idle_seconds=idle_seconds)
    scope = {"type": "http", "method": "POST", "path": "/api/runs", "headers": []}
    asyncio.run(asyncio.wait_for(guard(scope, receive, send), 5))
    return log, sent


def _body(chunk, more):
    return {"type": "http.request", "body": chunk, "more_body": more}


def test_the_guard_reads_the_whole_body_before_it_answers():
    log, sent = _guard([_body(b"a" * 100, True), _body(b"b" * 100, True), _body(b"c", False)])
    assert log == ["receive"] * 3 + ["send"] * 2
    assert sent[0]["type"] == "http.response.start" and sent[0]["status"] == 405
    assert (b"x-error-code", b"ui_demo_read_only") in sent[0]["headers"]


def test_the_guard_stops_reading_past_the_limit_and_still_answers():
    log, sent = _guard([_body(b"x" * 4, True)] * 100, body_limit=10)
    assert log.count("receive") == 3  # 4, 8, then 12 bytes > 10
    assert sent[0]["status"] == 405


def test_the_guard_answers_after_an_idle_wait():
    log, sent = _guard([_body(b"x", True)], idle_seconds=0.05)
    assert log.count("receive") == 2 and sent[0]["status"] == 405


def test_the_guard_does_not_answer_a_client_that_left():
    log, sent = _guard([_body(b"x", True), {"type": "http.disconnect"}])
    assert log == ["receive", "receive"] and sent == []


def test_reads_reach_the_app_without_the_guard_touching_the_body():
    log = []

    async def receive():
        log.append("receive")
        return _body(b"", False)

    async def app(scope, receive, send):
        log.append("app")

    guard = ui_demo.ReadOnly(app, body_limit=10, idle_seconds=5.0)
    for method in ("GET", "HEAD", "OPTIONS"):
        asyncio.run(guard({"type": "http", "method": method, "path": "/", "headers": []}, receive, None))
    assert log == ["app"] * 3


def _walk_call():
    """call() from the child's source, defined in this process."""
    source = re.search(r"\ndef call\(.*?\n(?=\n\S)", _CHILD, re.S).group(0)
    namespace = {}
    exec("import http.client, urllib.error, urllib.parse, urllib.request\n" + source, namespace)
    return namespace["call"]


def test_a_failed_call_in_the_walk_names_its_request():
    """A reset on CI said only ConnectionResetError (#319); the walk's call() now says which request."""
    with socket.socket() as probe:  # a loopback port with nothing listening
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    with pytest.raises(RuntimeError, match=r"^POST /api/runs failed: "):
        _walk_call()(f"http://127.0.0.1:{port}/api/runs", "POST", b"{}")


def test_a_reset_while_reading_an_error_body_names_its_request(monkeypatch):
    """exc.read() runs inside the HTTPError handler, where the handler beside it cannot catch a reset.

    Scripted: a real reset can arrive before the status line is read, and the
    test would then cover urlopen() instead of the error body.
    """

    class ResetBody(io.BytesIO):
        def read(self, *args):
            raise ConnectionResetError(errno.ECONNRESET, "Connection reset by peer")

    def refuse_then_reset(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 405, "Method Not Allowed", {}, ResetBody())

    monkeypatch.setattr(urllib.request, "urlopen", refuse_then_reset)
    with pytest.raises(RuntimeError, match=r"^POST /api/runs failed: ConnectionResetError\("):
        _walk_call()("http://127.0.0.1:9/api/runs", "POST", b"{}")


def test_a_short_body_names_its_request():
    """http.client.IncompleteRead is not an OSError, so call() names it separately."""
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        def answer_short():
            conn, _ = server.accept()
            with conn:
                conn.settimeout(10)
                request = b""
                while b"\r\n\r\n" not in request:
                    request += conn.recv(4096)
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\nConnection: close\r\n\r\nshort")
                conn.shutdown(socket.SHUT_WR)
                while conn.recv(4096):  # until the client closes, so that nothing is left unread to reset
                    pass

        thread = threading.Thread(target=answer_short, daemon=True)
        thread.start()
        with pytest.raises(RuntimeError, match=r"^GET /api/runs failed: IncompleteRead\("):
            _walk_call()(f"http://127.0.0.1:{port}/api/runs")
        thread.join(10)
    assert not thread.is_alive()
