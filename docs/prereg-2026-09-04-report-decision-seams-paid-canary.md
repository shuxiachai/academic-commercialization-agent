# Pre-registration: report decision seams post-fix paid canary

**Frozen:** 2026-09-04, before any provider-backed run in this study  
**Implementation baseline:** `b7a8731dc2a2c984dec058167fb3c1bdb79e3a24`  
**Execution revision:** the first `main` merge commit containing this protocol
and its manifest; record the full deployed SHA before submission  
**Manifest:**
`tests/fixtures/report_decision_seams_paid_canary_manifest.json`  
**Manifest SHA-256:** `2ca063df38f4cb5f58007d33919e307cde0b6cca288a81501de45aaad0e9a1ca`  
**Provider calls authorized by this document:** none  
**Future paid scope requiring fresh authorization:** one operator-funded root
run, with no operator retry, recovery child, Planner call, or supplementary
search  
**Future soft cost stop requiring fresh authorization:** USD 0.10; one already
admitted request may finish slightly above the boundary

## Question

Does the deployed post-fix pipeline preserve an owner-approved Decision
Context through the final report, both public status endpoints, the browser
summary, and the non-blocking report-audit boundary during one real Qwen run?

This is a delivery-seam regression canary. It is not an independent model
quality study, a source-truth evaluation, or evidence that the supplied
success criteria are technically or commercially correct.

## Why this case was frozen

The exact topic is:

> solid-state sodium-ion batteries using sulfide electrolytes for grid storage
> commercialization

An earlier Qwen production canary on this topic completed end to end but
exposed both failure classes addressed by the P1 implementation:

- orientation-mode prose introduced apparently mandatory numeric decision
  thresholds even though no owner had approved them; and
- a sulfide-electrolyte action criterion cited an oxide-electrolyte source.

Reusing the topic is intentional for regression pressure. It makes this case
neither unseen nor suitable for a generalization claim. The synthetic asset,
decision and thresholds were written before this study's first provider call.
They are request context, not retrieved evidence or recommendations from this
project.

## Frozen request

The committed manifest is the only request authority. It contains one case,
`RDS01`, with all four core Decision Context fields, five optional fields, and
an explicit `owner_approved` declaration for the supplied success criteria.

Expected code-derived state:

| Field | Frozen expectation |
|---|---|
| Assessment mode | `decision_support` |
| GO/NO_GO permission | `true` |
| Missing core fields | none |
| Threshold provenance | `owner_approved` |
| Criteria supplied | `true` |
| Owner approval declared | `true` |

No language, scoring profile, paper upload, BYOK credential, access code,
recovery request, or Planner option is part of the manifest. The access code
used for admission is operational authorization and must never be persisted in
the request fixture or run artifacts.

## Admission preflight

The paid run is inadmissible until all of the following are recorded:

1. this protocol, manifest, and manifest tests are merged to `main`;
2. the committed manifest bytes reproduce the SHA-256 above;
3. Railway reports the exact merge revision and `/health/ready` returns HTTP
   200 with `llm`, `search`, `outputs`, and `paid_accounting` all `ok`;
4. the deployed OpenAPI request schema exposes `success_criteria` and
   `success_criteria_authority`, with the latter restricted to
   `owner_approved`;
5. one operator access code passes the read-only access check without the code
   entering an artifact, URL, or log projection inspected by this study;
6. the pre-run history and paid-operation ledger are recorded before
   submission; and
7. the user gives fresh authorization naming the exact deployed revision,
   chosen access code, one root run, USD 0.10 soft stop, the ban on retry,
   recovery, Planner and supplementary search, and the possible small
   in-flight overrun.

Failure of any item means zero paid submissions. A successful readiness or
access check is not authorization to start the run.

## Frozen execution protocol

1. Recompute the manifest digest from committed bytes and validate the request
   through the deployed public schema.
2. Submit `RDS01` exactly once and persist its run ID before polling.
3. Poll only that root run until a terminal state. Do not replace, retry,
   recover, or resume it after any outcome.
4. Stop without another paid action if revision identity is absent or wrong,
   usage is uninspectable, a Planner/tool call appears, or the run exceeds the
   soft stop after admission.
