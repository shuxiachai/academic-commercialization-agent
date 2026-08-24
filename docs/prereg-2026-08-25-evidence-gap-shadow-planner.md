# Evidence-gap shadow planner — phase 1 pre-registration

**Frozen:** 2026-08-25, before the phase-1 implementation was written
**Production evidence changes authorized:** no
**LLM or search calls authorized by this phase:** no

## Question

Can the existing deterministic retrieval diagnostics identify a small,
auditable set of runs that are eligible for a later evidence-gap planner,
without changing accepted sources, adding provider calls, or presenting an
unperformed check as a pass?

This phase does **not** test whether an LLM can choose a useful tool call and
does **not** test whether supplementary retrieval improves a report. It builds
the contract and observation seam needed to measure those questions later.

## Development-set observation disclosed in advance

The 30 stored calibration runs were inspected before this pre-registration, so
they are a development set, not a held-out evaluation set. Under the current
coverage functions:

- academic source count: minimum 3, median 6, maximum 8;
- patent source count: 8 in every run;
- market source count: minimum 4, median 8, maximum 8;
- no run has a failed retrieval domain;
- component coverage is complete in 30/30 runs; and
- authority coverage is incomplete in 9/30 runs, consisting of three
  biomedical topics repeated three times.

The nine authority cases come from older evidence collections that lack both
regulator and clinical-registry records. Current retrieval already issues
bounded FDA, EMA, and ClinicalTrials.gov queries. A future planner merely
rediscovering those same queries is duplication, not evidence of value.

## Frozen phase-1 gate

A successfully collected `SourceCollection` is eligible only for one or more
of these high-precision signals:

1. an explicitly required authority category is missing;
2. a discriminating compound-topic component is explicitly `incomplete`; or
3. a known retrieval domain is recorded in `failed_domains`.

The following do **not** make a run eligible:

- source count alone;
- `partial` or `unchecked` component coverage;
- a non-applicable authority check;
- an unknown failed-domain label; or
- a fatal pre-collection academic shortage, because no `SourceCollection`
  exists at this seam. A separate pre-collection recovery design would be
  required for that case.

## Phase-1 behaviour

- The feature is disabled unless `EVIDENCE_GAP_SHADOW_ENABLED=true` (or an
  equivalent explicit truthy value) is set.
- Disabled, checked-with-no-gap, eligible, and failed evaluation are distinct
  states.
- The production worker records only eligibility. It does not invoke a planner
  model and does not execute a search tool.
- A strict Pydantic proposal contract allows at most two read-only search
  intents. A proposal is valid only when every intent refers to a real trigger
  and uses a tool authorized for that trigger.
- Valid proposals receive deterministic idempotency keys derived from the
  source-collection hash, tool, normalized query, result bound, and trigger
  ids. This suppresses local duplicate intents; it is not a claim of network
  exactly-once execution.
- An eligible run may produce `search` or `abstain`; `no_gap` is reserved for a
  gate with no signals. Planner parse/validation failure is recorded as
  `failed`, never as `no_gap`.
- The audit records zero executed calls, zero added search cost, and whether
  the source-collection hash changed. Any mutation fails the phase-1 audit.
- The audit artifact and both run-status endpoints carry the same state. A
  missing artifact is not silently described as persisted.

## Phase-1 acceptance checks

The implementation qualifies for merge only if all of the following pass:

1. the existing zero-network suite and Ruff remain green;
2. strict schema tests reject unknown fields, a third intent, duplicate
   intents, invented trigger ids, and unauthorized tool/trigger pairs;
3. a planner exception is exposed as `planner_state=failed`;
4. runtime-disabled mode and runtime-enabled eligibility both make zero tool
   calls and do not mutate evidence;
5. the API status and progress endpoints return the same shadow state;
6. the frozen 30-run audit loads exactly 30 collections, is deterministic,
   executes zero calls, and leaves every input hash unchanged; and
7. a deliberate reintroduction of one contract defect makes its targeted test
   fail before the defect is removed.

## Criteria reserved for phase 2

No production tool adapter is authorized by this document. Before one is
connected, a separately frozen challenge set and planner run must report:

- trigger precision of at least 90%;
- at most two **actual outbound requests**, not merely two logical tool names;
- zero invalid, unregistered, or policy-rejected sources entering evidence;
- wrong-source rate no greater than 5%;
- novel validated evidence in at least 50% of triggered cases;
- complete incremental latency, token, search-cost, rejection, and trace
  accounting; and
- no regression to the existing 30-run calibration outputs when the feature is
  disabled.

Those thresholds are future falsification criteria, not current results.
