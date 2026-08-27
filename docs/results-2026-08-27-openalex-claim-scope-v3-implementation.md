# Result: OpenAlex claim-scope v3 implementation and unseen preflight

**Date:** 2026-08-27

**Result state:** implementation complete; provider and source value
`not_evaluated`.

## Outcome

The production-disconnected claim-scope v3 candidate is implemented together
with a byte-frozen V01-V08 preflight. The implementation addresses the two
mechanical observations from precision v2 without treating unlabelled rows as
truth:

1. the request contract uses `filter=has_abstract:true` so missing-abstract
   works do not intentionally consume the eight bounded result slots;
2. OpenAlex topics and keywords are retained as scored, auditable aboutness
   signals that may bridge at most one required concept.

At least one required concept must still match source text, at least one must
match the title, and provider labels alone cannot authorize a candidate. Every
decision preserves channel-level match provenance and emits only `ACCEPT` or
`ABSTAIN`.

No provider request was made. No API key was read. No production or report
workflow import was added.

## Added boundaries

- `src/academic_agent/openalex_claim_scope.py`: deterministic claim-scope
  profile, provider aboutness schema, candidate identity and explainable gate;
- `src/academic_agent/tools/openalex_claim_scope_search.py`: anonymous,
  injected-transport, one-invocation OpenAlex adapter with complete row and
  reported-cost accounting;
- `tests/fixtures/openalex_claim_scope_v3_challenge.json`: V01-V08 queries,
  profiles, request contract and unchanged human-value gates, locked at
  SHA-256
  `f8084328d56fed9c5b2aaafa1eb2225b0798d30266cc12c34522e1cd1243be86`;
- `openalex_claim_scope_unseen.py`: zero-network fixture validation and
  deterministic collection/plan/profile/idempotency expansion;
- three focused test modules covering the decision, outbound HTTP seam and
  preflight identity boundary.

The adapter deliberately duplicates the small amount of response parsing it
needs instead of modifying the frozen Phase 4 adapter. Changing that older
implementation would invalidate the hash lineage attached to completed and
unexecuted Phase 4 studies.

## Verification

The zero-network dry-run produced:

- 8/8 ordered V01-V08 cases;
- eight distinct source-collection hashes;
- eight distinct validated-plan hashes;
- eight distinct profile hashes;
- eight distinct idempotency keys;
- `result_limit=8`, `has_abstract:true`, topics + keywords, no redirects and no
  internal retry;
- `real_network_calls_performed=false` and
  `live_provider_requests_authorized=false`.

Focused tests:

```text
16 passed in 1.52s
```

Full zero-network suite:

```text
1630 passed, 1 skipped, 609 subtests passed in 21.10s
```

CI-equivalent coverage run:

```text
7067 / 8083 statements covered = 87.43040950142274%
```

Static checks:

```text
uv run --python 3.12 --with ruff ruff check .
All checks passed!

uv run --python 3.12 --with pylint pylint src/ ui/ api/ \
  --disable=all \
  --enable=bad-except-order,unreachable,used-before-assignment,undefined-variable \
  --score=n
exit 0
```

The first default-temp full test attempt failed during fixture setup because
Windows denied access to
`C:\Users\shuxia\AppData\Local\Temp\pytest-of-shuxia`. No test body had
failed. Re-running with a worktree-local `--basetemp` executed the complete
suite successfully; no warning was ignored and no assertion was changed.

## Defect re-injection

After the outbound seam passed, the implementation was temporarily changed
from `filter=has_abstract:true` to `filter=has_fulltext:true`. The exact test

`test_adapter_uses_one_abstract_filtered_request_and_preserves_aboutness`

failed at the parsed HTTP query boundary:

```text
assert ['has_fulltext:true'] == ['has_abstract:true']
```

The defect was then reverted and all 16 focused tests passed again. This shows
the test observes the request that reaches the transport, not merely a profile
or fixture field.

## What remains unobserved

This implementation result establishes schemas, deterministic authorization,
request shape, accounting and fail-closed behavior only. It does not establish:

- OpenAlex compatibility for this new selected-field combination;
- that `has_abstract:true` eliminates every abstract rejection;
- precision, recall, wrong-source rate or novel-evidence yield;
- report improvement or planner-trigger quality;
- production reliability, user value or commercial benefit.

A later live study requires a separate explicit authorization, a new
write-once output directory, frozen implementation hashes and at most eight
single-attempt requests. Its output must remain disconnected until an eligible
human review passes all pre-registered source-value gates.
