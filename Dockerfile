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

# fonts-noto-cjk: the PDF exporter embeds a CJK font rather than relying on the
#   reader having one (ui/pdf_export.py). Its Linux candidates all live under
#   /usr/share/fonts and none ship in python:slim, so Chinese reports would fall
#   back to Helvetica and render as blank boxes. This exact gap already broke a
#   CI run on the Linux runner.
# tini: the UI launches each pipeline run as a subprocess and cancels it with
#   proc.terminate() (ui/runner.py). A bare Python PID 1 neither forwards
#   signals nor reaps children, so cancelled runs would linger as zombies and
#   `docker stop` would sit until it timed out and killed the container.
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-noto-cjk \
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

# Only the lockfile and manifest, so this layer is reused until they change.
COPY pyproject.toml uv.lock README.md ./
# The project is a package; src/ must exist for the build backend to succeed.
COPY src/academic_agent/__init__.py src/academic_agent/__init__.py

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

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

# Gradio binds 127.0.0.1 by default, which is unreachable from outside the
# container. It reads these at launch, so app.py stays unchanged and local
# development keeps its loopback-only default.
ENV GRADIO_SERVER_NAME=0.0.0.0 \
    GRADIO_SERVER_PORT=7860 \
    PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV=/app/.venv

# Runs are written here. Declared so an unmounted container still works, though
# compose binds a host directory over it — history and reports are state.
RUN mkdir -p /app/outputs && chown appuser:appuser /app/outputs
VOLUME ["/app/outputs"]

# Fail the build if no CJK font resolved. Without this the failure is silent:
# _resolve_font() degrades to a CID font and then to Helvetica, so a Chinese
# report renders as blank boxes for whoever opens it and nothing logs an error.
# Debian has moved these files between releases, so the check asks the
# application's own resolver rather than testing a hard-coded path.
RUN python scripts/verify_container_fonts.py

USER appuser
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/', timeout=4)" \
        || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "app.py"]