5. Inspect the terminal status, progress payload, delivered Markdown,
   `report_audit.json`, checkpoints, validated source collection,
   evidence-gap shadow artifact, usage, request count, latency, and owner run
   history.
6. Compare the bounded `decision_gate` and `report_audit` values exposed by
   both status endpoints. Missing output and a check that could not run are
   never passes.
7. Inspect the report manually for the frozen narrow threshold phrases and
   electrolyte-family citation claims, then compare those observations with
   the audit artifact. Do not open external sources or promote this inspection
   to source truth.
8. Classify every criterion as `pass`, `fail`, `not_inspectable`, or
   `not_observed`, and publish the result even when the run fails.

## Primary acceptance criteria: delivery and observability

The post-fix delivery canary passes only if every criterion below passes:

1. The root run reports the exact authorized `pipeline_revision`, reaches
   `completed`, creates no child, and commits the ordinary seven-node
   checkpoint sequence without an error.
2. Every recorded LLM role uses exactly `qwen3.5-plus`; request count, token
   usage, cost completeness, and terminal cost are inspectable.
3. Observed cost is no greater than USD 0.10. A permitted in-flight overrun is
   recorded rather than hidden but still fails this numerical criterion.
4. The evidence-gap record shows zero Planner/tool calls, zero supplementary
   search cost, and no supplementary mutation of the validated source set.
5. The persisted Markdown contains the code-owned applicability block with the
   exact `decision_support` mode, GO/NO_GO permission, and
   `owner_approved` threshold provenance.
6. The supplied success-criteria text is present only where private run input
   or delivered report behavior permits it. Neither public status endpoint may
   repeat that text; both must expose the same bounded authority state.
7. `report_audit.json` exists, is non-blocking, and distinguishes
   `completed`, `partial`, `not_applicable`, and `unavailable` behavior through
   real denominators. Its bounded summary is identical across both status
   endpoints and reaches the browser response seam.
8. Every manually observed in-scope narrow threshold or single-family
   electrolyte citation segment is represented by the audit as checked,
   qualified, mismatched, unverifiable, or not applicable. A missing eligible
   segment fails the seam even if the report otherwise reads well.

## Secondary observation: generated report content

Report content is classified separately so a successfully surfaced warning is
not confused with clean model output:

- `clean_observation`: no unqualified narrow decision threshold and no
  checkable material-family mismatch is observed;
- `caught_observation`: one or more such findings are generated and every one
  reaches the artifact, status, and browser seams;
- `missed_observation`: manual inspection finds an in-scope issue that the
  deterministic audit silently drops; or
- `not_inspectable`: the report or required evidence summary is unavailable.

Only `missed_observation` fails the P1 audit mechanism. A
`caught_observation` still documents a model-output quality problem and must
not be advertised as a clean report.

The supplied owner-approved thresholds must retain their authority and meaning
without being silently tightened. Any additional model-invented gate must be
identified as an analyst proposal, external benchmark, or pending owner
approval; otherwise it is an unqualified content finding even when the audit
catches it.

## Measurement limits fixed in advance

No evaluator in this protocol will verify the technical validity of the
synthetic thresholds or open cited papers, patents, market pages, or regulatory
sources. Therefore this study cannot establish:

- source truth, citation entailment in general, or factual accuracy;
- whether the owner-approved thresholds are scientifically appropriate;
- whether `GO`, `NO_GO`, or `DEFER` is the right commercial decision;
- user usefulness, adoption, time savings, or ROI;
- performance on another topic, language, model, deployment, or context;
- stable latency, cost, availability, or any production SLO; or
- value or readiness of production Tool Calling.

One successful run is one provider-backed boundary observation, not a rate.
The result must retain failed, partial, over-budget, `not_inspectable`, and
`not_observed` states.

## Explicit exclusions

This protocol does not change the scoring formula, evidence-confidence floor,
uncited-claim blocking policy, maturity-language checks, prompt caching,
source-summary retrieval, or CrewAI version. It adds no memory, model repair,
retry, recovery, source filter, or Tool Calling production connection. The v8
unseen Tool Calling failure remains sealed and unaffected.
