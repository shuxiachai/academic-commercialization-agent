# Result: role-slot consensus v6 zero-network implementation

**Date:** 2026-09-01

**Pre-registration commit:** `e93d792`

**Production connection:** false

**OpenAlex requests:** 0

**Model calls:** 0

**Private labels opened:** no

## Outcome

The candidate-local role-slot v6 decision kernel and frozen Y/Z preflight are
implemented and remain production-disconnected. This establishes only that the
new contract is mechanically testable without network or paid-provider access.
It does not establish that Qwen will follow the contract, that OpenAlex will
return useful candidates, that the method passes its human-value gates, or that
Tool Calling is ready for production.

The pre-registration was committed before implementation. The frozen fixture
contains eight new development cases, Y01-Y08, and eight new unseen cases,
Z01-Z08. Its raw bytes remain:

`f07c457f81fc5b198cb180874895410a4502b9fe3558c9e21c8b42a1f8240c85`

W01-W08 and X01-X08 were not reused. No historical v5 source, response, label
or decision enters the v6 preflight.

## Implemented boundary

`src/academic_agent/openalex_role_slot.py` implements:

- provider, reverse-provider and candidate-SHA order inputs;
- a prompt that exposes title, abstract, candidate identity, role kind,
  description and positional slot, but no provider metadata, human labels,
  role IDs or candidate-action field;
- strict `SUPPORTED`/`ABSTAIN` role-slot proposals;
- top-level failure states distinct from candidate-row and role-slot failures;
- candidate-local handling of missing, duplicate, unknown or malformed rows;
- slot-local handling of missing, duplicate, reordered, malformed or
  unverifiable slots;
- exact title/abstract quote verification with layout-only normalization;
- deterministic two-of-three role consensus;
- code-derived provisional and final candidate dispositions;
- deterministic set cover of at most three sources; and
- one serialized audit containing all three passes, every expected candidate,
  every role slot, local-valid-row and order-unanimity metrics, all consensus
  roles and all selected-source roles.

`openalex_role_slot_unseen.py` verifies the raw fixture hash before JSON
parsing, validates all 16 case/query/profile identities, and expands separate
development and unseen Evidence-gap plans. Each cohort exposes eight distinct
provider idempotency keys and 24 distinct judge-request-template identities.
The module imports no provider adapter, model adapter or execution client.

Current file identities are:

| File | SHA-256 |
|---|---|
| `src/academic_agent/openalex_role_slot.py` | `166eb6d6568a7a187e2f6654c27d3db938a79553c0205501d9328b38437ed8d4` |
| `openalex_role_slot_unseen.py` | `3bd69fa0a6703c1b928c905fbde1ce5639aaa3559c2a54f3356cbdb914800a75` |
| `tests/fixtures/openalex_role_slot_v6_challenge.json` | `f07c457f81fc5b198cb180874895410a4502b9fe3558c9e21c8b42a1f8240c85` |
| `tests/test_openalex_role_slot.py` | `dded711c853e0f6c8ba64112ff29af8079a6027e0ea937018d0739489c459149` |
| `tests/test_openalex_role_slot_unseen.py` | `ba793a810529dc3596b162aebd32ab8649cf19ae6a0454d5cf3337113e98fea2` |

These hashes describe this offline implementation record. A future runner and
adapter must freeze their own committed dependency set before any live call;
this result does not pre-authorise those missing components.

## Verification

The focused v6 suite passed:

```text
23 passed in 2.03s
```

The complete zero-network suite passed:

```text
1821 passed, 657 subtests passed in 35.38s
```

Latest Ruff passed the kernel, preflight and both test modules. The CI-matched
narrow Pylint gate passed the two implementation modules with no output.

Three protocol-mandated defects were re-injected and then reverted:

1. restoring whole-batch invalidation for one malformed candidate changed the
   valid neighbouring row to `pass_unavailable`; the candidate-isolation seam
   failed as required;
2. serializing only required roles after computing required, scope and
   supporting roles triggered `selected source must deliver every deterministic
   KEEP role` at the case boundary; and
3. restoring the later Sydney `2026-09-01` access date while the validator clock
   was frozen to UTC `2026-08-31` reproduced the cross-platform CI failure before
   the globally elapsed UTC date was restored.

After restoration, all 23 focused tests passed again. These checks cover three
high-risk seams: unrelated values being discarded together, correct internal
values never reaching the audit consumer, and deterministic artifact metadata
changing validity across local and CI calendar zones.

## What is still missing

v6 is not ready for a paid run or production connection. The next separately
reviewed implementation phase must add a write-once development runner and a
strict one-request Qwen adapter profile while reusing the existing anonymous
OpenAlex response contract. Before client construction it must freeze the
prompt, parser, quote verifier, consensus, selector, runner, adapter and every
transitive decision dependency. It must persist the complete manifest before
any request and each provider/model journal before a later request.

Only after that runner passes its own zero-network seams may the owner
separately authorise Y01-Y08. A complete Y run would permit at most eight
anonymous OpenAlex requests and 24 sequential `qwen3.5-plus` calls. Z01-Z08
remain unavailable until every frozen Y gate passes. No live request is
authorised by this result.
