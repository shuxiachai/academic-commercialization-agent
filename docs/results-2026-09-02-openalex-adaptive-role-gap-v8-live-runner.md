# Adaptive role-gap closure v8 live-runner implementation result

**Implemented:** 2026-09-02

**Parent protocol:**
[`prereg-2026-09-02-openalex-adaptive-role-gap-closure-v8.md`](prereg-2026-09-02-openalex-adaptive-role-gap-closure-v8.md)

**Live-runner amendment:**
[`prereg-2026-09-02-openalex-adaptive-role-gap-v8-live-runner.md`](prereg-2026-09-02-openalex-adaptive-role-gap-v8-live-runner.md)

**Fixture SHA-256:**
`0be98f249bfd1eaf891cd3c20903b9d6ae4cd2d6431282ee32e82298a2d8ecc7`

**Provider requests made:** 0

**Model calls made:** 0

**Production connection:** false

**AC source value:** `not_evaluated`

## Outcome

The production-disconnected AC01-AC08 write-once runner is implemented. It can
execute the frozen adaptive method, but its default CLI path remains a
zero-network protocol check. No OpenAlex request was authorized or made during
this implementation stage.

The runner preserves the distinction that motivated v8:

- every case spends one frozen anchor request;
- the anchor journal reaches durable storage before routing;
- all five candidate-local role observations are computed by the already
  frozen deterministic router;
- the complete route is persisted before a selected closure may run;
- a no-gap decision explicitly abstains and spends no closure request;
- a search decision can spend exactly one already-frozen role closure;
- the completed adaptive portfolio is persisted before the next case can
  begin; and
- a selected but unspent closure remains partial rather than becoming an
  abstention or a fabricated portfolio.

The same implementation therefore supports a mechanically complete eight-call
run when all anchors contain every role and a mechanically complete sixteen-
call run when every case requires a closure. This variability is planned
behavior, not hidden retry or fallback.

## Identity and authorization boundary

Before output reservation or adapter construction, the runner verifies:

- the frozen challenge bytes;
- ordered AC01-AC08 case, anchor, and forty possible closure identities;
- provider, routing, portfolio, and qualification contracts;
- six behavior-bearing implementation file hashes; and
- the positive soft stop at or below USD 0.02, daily-budget acknowledgement,
  fresh output path, and absence of `OPENALEX_API_KEY`.

The complete manifest is then written before the injected or real adapter is
constructed. The runner records its observed self hash without trying to
create a recursive self lock. A future real run still requires separate owner
authorization naming the exact merged revision and fixture.

The concrete anonymous transport follows no redirects and has no retry loop.
The imported adapter remains the existing one-request OpenAlex boundary. The
runner adds no model, recovery, supplementary search, result-page fetch, or
parallel request path.

## Durable artifacts

A complete synthetic execution produced and validated:

- `manifest.json`;
- one `lane-executions/ACxx--anchor_search.json` per case;
- one `route-executions/ACxx.json` per checked route;
- zero or one `lane-executions/ACxx--role_closure.json` per case;
- one `case-portfolios/ACxx.json` per completed case;
- `execution.json`;
- `provider-rows.csv`;
- `route-decisions.csv`;
- `unique-candidates.csv`;
- `candidate-review.csv`;
- `case-review.csv`; and
- `artifact-index.json` with hashes for every preceding source artifact.

Provider-valid candidates are not semantically filtered. Deduplication uses a
non-empty normalized DOI first and an unambiguous canonical OpenAlex work URL
second. Every occurrence retains its request lane, selected closure role,
provider rank, candidate identity, owner, and deduplication basis. Provider
rejections remain in raw-row accounting.

The route boundary separately retains all observations, checked candidate
counts, matched candidate and signal-group provenance, frozen missing-role
order, action, reason, and selected closure identity. Blank candidate and case
review files expose source, baseline, profile, and route context while leaving
all human labels empty.

## Failure semantics

Focused tests verify distinct behavior for:

- invalid live arguments before output or adapter construction;
- configured-key refusal;
- existing output refusal;
- implementation drift before output or adapter construction;
- provider failure with no retry;
- a schema-valid response that lacks the frozen OpenAlex accounting;
- response idempotency mismatch;
- uninspectable cost;
- soft stop after an anchor, with the checked route retained but no fabricated
  closure or portfolio; and
- strict-GBK CLI output without changing authoritative UTF-8 artifacts.

A response without auditable OpenAlex usage is recorded as
`accounting_invalid` with uninspectable cost. It is not converted to zero cost
and its unaccounted candidates cannot enter the provider-row or source-review
boundary.

## Verification

The new focused suite passes:

```text
19 passed
```

The complete zero-network suite passes:

```text
1928 passed, 657 subtests passed
```

Latest Ruff passes for the runner and tests. The project narrow Pylint gate is
also run before delivery.

Both protocol-mandated defects were re-injected:

1. manifest persistence was moved after adapter construction; the injected
   factory failed because `manifest.json` did not exist;
2. one correctly computed route was dropped from the final route CSV; the
   aggregate boundary failed because seven serialized routes could not satisfy
   the eight persisted decisions.

Both defects were restored, and the focused suite returned to 19/19.

## Interpretation

This stage establishes a bounded, sequential, adaptive, write-once and
inspectable execution contract. It does not establish OpenAlex compatibility
on AC, source relevance, novelty, candidate precision, routing correctness,
closure value, role coverability, gain over anchor-only retrieval, planner
trigger precision, report improvement, user utility, an SLO, autonomous tool
choice, or production Tool Calling.

AC01-AC08 have not been opened. AD01-AD08 remain unseen. A live AC study may
begin only after this implementation is merged and the owner separately
authorizes the exact merged revision, fixture hash, maximum sixteen sequential
anonymous OpenAlex requests, and a provider-reported soft stop no greater than
USD 0.02.
