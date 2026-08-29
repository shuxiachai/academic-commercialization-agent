# OpenAlex scope-link v4 live result

Date: 2026-08-29

Status: **provider run complete; mechanical gate failed; source value not evaluated**

## Question

Can the frozen W01-W08 scope-link v4 method retain enough candidates from
anonymous OpenAlex to justify a source-locked human review, while preserving
the one-request, write-once and production-disconnected execution contract?

## Authorization and identity

The owner separately authorized this run on merged revision
`678254d66c599402811d04f9b2b91ff6977ac089`. The authorization capped the
study at eight sequential requests and a provider-reported USD 0.01 soft stop,
and prohibited redirects, retries, supplementary search, model calls,
recovery and production connection.

Before any provider request, the zero-network dry-run revalidated:

- the W01-W08 fixture SHA-256
  `f4267c6a79c0bb8a685664de5086e4cfff59ebac1b352cbb56c2277957a55cc3`;
- all eight collection, plan, profile and idempotency identities;
- all nine frozen decision and transport dependency hashes; and
- runner SHA-256
  `bfd0bb7b4e668c56f3acd57a95d87a7fdedcd17699ae0b6d225dd882320de96d`.

The study used anonymous OpenAlex access and no API key. The production worker
and report workflow remained disconnected.

## Observed execution

| Measure | Observation |
|---|---:|
| Authorized cases | 8 |
| Attempted / successful cases | 8 / 8 |
| Requests | 8 |
| Internal retries / redirects | 0 / 0 |
| Provider rows reaching the v4 decision boundary | 64 |
| v4 `ACCEPT` / `ABSTAIN` decisions | 0 / 64 |
| Cases retaining at least one `ACCEPT` | 0 / 8 |
| Provider-reported cost | USD 0.008 |
| Total request latency | 12,938.428 ms |
| Production / report connection | false / false |

All eight case journals were committed in frozen order. The aggregate
candidate CSV contains 64 data rows, while the review CSV contains only its
header because no candidate passed the v4 gate. Sixty-three of the 64
candidate decisions include `missing_scope_link`; this is a description of
the deterministic decision trace, not a human judgment that those sources
were relevant or irrelevant.

## Frozen gate result

The pre-registered mechanical threshold required at least one accepted
candidate in at least 6/8 cases. The observed result was 0/8, so the runner
correctly emitted:

- `review_packet_eligibility=mechanical_gate_failed`;
- `source_lock_state=not_created`;
- `human_review_state=not_prepared`; and
- `source_value_state=not_evaluated`.

No human review packet may be prepared for this run. Human labels could not
rescue the failed all-gates rule, and reviewing the rejected rows would change
the registered study after seeing its outcome.

## Write-once evidence identity

The source directory is
`outputs/2026-08-29-openalex-scope-link-v4-live-678254d/`. It is intentionally
gitignored because it contains complete provider responses. Independently
recomputed aggregate hashes matched `artifact-index.json` byte for byte.

| File | SHA-256 |
|---|---|
| `manifest.json` | `3ea66fdb806efe049cba09b582a8dd99daf5a500c584dbce401b22d413ea630b` |
| `execution.json` | `aff3b692783c695647dede20b5aafbb9a6a5b96baf58b205349ca0cb691eff87` |
| `candidates.csv` | `7e3ae36d1efb02132de241d47bd685117ae4c1c5478d25adeaeeb88498bbcaf3` |
| `review.csv` | `6c89b81c657dc0cfd3c3853c738d132e244f91a54f0ec67aa61853ea08243148` |
| `artifact-index.json` | `2bc4cd8a7d6719c3799521ea0866530be0331bfb233a6af61c261ef69d67c445` |
| `case-executions/W01.json` | `27eac645e068eb064b1fa3e2d775996d707d0830b2e1437ab3ccd369eb14f411` |
| `case-executions/W02.json` | `6576026b30a12e2c93e9c893b322e7bdd0b0ae7a8d96c00bbb3d8a7680bb085c` |
| `case-executions/W03.json` | `042f6047ed075c5b76a7d4d75aaba1a65ca08f4a15385391e24c83e620f284a5` |
| `case-executions/W04.json` | `d230e72c3017ca9781e73e658a4e90160ce182786a7dae0d7c17379e0272ab95` |
| `case-executions/W05.json` | `e72d37f606be6b150aca371546deb64767d4027617717ccb46782b418bc9fa9d` |
| `case-executions/W06.json` | `3c6e6ff6a799bd25039d46dd5c2d2e1e5fa8709138e1e3b61e974b4baa08f913` |
| `case-executions/W07.json` | `41705e6da987a8d040e03ec4aa28703c3f7e1483f38476bb1d8da605089e3509` |
| `case-executions/W08.json` | `f34ec5f2f72956e34ae4d0e2e74f76eacaa9902b1e6731fd77efecb3f4c71e1b` |

## What this establishes

Observed:

- anonymous OpenAlex provider compatibility for the exact eight frozen
  requests;
- complete one-request-per-case persistence and known cost accounting;
- complete delivery of 64 provider candidates to the v4 decision seam; and
- a decisive coverage failure under the frozen v4 method.

Not established:

- whether any abstained source was directly relevant or baseline-novel;
- wrong-source rate, precision, recall or source truth;
- report improvement, planner-trigger precision or user value; or
- production Tool Calling.

## Decision

Scope-link v4 is **not eligible for source review or production connection**.
W01-W08 are now consumed evaluation cases: do not tune on them, rerun them and
call the result validation, or weaken the frozen threshold after observing
0/8. A future method would require a new pre-registered hypothesis and a new
unseen challenge. Until then, the production workflow remains phase-1
zero-call shadow mode and the accurate project claim is a bounded,
production-disconnected Tool Calling evaluation program, not completed
production Tool Calling.
