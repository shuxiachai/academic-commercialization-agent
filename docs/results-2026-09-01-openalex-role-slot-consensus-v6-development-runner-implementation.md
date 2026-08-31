# Result: role-slot consensus v6 disconnected development runner

**Implemented:** 2026-09-01, on top of pre-registration commits `488276f`
and `4f3e5fb`.

**Production connection authorized:** no

**Live provider or model calls performed:** none

**Private labels opened:** none

## Outcome

The Y01-Y08 development runner and its exact `qwen3.5-plus` one-request
adapter are implemented, but remain disconnected from the production worker,
report workflow and planner trigger.  The default command is a zero-network
dry-run.  Live mode is limited to the development cohort and still requires a
separate user authorization naming a merged revision, provider, request
ceilings and cost stops.  Z01-Z08 remain unopened.

This phase establishes an inspectable execution contract only.  It does not
establish model compliance, semantic quality, source truth, provider
precision, report improvement, cost stability or completed Tool Calling.

## Implemented boundaries

- The global manifest freezes the raw challenge bytes, eight OpenAlex request
  identities, 24 code-owned judge-template identities and 12 transitive
  implementation hashes before an adapter or credential-capable client is
  constructed.
- Because exact prompts depend on provider-returned source text, every case
  writes its complete provider journal and then its three derived request
  identities before Qwen construction or the first model call.
- OpenAlex and Qwen each use a one-request, no-redirect, no-retry transport.
  A provider or model failure stops the study rather than repairing, retrying,
  switching models or issuing a supplementary search.
- The Qwen wire contract fixes exact `qwen3.5-plus`, top-level
  `enable_thinking=false`, JSON Object mode, temperature zero, 8,000 output
  tokens and a 120-second timeout.  Environment price overrides are disabled.
- Every provider candidate and rejection, every attempted model request and
  safe accounting observation, all expected pass identities, every candidate
  row and every fixed role slot reaches write-once artifacts.
- Empty provider results are represented as checked-but-empty cases and never
  construct the model adapter.  A transport-successful but malformed semantic
  response remains a paid, completed call and becomes an explicit unavailable
  pass without repair.
- OpenAlex and Qwen costs remain separate.  A potentially spending call with
  missing usage makes that provider's total `uninspectable`; it can never be
  serialized as zero.

## Findings caught during implementation

The first focused run found two implementation defects without changing a
test expectation:

1. a provider failure before model planning omitted the explicit empty
   `model_calls` tuple from its durable case state; and
2. fixture-byte drift escaped as the phase-one preflight exception instead of
   the development runner's public error type.

Both were fixed at the failure boundary.  The first failure now serializes a
complete provider-failed case without implying model work, and the second is
wrapped without losing its original cause.

## Defect re-injection

The two pre-registered paid-boundary defects were deliberately restored one at
a time after the implementation passed:

1. Moving `manifest.json` persistence after provider-adapter construction made
   `test_complete_execution_persists_every_seam_and_actual_candidate_order`
   fail at the factory boundary because the manifest was absent.
2. Dropping Y08 only from the final `case-audits.json` aggregate made
   `test_malformed_semantic_json_is_accounted_unavailable_and_reaches_clients`
   fail even though the execution object and per-case audit still contained
   the correct value.

Each defect was reverted immediately, and both exact tests passed again.  This
demonstrates that the tests cover capability ordering and the final client
artifact, not merely internal fields.

## Verification

- Default zero-network dry-run: 8/8 Y cases, 8 provider identities, 24 distinct
  judge-template identities and 12/12 implementation hashes verified; no
  adapter, socket or model call constructed.
- Combined v6 kernel, preflight, adapter and runner subset: 39/39 tests passed.
- New runner/adapter subset: 16/16 tests passed.
- Full zero-network suite: 1,837 tests and 657 subtests passed.
- Latest Ruff: passed for the new implementation and tests.
- CI-equivalent narrow Pylint: passed.

No paid or anonymous OpenAlex request, Qwen request, private-label read,
review aggregation, production import or planner-trigger study occurred in
this phase.

## Next authorized step

After this implementation is reviewed, merged and deployed, a separate
authorization may permit one bounded Y01-Y08 development run.  That
authorization must name the exact merged revision, anonymous OpenAlex and
exact `qwen3.5-plus`, at most eight OpenAlex requests and 24 sequential model
requests, provider-specific soft stops, and the prohibition on retry, repair,
fallback, recovery, supplementary search and production connection.

The returned development artifacts must then be mechanically checked before a
label-blind source-review packet is prepared.  Z01-Z08 cannot be opened unless
all pre-registered Y gates, including eligible human review, pass.
