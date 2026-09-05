# Contributing

Read [AGENTS.md](AGENTS.md) first. It is a decision index: several seemingly
obvious changes have already been rejected on measured evidence. Use
[the documentation map](docs/README.md) for current guides and historical results.

## Setup

```bash
git clone https://github.com/shuxiachai/academic-commercialization-agent.git
cd academic-commercialization-agent
uv sync
```

Python 3.11/3.12 are the CI-tested versions. Dependencies need network to
install; the default tests need neither provider keys nor paid requests.
Configure `.env` only when intentionally running real analysis.

## Checks before and after a change

```bash
uv run pytest -q
uv run --with ruff ruff check .
uv run --with pylint pylint src/ ui/ api/ --disable=all --enable=bad-except-order,unreachable,used-before-assignment,undefined-variable --score=n
```

The Ruff invocation is intentional: CI resolves the latest release, while the
local pin can disagree. The narrow Pylint set catches specific correctness
failures; do not replace it with a general style cleanup.

- Run the complete suite before editing and after the fix.
- Do not weaken assertions or add skips to make a failure disappear.
- Read the actual `UserWarning` before acting. A network-leak warning means
  test isolation is broken; an intentional domain warning needs an explicit
  assertion, not a global ignore.
- Use Node locally to execute JavaScript-backed contract tests. CI requires
  it instead of accepting a silently reduced browser-contract denominator.
- Assert at the API/status/progress/browser seam, not just internal fields.
- Re-inject the original defect and confirm the new regression test fails,
  then restore the fix.
- Update nearby explanations when behaviour changes. Bilingual benchmark
  tables and claims are checked independently in `tests/test_public_docs.py`.

If pytest fails to create its temporary directory because of local permissions,
choose a new writable temporary root; pytest may clear an explicitly supplied
`--basetemp`, so never point it at an existing data directory. For example:

```powershell
$testTemp = Join-Path (Get-Location).Path ("outputs/pytest-" + [guid]::NewGuid().ToString("N"))
uv run pytest -q --basetemp $testTemp
```

CI runs Linux/Windows × Python 3.11/3.12, lint, an 85% coverage floor,
zero-provider Chromium and Docker runtime checks. Historical test totals are
not a substitute for passing the current suite.

### Optional real-browser smoke

```bash
uv sync --group e2e
uv run --group e2e playwright install chromium
uv run --group e2e python -m e2e.browser_smoke
```

This uses real Chromium and the real loopback application with fixture runs.
It blocks external and mutating requests: it cannot launch paid work and does
not establish Railway availability or model quality.

## What to contribute

- Focused bug fixes with an observed failure, a boundary assertion and a
  re-injection check.
- UI/accessibility and translation improvements in `web/` and shared
  `ui/i18n.py`, preserving CSP and explicit unavailable states.
- Retrieval changes measured first on stored data. New source adapters need
  bounded transport, accounting, validation and independent source-value
  evidence before production connection.
- Documentation corrections that distinguish current behaviour from dated
  experiments, without rewriting failed studies.

Do **not** casually add scoring profiles, change the confidence floor, upgrade
CrewAI on main or wire experimental Tool Calling into the worker. The reasons
and required evidence are in [Do not redo these](AGENTS.md#do-not-redo-these).

## Pull requests and privacy

Keep each PR focused and describe the problem, alternatives, evidence,
limitations and validation. Commit messages are deliberately substantive and
in English; do not add Co-Authored-By or tool-signature lines. Preserve
unrelated worktree changes and raw reviewer files.

This public repository must not receive credentials, private review packets,
first-person resume notes or private run capability URLs. Resume notes are a
separate private repository. A paid test, production restart, publication of
private material or PR merge needs its own applicable authorization; a
documentation change is not that authorization.

## Code map

| Area | Entry |
|---|---|
| API and ownership/admission | `api/main.py`, `api/runs.py`, `api/papers.py`, `api/models.py` |
| Build-free web client | `web/` |
| Shared presentation/readers | `ui/i18n.py`, `ui/run_reader.py`, `ui/pdf_export.py` |
| Pipeline and source validation | `src/academic_agent/crew.py`, `source_pipeline.py`, `evidence.py` |
| Worker, recovery and terminal truth | `src/academic_agent/pipeline_worker.py`, `checkpoint_runtime.py`, `run_terminal.py` |
| Configured roles and tasks | `src/academic_agent/config/` |
| Zero-provider browser journey | `e2e/browser_smoke.py` |

The detailed boundary map is in [AGENTS.md](AGENTS.md#layout-and-boundary-specific-reading).
