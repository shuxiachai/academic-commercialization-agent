# syntax=docker/dockerfile:1
#
# Two stages so that dependency installation is cached separately from source.
# CrewAI and its transitive deps take minutes to resolve; without this split,
# editing a single .py file would reinstall all 26 dependencies.

ARG PYTHON_VERSION=3.12

# ---------------------------------------------------------------------------
# Stage 1 — base: system packages shared by build and runtime
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS base

# fonts-wqy-zenhei: the PDF exporter embeds a CJK font rather than relying on
#   the reader having one (ui/pdf_export.py), and none ship in python:slim.
#
#   Not fonts-noto-cjk, which is the obvious choice and does not work here.
#   Debian ships Noto CJK as OpenType/CFF, and reportlab's TTFont only reads
#   TrueType outlines — it rejects the file with "postscript outlines are not
#   supported" even though the path resolves. The font then degrades to a CID
#   face and reports render as blank boxes for anyone whose reader lacks the
#   typeface. WenQuanYi Zen Hei is TrueType, registers cleanly, and was
#   verified to cover Simplified, Traditional, Japanese and Korean glyphs.
#   Its path is already among _CJK_TTF_CANDIDATES, so no code change is needed.
# tini: the UI launches each pipeline run as a subprocess and cancels it with
#   proc.terminate() (ui/runner.py). A bare Python PID 1 neither forwards
#   signals nor reaps children, so cancelled runs would linger as zombies and
#   `docker stop` would sit until it timed out and killed the container.
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-wqy-zenhei \
        tini \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# ---------------------------------------------------------------------------
# Stage 2 — deps: resolve the locked environment, nothing else
# ---------------------------------------------------------------------------
FROM base AS deps

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

WORKDIR /app

# Only the lockfile and manifest, so this layer is reused until they change —
# the main speedup this stage relies on. A --mount=type=cache on top of that
# would help when the lockfile does change, but Railway's builder requires
# its own cacheKey-prefixed id format on that flag, which isn't worth
# chasing for a secondary optimization; plain layer caching is enough.
COPY pyproject.toml uv.lock README.md ./
# The project is a package; src/ must exist for the build backend to succeed.
COPY src/academic_agent/__init__.py src/academic_agent/__init__.py

RUN uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Stage 3 — runtime
# ---------------------------------------------------------------------------
FROM base AS runtime

# Non-root. The UID is fixed at 1000 so a bind-mounted outputs/ directory has
# predictable ownership; see the compose file, which creates the directory on
# the host before mounting it.
RUN useradd --create-home --uid 1000 appuser

WORKDIR /app

COPY --from=deps --chown=appuser:appuser /app/.venv /app/.venv
# uv is kept in the image so benchmark.py can run inside the container. It adds
# roughly 30 MB; drop this line if image size matters more than being able to
# reproduce a benchmark run in the same environment the app uses.
COPY --from=deps /usr/local/bin/uv /usr/local/bin/uv

COPY --chown=appuser:appuser . .

ENV PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV=/app/.venv

# Runs are written here — history and reports are state, so whatever runs
# this image should mount something over it (docker-compose binds a host
# directory; Railway and similar PaaS use their own volume feature instead
# of the Dockerfile VOLUME instruction, which some of their builders reject
# outright).
RUN mkdir -p /app/outputs && chown appuser:appuser /app/outputs

# Fail the build if no CJK font resolved. Without this the failure is silent:
# _resolve_font() degrades to a CID font and then to Helvetica, so a Chinese
# report renders as blank boxes for whoever opens it and nothing logs an error.
# Debian has moved these files between releases, so the check asks the
# application's own resolver rather than testing a hard-coded path.
RUN python scripts/verify_container_fonts.py

USER appuser
EXPOSE 8000

# Checks /health rather than the page. It reports the concurrency state and
# whether an LLM provider resolved, so a container that serves HTML but cannot
# actually run an assessment is still reported unhealthy. Reads $PORT rather
# than assuming 8000, so it still checks the right port on a platform that
# assigns one (see CMD below).
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT','8000') + '/health', timeout=4)" \
        || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
# A single worker on purpose. Runs are subprocesses tracked in an in-process
# registry, so a second worker would enforce its own separate concurrency cap
# and could neither see nor cancel the first one's runs.
#
# Binds to $PORT when the platform sets one (Railway, Render, Heroku-style
# PaaS all assign a port at deploy time and expect the app to listen on it)
# and falls back to 8000 for docker-compose, where the mapping is fixed on
# the host side instead. `exec` replaces this shell rather than forking a
# child of it, so tini still supervises uvicorn directly — the whole reason
# a shell shows up here instead of the exec-form CMD used everywhere else in
# this file is that JSON-array CMD does not expand environment variables.
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
