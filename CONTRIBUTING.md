# Contributing

Thank you for your interest in contributing!

## Getting started

```bash
git clone https://github.com/shuxiachai/academic-commercialization-agent.git
cd academic-commercialization-agent
uv sync
cp .env.example .env   # fill in your API keys
```

## Running tests

```bash
uv run pytest tests/ -q
```

All 188 tests must pass before submitting a PR.

## What to contribute

- **Bug fixes** — check the [issue tracker](https://github.com/shuxiachai/academic-commercialization-agent/issues) for open bugs
- **New language support** — add entries to `_WARNING_I18N`, `_UI_I18N`, and `_SCORECARD_I18N` in `app.py`
- **New industry weight profiles** — add to `_WEIGHT_PROFILES` in `evidence.py`
- **Source API integrations** — extend `source_pipeline.py` with additional academic or patent sources
- **UI improvements** — `app.py` contains the full Gradio interface

## Pull request guidelines

1. Keep PRs focused — one fix or feature per PR
2. Add or update tests for any changed logic in `source_pipeline.py` or `evidence.py`
3. Run `uv run pytest tests/ -q` locally before opening the PR
4. Describe what problem your PR solves in the PR description

## Project structure

| File | Purpose |
|---|---|
| `app.py` | Gradio web UI |
| `src/academic_agent/crew.py` | Agent and task wiring |
| `src/academic_agent/source_pipeline.py` | Pre-run source collection |
| `src/academic_agent/evidence.py` | Evidence models and guardrails |
| `src/academic_agent/pipeline_worker.py` | Subprocess worker |
| `src/academic_agent/config/agents.yaml` | Agent role definitions |
| `src/academic_agent/config/tasks.yaml` | Task requirements |

## Questions?

Open an issue or start a discussion — happy to help.
