# Portfolio Case Study: Evidence-Constrained Commercialization Assessment

## The problem

Commercialization decisions require evidence from several domains at once:
technical maturity, patents, market signals, competitors, and regulatory or
clinical milestones where applicable. A general-purpose chat response can be
fast, but it is difficult to audit when a claim, score, or recommendation is
not tied to a source.

This project turns a research topic or paper into a structured, scored
commercialization report. It is designed as a reliability-first decision-support
workflow for technology-transfer, investment, and industry-research scenarios.
It does not replace technical, legal, regulatory, or investment due diligence.

## What I built

The production path is an **evidence-constrained, six-stage LLM workflow**, not
an unrestricted autonomous agent:

Before those stages, deterministic Python retrieval plans the query, collects
academic, patent, market, and applicable authority evidence, validates
identifiers and URLs, assigns provenance tiers, deduplicates records, and
persists a frozen source registry. The LLM workflow then runs:

1. An Academic specialist analyses the frozen literature collection.
2. A Patent specialist analyses the frozen patent collection.
3. A Market specialist analyses the frozen market and authority collection.
4. A Writer produces a report whose inline source IDs must resolve to the
   validated registry.
5. A Reviewer emits a bounded correction plan; code applies exact edits rather
   than allowing an unconstrained rewrite.
6. A Scorer produces a traceable scorecard, while deterministic code validates
   source IDs and recalculates the weighted total.

FastAPI serves the same run artifacts to a build-free HTML/CSS/ES-module client
and the CLI. Each run executes in a subprocess and writes auditable state under
outputs/<run_id>/, so the API, browser, CLI, and recovery path observe the same
source of truth.

## Reliability and production engineering

- Pydantic schemas and task guardrails reject malformed evidence, invented
  source IDs, broken citation registries, invalid report structure, and score
  formula drift.
- Node-level, content-addressed checkpoints bind reuse to input, evidence,
  configuration, task, and pipeline identity. Recovery creates an immutable
  child and revalidates the longest contiguous committed prefix.
- Access-code and BYOK paths isolate credentials, share bounded paid-operation
  admission, and enforce concurrency and daily operator-funded limits before a
  provider call.
- Rate limiting, ownership checks, upload bounds, SSRF-oriented URL validation,
  strict security headers, and retention controls protect the public surface.
- OpenTelemetry and OpenInference connect retrieval, CrewAI tasks, provider
  requests, and post-run checks in one privacy-reduced trace. Local artifacts
  remain authoritative if the collector is unavailable.
- Docker runs as a non-root user with tini; Railway hosts the public demo.

## What I measured

| Evaluation | Result | What it does **not** prove |
|---|---|---|
| Frozen live baseline | 30/30 completed; 26/30 within milestone-anchored TRL ranges; 30/30 formula and structure checks; 0 unsupported numeric lines | Not a blinded held-out accuracy score, and not complete hallucination elimination |
| Topology ablation | 90 paid cells across 1-, 4-, and 6-node workflows; the 4-node arm used 54.89% fewer median tokens and 47.03% lower median cost than the 6-node arm | Supports domain decomposition, but does not prove every production stage is necessary |
| Blinded utility audit | Five reviewers returned 20/20 eligible judgments; both rounds preferred the full workflow 6:4 for decision usefulness | The pre-registered success rule failed; the monolith led information gain 11:5, so this is not proof of six-stage superiority or adoption |
| Offline fault injection | 30/30 immutable children completed; 90 committed task executions were skipped with 0 duplicate task executions | Zero-network process evidence, not an exactly-once, latency, cost-saving, or production-SLO claim |
| Provider-backed recovery canary | One same-revision child reused a four-node prefix, made 0 new evidence-agent requests, and completed the remaining workflow | One observation only; interrupted-source usage was unavailable, so total cost and general savings are not inspectable |
| Bounded Tool Calling contracts | Phase 2 passed 14/14 frozen execution cases; the disconnected Phase 3 generic pilot completed 5/5 requests; Phase 4 passes a 71/71 adapter/executor seam set plus a 50/50 live-runner and source-locked Schema v2 review subset over eight OpenAlex/Lens cases | Production remains zero-call shadow mode: the Phase 3 form declared substantive AI use and only 5/25 candidates relevant; the Phase 4 runner has made no live request, so compatibility, precision and evidence gain remain unobserved |
| Test and CI contract | 1,524 tests plus 627 subtests; Linux/Windows × Python 3.11/3.12; 87.07% measured coverage above an 85% floor; a dedicated Chromium journey exercises the access gate, client admission, run history and report DOM | The browser smoke is loopback-only and blocks mutating requests, so it proves the shipped client/API seam without claiming provider compatibility or deployed-service availability |

