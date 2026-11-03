"""Serve the web client on fixture runs, with no keys and no provider calls.

    uv run python -m scripts.demos.ui_demo

This is the browser smoke's isolated app (``e2e/isolated_app.py``) left
running for a person: the real FastAPI app on a loopback port, an access
code, and a few completed runs written into a temporary directory. Edit
anything under ``web/`` and reload the page; static files are read from disk
on every request.

It refuses to start while a provider key is set, so it cannot spend one.
Keys in ``.env`` do not count: it blanks every provider key before importing
the app, and ``load_dotenv`` never overrides a variable that is already set.
It answers only GET, HEAD and OPTIONS, which is all the read journeys need:
starting a run, uploading a paper or signing up gets a 405 before any code
that could reach a provider runs. Nothing is written under ``outputs/``, and
the temporary directory is removed on Ctrl+C.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

# Nothing from academic_agent, api or e2e at module level: they import crewai,
# which loads .env and starts its telemetry as it is imported. ui_demo()
# imports them only after it has set the environment they read.

#: Every provider credential the app or the pipeline reads. A test fails if
#: the code starts reading an ``*_API_KEY`` that is missing here.
PROVIDER_KEYS = (
    "ANTHROPIC_API_KEY",
    "DASHSCOPE_API_KEY",
    "DEEPSEEK_API_KEY",
    "LENS_API_KEY",
    "NCBI_API_KEY",
    "OPENAI_API_KEY",
    "OPENALEX_API_KEY",
    "SEMANTIC_SCHOLAR_API_KEY",
    "SERPER_API_KEY",
    "TAVILY_API_KEY",
)
#: Features with storage of their own. An empty value switches each one off,
#: and keeps ``.env`` from switching it on.
SWITCHED_OFF = ("ACCOUNTS_DB", "SOURCE_LOCATOR_ENABLED", "SOURCE_LOCATOR_EXECUTION_ENABLED")
READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
FIXTURE_RUNS = 3
_SCORES = {
    "overall_score": 65, "trl_score": 6, "mrl_score": 6,
    "patent_strength": 3, "market_accessibility": 3.5, "evidence_confidence": 4,
    "market_uncertainty": "high (2000× spread: 0.01–20 bn USD)",
}


class DemoRefused(RuntimeError):
    """The demo will not start in this environment."""


def provider_keys_set() -> list[str]:
    """Names of provider keys with a value in this process. Never the values."""
    return [name for name in PROVIDER_KEYS if os.environ.get(name, "").strip()]


class ReadOnly:
    """Answer 405 to every request that is not a read, before the app sees it."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] not in READ_METHODS:
            response = JSONResponse(
                {"detail": "The UI demo is read-only: it serves fixture runs and makes no provider calls."},
                status_code=405,
                headers={"Allow": "GET, HEAD, OPTIONS", "X-Error-Code": "ui_demo_read_only"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _configure_app(output_root: Path):
    from e2e.isolated_app import _configure_isolated_app

    return _configure_isolated_app(output_root)


@contextmanager
def ui_demo(fixture_runs: int = FIXTURE_RUNS) -> Iterator[tuple[str, str]]:
    """Serve the demo and yield ``(url, access_code)``; clean up on exit."""
    found = provider_keys_set()
    if found:
        raise DemoRefused(
            "provider keys are set: " + ", ".join(found)
            + ". Unset them; the UI demo never needs one."
        )
    for name in PROVIDER_KEYS + SWITCHED_OFF:
        os.environ[name] = ""
    # crewai's telemetry reads this once, on import, and otherwise takes over
    # SIGINT and SIGTERM. The isolated app sets it too, but only after the
    # imports below have already loaded crewai.
    os.environ["OTEL_SDK_DISABLED"] = "true"

    from academic_agent.run_output import save_scores, save_source_collection
    from e2e.isolated_app import (
        ACCESS_CODE,
        _saved_source_fixture,
        _serve,
        _write_completed_run,
    )

    with TemporaryDirectory(prefix="ui-demo-") as temp_dir:
        output_root = Path(temp_dir) / "outputs"
        app, access = _configure_app(output_root)
        # Both .env loaders have run by now (crewai's in the imports above,
        # api/main.py's in this call). The blanks should have kept every key
        # out; check, not assume.
        found = provider_keys_set()
        if found:
            raise DemoRefused("provider keys appeared while the app was imported: " + ", ".join(found))
        owner = access.owner_id(ACCESS_CODE)
        for index in range(fixture_runs):
            run_id = _write_completed_run(output_root, owner)
            if index == 0:
                # One run with saved sources and a scorecard, so those tabs
                # have something to show; the others are report-only.
                save_source_collection(json.dumps(_saved_source_fixture(), ensure_ascii=False), run_id, output_root)
                save_scores(json.dumps(_SCORES), run_id, output_root)
        with _serve(ReadOnly(app)) as url:
            yield url, ACCESS_CODE


def main(argv: list[str] | None = None) -> int:
    if (sys.argv[1:] if argv is None else argv):
        raise SystemExit("usage: python -m scripts.demos.ui_demo  (it takes no arguments)")
    stop = threading.Event()
    previous = signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        with ui_demo() as (url, code):
            print(f"UI demo on {url}\nAccess code: {code}\nCtrl+C stops it.", flush=True)
            try:
                # A timed wait, because Event.wait() without one cannot be
                # interrupted by Ctrl+C on Windows.
                while not stop.wait(0.5):
                    pass
            except KeyboardInterrupt:
                pass
    except DemoRefused as exc:
        print(f"ui_demo: {exc}", file=sys.stderr)
        return 2
    finally:
        signal.signal(signal.SIGTERM, previous)
    print("Stopped; the temporary directory is gone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
