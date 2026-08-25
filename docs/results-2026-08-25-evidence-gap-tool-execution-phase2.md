# Evidence-gap bounded Tool Calling execution ¡ª phase 2 result

**Date:** 2026-08-25
**Status:** **PASS for the offline execution contract; not production-connected
Tool Calling evidence**

## Frozen question

Can a validated phase-1 evidence-gap plan drive no more than two read-only
adapter attempts while keeping every returned row outside the original
`SourceCollection` until it passes URL, domain, relevance, deduplication, and
source-registration checks?

The protocol was frozen before the executor and challenge fixture were written:
[phase-2 pre-registration](prereg-2026-08-25-evidence-gap-tool-execution-phase2.md).

## Inputs and method

The audit uses one strict JSON fixture with 14 adversarial cases. It injects
deterministic local adapters for `academic_search`, `patent_search`,
`market_search`, and `authority_search`; no adapter opens a socket, calls a
model, or reads a provider credential.

Each case is executed twice from a fresh `SourceCollection`. The complete
audit payload must be byte-equivalent across the two replays after excluding
wall-clock `latency_ms`, which is telemetry rather than identity. The first
replay is compared with the exact answer frozen in the fixture.

Fixture:

- `tests/fixtures/evidence_gap_phase2_challenge.json`
- SHA-256:
  `e75cf412ebdb03528753a5748ca71f6e732e066d332585be0def3879b7e5179a`
- design:
  `synthetic_adversarial_contract_not_production`

Reproduction:

```bash
uv run python evidence_gap_phase2_audit.py \
  --fixture tests/fixtures/evidence_gap_phase2_challenge.json \
  --output outputs/evidence-gap-phase2-contract-<new-id>
```

The output directory must not already exist. The audit writes `summary.json`
and `cases.csv` once rather than silently replacing an earlier measurement.

## Result

| Measure | Observed |
|---|---:|
| Exact frozen dispositions | **14/14** |
| Deterministic replays outside latency | **14/14** |
| Canonical-replay simulated adapter attempts | **15** |
| Maximum attempts in any case | **2** |
| Valid candidates registered into the separate delta | **6** |
| Unexpected candidates registered | **0** |
| Production connection | **false** |
| Real network/model/provider calls | **0** |

The second deterministic replay repeated the same 15 simulated attempts, so
the complete local audit exercised 30 adapter invocations. The cost values are
synthetic accounting fixtures; they are not money spent and are not a
production cost estimate.

## Covered seams

| Case | Frozen observation |
|---|---|
| C01 | A valid academic record becomes quarantined source `A2` |
| C02 | Existing URL, DOI, and normalized title are each rejected |
| C03 | Literal-IP, credentialed, file, untrusted, and wrong-domain URLs are rejected |
| C04 | An allowed-host but off-topic academic record is rejected |
| C05 | A valid patent is retained while a DOI record returned by the patent tool is rejected as `wrong_evidence_domain` |
| C06 | A valid reputable-market record reaches the same registration seam |
| C07 | A requested FDA regulatory record is retained as market-domain evidence |
| C08 | A clinical-registry record cannot satisfy a regulatory trigger |
| C09 | One retryable failure consumes the first slot; the second and final attempt succeeds |
| C10 | A clean zero-result response is `incomplete`, not evidence success |
| C11 | A malformed response is failed with cost `uninspectable`, not free |
| C12 | A missing adapter fails before any request and is not reported as a clean empty result |
| C13 | Two planned calls receive one attempt each; the first cannot consume the second call's slot |
| C14 | Adapter mutation changes the input hash and invalidates the entire accepted delta |

Plan validation also rejects queries that widen scope: every query must overlap
the original topic, and component or authority searches must name their
specific missing component or category.

## Defect re-injection

Two defects were deliberately reintroduced after the tests were written:

1. Raising the global request budget from two to three made
   `test_two_planned_calls_each_keep_one_slot_and_cannot_retry` fail because
   the first adapter executed twice instead of once.
2. Adding `untrusted.example` to the academic host allowlist made
   `test_untrusted_candidate_urls_never_reach_evidence` fail because an
   invalid row reached `accepted_sources`.

Both defects were then removed, and the execution/audit subset returned to
24/24 passing. This checks that the new tests detect the relevant seams rather
than merely restating current field values.

## Decision

The bounded executor, strict adapter schema, query-scope authorization,
quarantined evidence delta, and zero-network audit are suitable to merge as an
**experimental production-disconnected kernel**.

The production worker remains on phase-1 shadow behavior:

- no planner model is injected;
- no supplementary search adapter is instantiated;
- `validated_sources.json` is unchanged; and
- the six-stage report workflow receives no phase-2 evidence delta.

## What this result does not establish

This audit does **not** measure:

- planner trigger precision;
- live-provider response validity or wrong-source rate;
- novel evidence yield on real gaps;
- report-quality improvement;
- production latency, cost, reliability, or SLO;
- whether Tool Calling should be enabled by default.

A separately pre-registered provider-backed experiment is still required.
Until it satisfies the phase-1 production thresholds, the accurate project
claim is:

> A bounded Tool Calling execution kernel was validated offline; production
> remains zero-call shadow mode.