The negative results are retained deliberately. For example, the first patent
relevance candidate raised auto-kept precision to 94.6% but falsely removed six
relevant patents, so it was rejected rather than tuned after seeing the labels.
The user-utility study also failed its registered success criterion even though
the full workflow won a simple majority. This distinction is part of the
project's engineering argument: evaluation should be capable of saying no.

## Key decisions and lessons

- **Retrieval before reasoning:** freezing and validating evidence before CrewAI
  reduces tool autonomy, but makes citations, retries, replay, and fault recovery
  auditable.
- **Assertions at system seams:** tests cover whether computed values reach both
  API endpoints and the browser contract, not only whether an internal field is
  correct.
- **Silence is not success:** checks distinguish pass, fail, not_run,
  not_observed, and not_inspectable where a zero denominator could otherwise
  look healthy.
- **Precision before blocking:** heuristic screens report conservatively. The
  uncited-claim detector remains non-blocking because the stored baseline shows
  that its false-positive burden is still too high.
- **Recovery is at-least-once at provider boundaries:** committed local nodes can
  be reused safely, but an interrupted external request cannot be claimed as
  exactly once without provider-supported idempotency.

## Current limitations

- The small utility panel contains only one target-domain user and does not
  establish adoption, ROI, or improved real-world decisions.
- Run state, quotas, and artifacts are designed for one application replica;
  horizontal scaling requires shared transactional storage and a distributed
  work queue.
- Evidence-gap production planning remains shadow-only and issues zero
  supplementary searches. A disconnected five-case pilot passed provider
  compatibility at USD 0.040, but its returned form declared substantive AI
  use and labeled only 5/25 candidates directly relevant. Packet v1 also hid
  the frozen novelty baseline from the reviewer; schema v2 fixes that seam,
  but the old result remains excluded and does not authorize production.
- Code-package analysis is not implemented, and patent relevance has no second
  independent reviewer or inter-rater estimate.
- The completed user-utility audit included only one actual target user. A
  separate two-slot target-user decision pilot is prepared with a pre-report
  baseline and post-report decision. Both Stage 1 baselines have returned and
  both reviewers selected topic 08; owner-coded enum normalization is disclosed
  and Stage 2 AI use is collected separately. Neither Stage 2 follow-up has
  returned, so completed observations and user-value evidence remain zero.

## Reproduce or inspect

- [Live application](https://academic-commercialization-agent.up.railway.app)
- [Architecture and full documentation](../README.md)
- [Topology ablation protocol and result](prereg-2026-08-21-agent-topology-ablation.md)
- [User-utility result](results-2026-08-23-user-utility-audit.md)
- [Target-user pilot pre-registration](prereg-2026-08-26-target-user-decision-pilot.md)
- [Target-user pilot operator guide](target-user-decision-pilot-guide.md)
- [Target-user pilot form-timing erratum](errata-2026-08-26-target-user-pilot-form-enums-and-ai-timing.md)
- [Checkpoint recovery design](checkpoint-recovery.md)
- [Production recovery canary](results-2026-08-24-paid-same-revision-recovery-post-fix.md)

    uv sync
    uv run pytest -q
    uv run --with ruff ruff check .
    uv run uvicorn api.main:app --reload
