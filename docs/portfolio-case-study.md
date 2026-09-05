# Portfolio Case Study: Evidence-Constrained Commercialization Assessment

[Project](../README.md) · [Current evidence ledger](evidence-status.md) · [Experiment archive](experiment-index.md)

## Problem and product boundary

Commercialization triage combines technical maturity, patents, market signals,
competitors and applicable authority evidence. A plausible narrative is not
enough if its claims, scores and limitations cannot be traced to sources.

This project turns a topic or paper into a cited report and scorecard for
technology-transfer, investment and industry-research scenarios. It supports
research triage; it does not replace technical, legal, regulatory, investment
or freedom-to-operate due diligence. Target-user value remains incompletely
established.

## What is implemented

The production path is an **evidence-constrained six-stage LLM workflow**, not
an unrestricted tool-using autonomous agent:

1. Deterministic retrieval first collects, validates, tiers and deduplicates
   source records into a frozen registry.
2. Academic, Patent and Market specialists analyse that evidence in parallel.
3. A Writer produces the structured cited report.
4. A Reviewer proposes bounded corrections instead of an unconstrained rewrite.
5. A Scorer emits dimension scores; code validates the references and
   recomputes the weighted total.

Optional seven-field Decision Context travels through the immutable RunSpec
and derives applicability. Topic-only inputs remain usable orientation runs;
they are not silently upgraded into actor-specific GO/NO_GO advice. Narrow
threshold and material-family citation screens are advisory, not a universal
semantic correctness oracle.

FastAPI serves a build-free HTML/CSS/ES-module client and shared run artifacts.
The CLI uses the same pipeline. Per-run subprocesses isolate execution;
content-addressed checkpoints bind reuse to input, evidence, configuration,
task and pipeline identity. Recovery creates a new child and revalidates the
longest committed prefix rather than modifying a finished parent.

## Reliability at expensive boundaries

- Run and PDF extraction share concurrency and operator-funded admission.
  Persistent daily quota does not reset with a process restart. BYOK uses
  isolated credentials and still consumes bounded host capacity.
- Run IDs are capability links. Code-owned mutation requires owner/admin
  authority; ownerless BYOK has a distinct, explicitly weaker identity model.
- Write-once terminal records distinguish normal completion from external stop.
  Monotonic snapshots report complete, lower-bound or unavailable usage instead
  of presenting interrupted requests as zero cost.
- OpenTelemetry/OpenInference exposes redacted task/provider traces through an
  optional Phoenix/OTLP collector. Collector failure does not invalidate local
  run artifacts.
- Docker preserves non-root application execution, process supervision and
  embedded CJK PDF fonts. Railway is deliberately a single-replica deployment.

## Measurements that changed decisions

| Evidence | Observation | Engineering decision / limitation |
|---|---|---|
| 30-run baseline | 30/30 completed, 26/30 TRL-range hits, 30/30 formula and structure, zero uncited numeric lines | Keep the calibrated scoring baseline; disclose post-observation range edits and that citation proxies do not establish source truth |
| 90-cell 1/4/6-node ablation | Four-node median tokens -54.89% and cost -47.03% against six-node | Do not claim six nodes were universally necessary |
| Five-reviewer utility audit | 20 eligible judgments; each round decision preference 6:4, but the registered success rule failed | A simple majority is not a positive utility result; only one reviewer was a target user |
| Two-target-user pilot | Both retained DEFER, both MAYBE on reuse; usefulness/information gain medians 3/5, actionability/trust/acceptance 2/5 | Do not claim adoption or measured time savings; estimated revision effort and no external checks limit interpretation |
| Offline recovery | 30/30 children completed, 90 committed tasks skipped, zero duplicate committed-task executions | Local reuse is demonstrated; provider exactly-once is not |
| Real recovery | One child reused four nodes and completed the suffix with no evidence-agent requests | Interrupted-source usage was unavailable; total savings cannot be calculated |
| RTI02 runtime canary | One completed Qwen run, 12/12 primary terminal checks, 69,932 tokens, USD 0.067922 estimate, 885 seconds | Normal browser delivery/accounting observed with a minor polling deviation; not fallback/timeout quality, general latency or an SLO |
| Tool Calling v8 | AC development passed; AD unseen failed routing, closure-role value and incremental coverage | Seal v8 and keep supplementary Tool Calling out of production |

Each row's protocol, exact denominator and method limits are linked in
[the evidence ledger](evidence-status.md). Do not add these denominators together.

The earlier patent candidate is another instructive rejection: it improved
selective precision to 94.6% but removed six relevant patents. That violated
the frozen false-removal gate, so it was not deployed. Negative results are
part of the engineering record, not shortcomings hidden behind a feature list.

## What Tool Calling means in this project

The research implementation includes a bounded execution kernel, strict
one-request adapters, cost/request accounting, source-lock review and frozen
development/unseen harnesses. The [v1–v8 ledger](evidence-status.md#tool-calling-experiments)
shows both provider compatibility and failures in source precision, semantic
agreement, role-coverability and routing value.

Production is still **zero-call shadow mode**. V8's unseen result is final:
routing 5/8, closure-role value 2/7 and coverability gain +1 failed their gates.
A new method needs fresh cohorts and pre-registration; adding another model
pass or tuning AD cannot create independent validation.

## What the tests prove

At the audited pre-consolidation revision `0fdaa76`, 2071 tests and 678
subtests passed. CI spans Linux/Windows × Python 3.11/3.12, latest Ruff, narrow
Pylint, an 85% coverage floor, real Chromium against loopback fixtures and
Docker runtime assertions.

Tests target seams: a correct field stored on disk is insufficient if FastAPI
serialization drops it or the browser never renders it. Regression tests are
checked by re-injecting the original defect. The browser smoke blocks external
and mutating requests, so it cannot stand in for paid-provider or deployed
availability evidence.

## Open work and scope discipline

The next low-cost maintenance seam is auxiliary metadata: some legacy readers
still conflate missing and unreadable values. Qualitative entailment, broader
input-distribution evaluation, cross-topic target-user utility and sustained
adoption remain open. Single-replica state needs redesign before horizontal
scaling; code-package ingestion is unimplemented.

The completed utility panels cannot be enlarged retroactively. Future review
requires a new protocol and honest source-check provenance. More agents,
Kubernetes, memory or a vector store would not by themselves fix these gaps.

## Reproduce

```bash
uv sync
uv run pytest -q
uv run --with ruff ruff check .
uv run uvicorn api.main:app --reload
```

See [the operating guide](operating-guide.md) for credentials and paid boundaries,
[AGENTS.md](../AGENTS.md) for rejected alternatives and [Contributing](../CONTRIBUTING.md)
for the complete CI-compatible check sequence.
