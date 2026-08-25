# Academic Commercialization Assessment Agent v2.0.0

## Reliability-first production workflow

Version 2.0.0 turns the original Gradio demonstration into a deployable,
evidence-constrained decision-support system. A FastAPI service, build-free web
client, CLI, and recovery path now observe the same persisted run artifacts.
The release also adds measured evaluation, paid-operation controls,
privacy-reduced tracing, and node-level crash recovery.

This remains decision support rather than legal, regulatory, technical, or
investment advice.

## Highlights

### Evidence before generation

- Deterministic retrieval plans free-form topics and collects academic, patent,
  market, and applicable regulator or trial-registry records before CrewAI runs.
- DOI/URL checks, allowlists, provenance tiers, relevance screening,
  deduplication, and a rejection audit produce a frozen source registry.
- The six-stage workflow analyses that registry, writes a cited report, applies
  a bounded review plan, and generates a source-traceable scorecard.
- Evidence-gap planning is available as zero-call shadow instrumentation. It
  records whether bounded supplemental search would be justified but performs
  no production Tool Calling in this release.

### Public application and paid boundaries

- Gradio has been replaced by FastAPI plus a vanilla HTML/CSS/ES-module client.
- Runs execute in cancellable subprocesses and expose live progress, sources,
  scorecards, reliability states, usage, cost, and downloadable reports.
- Access-code and BYOK modes isolate credentials and run history.
- Complete runs and PDF extraction share concurrency and daily paid-operation
  admission; failed startup rolls back reserved quota.
- Rate limiting, ownership checks, bounded uploads, retention, URL validation,
  and strict response headers harden the public surface.

### Auditable recovery and observability

- Content-addressed checkpoints bind reusable outputs to input, evidence,
  configuration, task, and pipeline identity.
- Recovery creates an immutable child, requires fresh credentials, validates
  the longest contiguous prefix, and exposes reuse separately from persistence.
- OpenTelemetry and OpenInference connect retrieval, CrewAI tasks, provider
  calls, and quality checks in one privacy-reduced trace. Local artifacts remain
  authoritative when the collector is unavailable.

## Measured evidence

- **Baseline:** 30/30 end-to-end completions, 26/30 milestone-anchored TRL
  matches, 30/30 formula checks, 30/30 report-structure checks, and 0 unsupported
  numeric lines. This is a revised calibration baseline, not a held-out score.
- **Topology ablation:** 90 paid cells across 1-, 4-, and 6-node workflows. The
  4-node arm used 54.89% fewer median tokens and 47.03% lower median cost than
  the 6-node arm. This supports domain decomposition, not every production node.
- **User utility:** five reviewers completed 20/20 eligible blinded judgments.
  The full workflow won decision usefulness 6:4 in each round but failed the
  pre-registered success rule; the monolith led information gain 11:5.
- **Fault injection:** 30/30 zero-network recovery children completed, skipped
  90 committed task executions, and duplicated 0 task executions.
- **Production recovery:** one post-fix same-revision child reused a four-node
  prefix, made 0 new evidence-agent requests, and completed the suffix. The
  interrupted source's usage was unavailable, so total cost and general savings
  remain uninspectable.
- **Verification:** 1,391 tests plus 627 subtests, Linux/Windows × Python
  3.11/3.12 CI, and 87.01% measured coverage above an 85% floor.

The protocols, row-level artifacts, failed candidates, and caveats are linked
from the [README](https://github.com/shuxiachai/academic-commercialization-agent/blob/v2.0.0/README.md)
and summarized in the
[portfolio case study](https://github.com/shuxiachai/academic-commercialization-agent/blob/v2.0.0/docs/portfolio-case-study.md).

## Breaking changes from v1.0.0

- The Gradio UI and python app.py development path are retired. Start the web
  application with uv run uvicorn api.main:app --reload.
- The HTTP API and persisted run contract are now the supported integration
  surfaces. Consumers of the original UI callbacks must migrate to the FastAPI
  endpoints documented at /docs.
- Public deployment configuration now separates operator-funded access codes,
  BYOK credentials, paid-operation limits, retention, and optional telemetry.
  Review .env.example rather than carrying forward a v1 environment blindly.

## Run locally

    uv sync
    uv run pytest -q
    uv run --with ruff ruff check .
    uv run uvicorn api.main:app --reload

Then open http://127.0.0.1:8000. Real analysis requires one supported LLM key
and one search-provider key; the test suite is zero-network.

## Known limits

- The user-utility panel is small and mostly proxy users; it does not establish
  adoption, ROI, or better real-world investment decisions.
- File-backed run state and paid-operation accounting target one application
  replica. Horizontal scale requires a transactional shared store and queue.
- External provider requests remain at-least-once at interruption boundaries.
- Production supplemental Tool Calling is intentionally disabled until the
  shadow planner demonstrates useful evidence gain at acceptable error, cost,
  and latency.
- Code-package analysis is not implemented. Patent relevance has one human
  label set but no second independent reviewer or inter-rater agreement.
- Precision-first regulator-title recovery covers only exact FDA 510(k) and
  ClinicalTrials.gov URL shapes and is not evidence of title truth.

## Portfolio material

- [Live application](https://academic-commercialization-agent.up.railway.app)
- [One-page case study](https://github.com/shuxiachai/academic-commercialization-agent/blob/v2.0.0/docs/portfolio-case-study.md)
- [90-second demo recording guide](https://github.com/shuxiachai/academic-commercialization-agent/blob/v2.0.0/docs/demo-script-90s.md)
- [Full README](https://github.com/shuxiachai/academic-commercialization-agent/blob/v2.0.0/README.md)
