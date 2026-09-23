"""Fresh main-import absence, not a callback app constructed with None."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("inject_post", [False, True])
def test_fresh_main_default_off_has_no_locator_entry_or_native_import(tmp_path, inject_post):
    """Real routing/import/store absence must fail under an injected production POST."""
    script = r'''
import asyncio
import http.client
import os
from pathlib import Path
import sys
from unittest.mock import patch

import dotenv
import dotenv.main
import httpx
from starlette.routing import Match

root = Path(sys.argv[1]).resolve()
temporary = Path.cwd().resolve()
sys.path[:0] = [str(root), str(root / 'src')]
attempts = []

def forbidden(*args, **kwargs):
    attempts.append('external_call')
    raise AssertionError('network, provider and worker dispatch forbidden')

def audit(event, args):
    if (event.startswith('socket.') and event != 'socket.__new__') or event == 'subprocess.Popen':
        forbidden()
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path = Path(os.fsdecode(args[0])).resolve()
        if path.name == '.env' or path.name.startswith('.env.'):
            attempts.append('dotenv')
            raise AssertionError('dotenv forbidden')
        if path.is_relative_to(root / 'outputs') and not path.is_relative_to(temporary):
            attempts.append('private_output')
            raise AssertionError('production outputs forbidden')
        if args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            if not path.is_relative_to(temporary):
                forbidden()
    if event == 'os.mkdir' and not Path(os.fsdecode(args[0])).resolve().is_relative_to(temporary):
        forbidden()

async def scenario():
    from api import main

    assert main._source_locator is main.app.state.source_locator is None
    assert {'/health', '/health/ready', '/api/runs', '/api/papers', '/api/receipts'} <= {
        getattr(route, 'path', None) for route in main.app.routes
    }
    # No import means no constructor/key-loader/native-ledger factory can run.
    absent = {'api.saved_source_production', 'api.saved_source_controller',
              'api.saved_source_accounting', 'academic_agent.saved_source_accounted_qwen'}
    assert not absent.intersection(sys.modules)
    assert not any(name.startswith('academic_agent.report_evidence_source_locator_qwen') for name in sys.modules)
    url = '/api/runs/20260919T123456Z-0123456789abcdef0123456789abcdef/source-locator'
    if sys.argv[2] == 'inject':
        async def injected():
            return {'unexpected': 'production POST'}
        main.app.add_api_route('/api/runs/{run_id}/source-locator', injected, methods=['POST'])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(main.app), base_url='http://test') as client:
        page = await client.get('/')
        assert page.status_code == 200 and b'href="/source-locator' not in page.content
        for path in ('/source-locator', '/api/source-locator/receipts',
                     '/source-locator-static/entry.js', '/source-locator-static/receipt.js',
                     '/source-locator-static/accounting.js', '/source-locator-static/result.js',
                     '/source-locator-static/app.css', '/source-locator-static/receipt.css',
                     '/api/saved-source-receipts', '/api/saved-source-usage-receipts',
                     '/locator-static/app.js', '/receipt-static/app.js', '/usage-static/app.js'):
            response = await client.get(path)
            assert response.status_code == 404, (path, response.status_code)
        response = await client.post(url, json={'question': 'Synthetic question'})
        assert response.status_code == 405, 'unexpected production POST: ' + str(response.status_code)
    for method, path in (('POST', url), ('GET', '/source-locator'), ('GET', '/api/source-locator/receipts')):
        scope = {'type': 'http', 'method': method, 'path': path, 'root_path': ''}
        assert not any(route.matches(scope)[0] is Match.FULL for route in main.app.routes)
    assert not list(temporary.rglob('.source-locator-v1'))
    assert not attempts, attempts
    print('fresh main default-OFF verified; external calls=0; native imports=0')

# Only asyncio's Windows self-pipe is constructed before the socket guard.
# The actual main import and every request remain inside the audit boundary.
with asyncio.Runner() as runner:
    runner.get_loop()
    sys.addaudithook(audit)
    with (patch.object(dotenv, 'load_dotenv', return_value=False),
          patch.object(dotenv.main, 'load_dotenv', return_value=False),
          patch.object(http.client.HTTPConnection, 'request', forbidden),
          patch.object(httpx.HTTPTransport, 'handle_request', forbidden),
          patch.object(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden),
          patch('appdirs.user_data_dir', return_value=str(temporary / 'crewai-data'))):
        with patch('socket.has_ipv6', False):
            import urllib3.util.connection
        runner.run(scenario())
'''
    environment = {name: os.environ[name] for name in ("SYSTEMROOT", "WINDIR") if name in os.environ}
    environment.update({name: str(tmp_path) for name in (
        "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "XDG_CACHE_HOME", "TMP", "TEMP",
    )})
    environment.update({
        "PYTHON_DOTENV_DISABLED": "1", "SOURCE_LOCATOR_ENABLED": "false",
        "AGENT_OBSERVABILITY_ENABLED": "false", "OTEL_SDK_DISABLED": "true",
        "CREWAI_TELEMETRY_ENABLED": "false", "DO_NOT_TRACK": "1",
    })
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-X", "utf8", "-c", script,
         str(Path(__file__).resolve().parents[1]), "inject" if inject_post else "absent"],
        cwd=tmp_path, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=90, check=False,
    )
    if inject_post:
        assert result.returncode != 0
        assert "AssertionError: unexpected production POST: 200" in result.stderr
        assert "fresh main default-OFF verified" not in result.stdout
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert "fresh main default-OFF verified; external calls=0; native imports=0" in result.stdout
