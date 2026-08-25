# Evidence-gap live-provider adapter — phase 3 implementation result

**Date:** 2026-08-25
**Status:** **PASS for the production-disconnected adapter and audit contract;
live provider pilot not run**

## Frozen question

Can the phase-2 executor call Tavily through an adapter that performs exactly
one HTTP request, exposes provider request and credit accounting, preserves
malformed result rows as inspectable rejections, and keeps all surviving rows
behind the existing evidence quarantine?

The protocol was committed before the adapter, manifest, or runner was written:
[phase-3 pre-registration](prereg-2026-08-25-evidence-gap-live-adapter-phase3.md).
That protocol does not authorize live requests. No Tavily request was made for
this implementation result.

## Frozen inputs

The disclosed five-case compatibility manifest is:

- `tests/fixtures/evidence_gap_phase3_manifest.json`
- fixture SHA-256:
  `4ee79ec8295c5e51a14fcef78180788be09aaa5102e8e0c6096e0944528339b2`
- maximum provider requests: **5**
- request limit per case: **1**
- conservative accounting rate: **USD 0.008 per observed credit**

| Case | Capability | Collection SHA-256 | Validated plan SHA-256 |
|---|---|---|---|
| L01 | `academic_search` | `29c5f4d7950a1b922181b80d5a030d4f6195fe3e36914eba98516477b8b60e0e` | `edf5fa01ef2602e4784a1c142280a7b1cfb89b8eaba6d7e4d0aa6095bcce2fdc` |
| L02 | `patent_search` | `eb89323dce3f4cd26eeba6c65ca6615192c2d77e5770a01f84292ce34c52e602` | `ebe2eafb2d4edb15bfab92a5ce410682438e29383505f5bf637fc239f6b0af02` |
| L03 | `market_search` | `5d43335e8573f5339b6dcb9082338404cb48b5cc39427864233f4ecbb83269fc` | `77f1799658dfd8eb38ca7e7bbe7b6e07f5cfc4f2092a616014fd79cd7f53e0df` |
| L04 | `authority_search` | `b2602e731706f72a391868c59cf52e10fa90c8d24213f57f39edca111a192412` | `24f47b475c9c2ceea18933c5db5e0d9dd7bcc630f2de56877a9cf524edaf4d09` |
| L05 | `authority_search` | `bf90f23ee209a5047877c6ac613c202fc383e5b29462211dc50cf8d8b9ec1f88` | `6eeb08af683cf1b2a18c312fee0eb7e30c40db88c747299315dd724ac57f3dde` |

Reproduce the zero-network identity check with:

```bash
uv run python evidence_gap_phase3_audit.py
```

Dry-run is the command default. It constructs no provider adapter, reads no API
key, and opens no socket.

## Implemented boundary

The new adapter and runner establish the following implementation facts:

- one adapter invocation calls its injected transport exactly once;
- the default transport follows no redirects and contains no retry loop;
- request bodies force Tavily `basic` search, disable generated answers, raw
  content and images, request usage accounting, and use code-owned domains;
- the API key is read only from an explicit constructor value or
  `TAVILY_API_KEY`; it does not enter request bodies or artifacts;
- a successful response requires both `request_id` and `usage.credits`;
- provider rows are parsed independently, including malformed URL rows;
- candidates plus adapter-rejected rows must exactly cover every provider row;
- provider identity, credits, row rejections, local quarantine decisions,
  latency, cost, trace ID and the one-attempt limit reach `execution.json`;
- accepted rows remain a separate evidence delta and never enter
  `validated_sources.json`; and
- a live execution, if separately authorized, writes `manifest.json`,
  `execution.json`, `candidates.csv` and an initially blank `review.csv` once.

The injected five-case artifact test observed five simulated requests, five
credits, a conservative USD 0.04 total, one adapter-rejected row, five locally
accepted quarantined rows, and zero production connections. These are fixture
values, not provider performance or money spent.

## Failure states

The runner keeps these states distinct:

- missing key, invalid soft stop, existing output path, or identity drift fail
  before any adapter request;
- redirect and non-retryable HTTP failures are not retried;
- a retryable transport failure still receives only one pilot attempt;
- missing usage or request identity makes cost/credits `uninspectable` rather
  than zero;
- observed cost can stop the pilot before the next reserved request; and
- human relevance and novelty remain `not_inspected` until every accepted row
  in `review.csv` is labelled.

## Defect re-injection

Three implementation defects were temporarily reintroduced after the tests were
written:

1. A second call to the injected transport made
   `test_adapter_performs_one_basic_search_and_keeps_secret_out_of_artifacts`
   fail with two observed calls instead of one.
2. Counting only parsed candidates instead of every provider result made
   `test_malformed_provider_rows_are_accounted_without_dropping_valid_siblings`
   fail at the strict response boundary because three rejected rows vanished
   from the provider total.
3. Removing the finite accounting-rate check made the `NaN` and infinity cases
   in `test_invalid_accounting_rate_fails_before_transport` fail before the
   defect was removed.


All three defects were removed. The adapter, phase-3 audit, and phase-2 executor
subset then returned to **46/46 passing**. The complete zero-network suite
passed **1444 tests plus 627 subtests**. CI-equivalent coverage measured
**87.07%**, above the frozen 85% floor. Latest Ruff and the narrow CI Pylint
checks for exception order, unreachable code and undefined names also returned
clean.

## Decision and next gate

The single-request adapter and five-case runner are suitable to merge as a
**production-disconnected compatibility harness**. The production worker still
imports neither the phase-2 executor nor this Tavily adapter. Shadow mode still
performs zero supplementary calls.

The next operation is optional and separately paid: execute the exact five
cases with `--execute-live`, `TAVILY_API_KEY`, a new output directory, and a
USD 0.04–0.05 soft stop after explicit user authorization. The resulting
accepted rows then require complete human review before wrong-source rate or
novel evidence yield can be calculated.

## Explicit non-claims

This implementation result does **not** establish:

- live-provider compatibility or response quality;
- planner trigger precision or autonomous tool selection;
- novel evidence yield or wrong-source rate;
- improvement to any commercialization report;
- production latency, reliability, cost, SLO or adoption; or
- permission to connect supplementary evidence to the report workflow.

The accurate claim at this point is:

> A production-disconnected bounded Tool Calling kernel now has a strict
> single-request Tavily adapter and a frozen, auditable five-case live-pilot
> protocol; production remains zero-call shadow mode.
