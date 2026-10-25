# Contributing

Read [AGENTS.md](AGENTS.md) first. It is a decision index: several seemingly
obvious changes have already been rejected on measured evidence. Use
[the documentation map](docs/README.md) for current guides and historical results.

For a first contribution, the map below is enough; read AGENTS.md before
changing pipeline, scoring or experiment code.

## Where newcomers can work

Look for issues labelled
[`good first issue`](https://github.com/shuxiachai/academic-commercialization-agent/labels/good%20first%20issue)
or [`help wanted`](https://github.com/shuxiachai/academic-commercialization-agent/labels/help%20wanted).
You need no API keys: the test suite and the browser smokes make no paid
requests.

| | Where |
|---|---|
| **Good for a first PR** | The main web client (`web/index.html`, `web/samples.html`, `web/static/`; new UI strings go in `web/static/js/i18n.js`, in English and Chinese); `ui/` readers and PDF export; current guides (`README*`, `CONTRIBUTING.md`, `docs/operating-guide.md`, `docs/README.md`); new tests in `tests/` and `e2e/`; new tools under `scripts/` |
| **Open an issue first** | Production pipeline and retrieval (`src/academic_agent/crew.py`, `source_pipeline.py`, `config/`); API access, BYOK and billing boundaries in `api/`; anything that changes scores, prompts or providers |
| **Do not change** | `src/academic_agent/evidence.py` (frozen experiments hash its bytes, and their tests fail on any edit; to change its behaviour, wrap it as `reviewer_plan_bounds.py` does); `AGENTS.md`, the maintainer's instructions to assistants; the experimental pages `web/saved-source-*/` and `web/source-locator/`; the root experiment scripts and the experimental modules in `src/academic_agent/` (their paths and bytes are bound the same way); dated documents `docs/prereg-*`, `docs/results-*`, `docs/errata-*`, `docs/protocol-*`; fixtures in `tests/fixtures/`, `evals/` and `benchmark_fixtures/`. Touch `pyproject.toml` and `uv.lock` only as far as your change needs |

If a change you need falls in the last row, open an issue and explain why;
the frozen material belongs to closed studies whose results depend on it.

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

Locally you can add `-n auto` (pytest-xdist, in the dev group) to spread the
suite over your cores: it then takes minutes rather than about ten. Run it
inside the project environment (`uv run`), not with `uv run --with`: some
tests start a fresh interpreter that may only read the project's own
installed packages. CI still runs serially: on a saturated four-core runner
a few timing-sensitive concurrency tests fail intermittently in parallel, so
confirm a parallel-only failure with a serial rerun before chasing it.

The guides link to sites this repository does not control (provider docs, the
live app, commit permalinks). `tests/test_public_docs.py` resolves only
repository-relative paths and deliberately makes no network request, so check
the external ones before sending a documentation change:

```bash
uv run python scripts/check_external_links.py
```

It reads the same guides that test lists, requests every `http(s)` link with a
timeout and a short pause per host, prints what is broken, and exits non-zero
if anything is. A 403 or 429 is a warning, not a failure: those hosts block
bots, and a bot-blocked page is not a dead page.

Tests of closed experiments, audits and probes are marked `experiment`
([list](tests/experiment_tests.txt)); they take about 80% of suite time for
code the app and pipeline never import. `uv run pytest -m "not experiment"`
runs the rest in a couple of minutes. On a pull request, the Ubuntu/Python
3.12 cell runs everything and the other cells skip `experiment`; the weekly
[full-suite workflow](.github/workflows/full-suite.yml) runs everything on
every cell. Add a new test of experiment code to the list;
`tests/test_experiment_suite.py` rejects a listed file that tests code the
app or pipeline uses. An unlisted test simply runs everywhere.

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

The Ubuntu Python 3.12 matrix cell measures coverage during its full test run;
the other three cells run the full suite without coverage. The existing
coverage status check aggregates matrix success, including that measurement,
rather than executing the suite a fifth time. It fails for failed, cancelled
or skipped matrix results. Verbose reporting remains enabled in every cell.

Every matrix cell also publishes its 40 slowest test phases with
`--durations=40`. Use `uv run pytest -q --durations=40` for a local profile before
optimizing fixtures. These timings locate expensive setup/calls/teardown, not
the cause of that cost, and cannot by themselves justify removing process or
default-off isolation checks. Preserve the collected suite and coverage scope
when comparing measurement overhead; concurrent workloads are a confounder.

Maintain failure coverage, not a target test count. Combine identical setup
when result and audit assertions protect the same scenario; assert nonempty
data at its delivery boundary and request parameters at the real call seam.
Replace brittle display-name/prose checks with the actual executable contract,
including a negative control that the replacement rejects. Reusable helpers
must still exercise each distinct adapter. Do not delete or relocate frozen
experiment tests, some of which are included in source identity hashes, merely
to shrink the default suite. Warning policy, full-suite collection and the
cross-platform/browser/container boundaries remain unchanged.

Keep source worktrees outside `outputs`: offline audit guards deliberately treat
that path as private runtime data, so a checkout there can fail while reading
its own source. Managed worktrees or the existing excluded `.claude/worktrees`
boundary avoid that layout conflict. A nested offline checkout should have an
empty ignored `.env` boundary to prevent discovery of its parent's real config,
and its own virtual environment so editable imports refer to the tested source.
See the [testing status and boundary map](docs/testing-status.md) for qualified
measurements and the current coverage targets.

Negative controls need an assertion path that raises directly. A `subTest`
records an assertion failure instead of propagating it into an outer
`assertRaises`; keep per-field subtests for positive delivery checks and use
the same underlying assertions directly for deliberate mutants. Mocking
`api.runs.subprocess.Popen` also patches the shared standard-library module.
Keep real, fixed Node harness launches separate from worker-launch mocks,
with explicit timeout termination and bounded stream cleanup.

### Optional real-browser smoke

```bash
uv sync --group e2e
uv run --group e2e playwright install chromium
uv run --group e2e python -m e2e.browser_smoke
uv run --group e2e python -m e2e.composer_smoke
```

This uses real Chromium and the real loopback application with fixture runs.
It blocks external and mutating requests: it cannot launch paid work and does
not establish Railway availability or model quality.

The separate composer journey serves the actual static client from a loopback
server that has no paid API routes. Browser-intercepted POST responses exercise
upload/submission races, accepted-run navigation and translated admission errors;
unexpected requests fail the audit. It does not relax the original journey's
read-only guard or contact any model/search provider.

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

The project is licensed under the [MIT License](LICENSE). By submitting a
pull request you agree that your contribution is licensed under the same
terms, and that you have the right to submit it under them.

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

New experiment runners, probes and audits belong under `scripts/` (offline
audits in `scripts/audits/`), not at the repository root. Existing root
runners stay where they are because their protocols bind paths and hashes;
see the [repository map](docs/README.md#repository-map).
