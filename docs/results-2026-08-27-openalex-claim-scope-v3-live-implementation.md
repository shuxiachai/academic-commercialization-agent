# Result: OpenAlex claim-scope v3 live harness implementation

**Date:** 2026-08-27

**Result state:** live harness complete; provider and source value
`not_evaluated`.

## Outcome

The production-disconnected V01-V08 claim-scope study now has a write-once
live runner. No provider request was made while implementing or testing it.
The runner exists so a separately authorized execution can be attached to an
exact merged implementation rather than an ad hoc local script.

The default CLI path remains a zero-network dry-run. The live path requires an
explicit flag, a provider-reported soft stop no greater than USD 0.01 and an
acknowledgement of the anonymous OpenAlex daily budget. It refuses to run when
`OPENALEX_API_KEY` is configured.

Production and report connections remain false. `pipeline_worker.py` imports
neither the runner, the V01-V08 preflight, the adapter nor the claim-scope
decision module.

## Durable request boundary

`openalex_claim_scope_live.py` adds the following order and state guarantees:

1. the raw fixture and eight implementation files are hash-checked before an
   output directory or adapter exists;
2. the output path is write-once, and `manifest.json` records every expanded
   collection, validated plan, profile, idempotency key, gate and hash before
   adapter construction;
3. each attempted case owns exactly one outbound request, one deterministic
   trace identity and one persisted monotonic request latency;
4. its `case-executions/Vxx.json` journal is committed before the next case may
   start;
5. every valid provider row reaches a label-blind `ACCEPT` or `ABSTAIN`
   decision, while every malformed row reaches an indexed provider rejection;
6. provider failure, invalid accounting, unknown cost, soft stop and complete
   execution remain distinct states, while the provider summary equals the sum
   of case-journal latencies;
7. `candidates.csv` carries channel-level decision provenance, and
   `review.csv` contains only `ACCEPT` rows with blank human labels;
8. aggregate files receive a final SHA-256 artifact index.

A complete provider run does not imply source value. Fewer than six accepted
cases records `mechanical_gate_failed`; six or more records only
`eligible_for_source_lock`. Both keep `human_review_state=not_prepared` and
`source_value_state=not_evaluated` until a separate provenance-locked human
review applies the remaining novelty and wrong-source gates.

## Frozen implementation identities

The live runner locks these already committed inputs before any request:

- `domain_evidence_search.py`:
  `ae79c38378321f6ce4481e682787ee49f930ec4c34b696d404fcf78d97b2eeab`;
- `evidence.py`:
  `8e9eda3126dc1b81ec5a97e23ecfce8ba64c59a0d77c9a3fb3aec259f07b38c5`;
- `evidence_gap.py`:
  `f2b978ce2af6b4e1d759116466d5a79371e6e4a7e414198b728b427cd93eea25`;
- `evidence_search.py`:
  `2721debe3bb193b8971f8a89db0f4c91342944cb232f1829c02dd8d3780422d0`;
- `openalex_claim_scope.py`:
  `739e165838ff5042ec863c3c510311e737216e8d90804c8d3da5095acce22f16`;
- `openalex_claim_scope_search.py`:
  `070d07ac8c4bcaa32bfbc563513b4034162b012aea1f47ce3208ed06cb085642`;
- `openalex_claim_scope_unseen.py`:
  `6104a060b80bb2126a7cbdb2d1c4eb74ae3a12291a43acda6d5dd14eb271d552`;
- `openalex_precision.py`:
  `7c6e0f2999aae68a9caa042584c886bc5273037a2eaf2e95d80c553b7a503029`.

The V01-V08 fixture remains
`f8084328d56fed9c5b2aaafa1eb2225b0798d30266cc12c34522e1cd1243be86`.

## Verification

Focused live-harness tests:

```text
17 passed in 1.68s
```

Full zero-network suite:

```text
1647 passed, 1 skipped, 609 subtests passed in 15.83s
```

CI-equivalent coverage run:

```text
7067 / 8083 statements covered = 87.43%
1647 passed, 1 skipped, 609 subtests passed
```

The coverage run emitted third-party `ResourceWarning` messages about CrewAI
SQLite connections. It emitted no `UserWarning`, changed no warning policy and
passed the frozen 85% gate.

Static checks:

```text
uv run --with ruff ruff check .
All checks passed!

uv run --with pylint pylint openalex_claim_scope_live.py \
  --disable=all \
  --enable=bad-except-order,unreachable,used-before-assignment,undefined-variable \
  --score=n
exit 0
```

The dry-run verified 8/8 collection, plan, profile and idempotency identities,
the abstract-only request contract, topics/keywords aboutness fields, no
redirects, no internal retry and zero live authority.

## Defect re-injection

After the focused suite passed, manifest persistence was temporarily moved
after adapter construction. The exact full-run seam test failed inside the
injected factory because `manifest.json` did not yet exist. The original order
was restored and all 16 focused tests passed again.

This demonstrates that the test observes the durable request boundary, not
merely a final artifact that could have been written after spending budget.

## What remains unobserved

This result does not establish provider compatibility, candidate precision,
wrong-source rate, novel-evidence yield, report improvement, planner-trigger
quality or production reliability. The next valid step is one separately
authorized execution on the exact merged revision, in a fresh write-once
directory, with no retries and no more than eight single-attempt anonymous
OpenAlex requests. If the six-case mechanical gate passes, source locking and
an eligible human review are still required before any source-value claim.
