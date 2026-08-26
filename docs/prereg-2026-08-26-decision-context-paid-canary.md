# Pre-registration: Decision Context three-mode paid production canary

**Frozen:** 2026-08-26T12:14:00Z, before any provider-backed case in this study
**Implementation baseline:** `f0f4baba0f73d7dd986f7571ede6d5d4b8356ad3`
**Execution revision:** the first `main` merge commit containing this protocol
and its manifest; record the full deployed SHA before submission
**Manifest:**
`tests/fixtures/decision_context_paid_canary_manifest.json`
**Manifest SHA-256:** `bd18ecb13f91d0f4dc9a3dde5059259f0d39579a41e6b2d4f62992d2196b63ad`
**Provider calls authorized by this document:** none
**Future paid scope requiring fresh authorization:** at most three sequential
operator-funded root runs, one per frozen case, with no retry or resume
**Soft cost stops requiring fresh authorization:** USD 0.05 per admitted run
and USD 0.12 for the study; one already-admitted run may finish slightly above
either boundary

## Question

On one previously measured topic, does the deployed Writer/Reviewer path obey
the code-derived applicability contract for all three Decision Context modes?

Specifically:

- does an omitted context produce an orientation brief that withholds an
  actor-specific GO/NO_GO conclusion;
- does a partial context expose the missing core fields and still withhold that
  conclusion; and
- does a complete context address the supplied actor and decision while
  emitting one bounded `GO`, `NO_GO`, or `DEFER` conclusion?

This is a prompt-compliance and public-boundary canary. It is not a factual
accuracy evaluation, a user-utility comparison, or evidence that a conclusion
is commercially correct.

## Why this topic was frozen

The exact topic for all three cases is:

> quantum computing for drug discovery

The choice was made from data already on disk, before seeing any report from
this study:

- benchmark case 08 completed 3/3 live runs;
- all three runs produced TRL 4, and all required report sections and scoring
  formulas passed the frozen benchmark checks;
- each run retained eight patent and eight market sources, while academic
  coverage varied from three to seven sources; and
- both separately recruited target users selected case 08 before report
  exposure, retained `DEFER`, and later described actionability and evidence
  trust as weak.

Those observations make the topic inspectable and product-relevant; they do
not establish source truth or make it an easy positive case. Keeping one topic
across all modes reduces an obvious content confound, but retrieval and model
sampling may still vary. This study therefore cannot estimate the causal effect
of Decision Context.

## Frozen requests

The committed manifest is the request authority. No language, weight profile,
paper, BYOK credential, planner option, or recovery request may be added.

| Case | Supplied context | Expected mode | Expected decision authority |
|---|---|---|---|
| `DC01` | none | `orientation` | actor-specific GO/NO_GO prohibited |
| `DC02` | asset description and US jurisdiction only | `decision_context_incomplete` | actor-specific GO/NO_GO prohibited; application, owner, and decision type are missing |
| `DC03` | all seven fields | `decision_support` | exactly one bounded GO, NO_GO, or DEFER conclusion permitted |

The context is synthetic, non-confidential, and intentionally unverified. In
particular, it is user-supplied input rather than retrieved evidence. A report
that silently promotes it to an independently verified fact fails the contract
even if the wording sounds plausible.

## Admission preflight

Paid execution is inadmissible until all of the following are recorded:

1. this protocol and the manifest are merged to `main`, and their exact bytes
   match the SHA-256 above;
2. Railway serves the exact merge revision and `/health/ready` returns HTTP 200
   with `llm`, `search`, `outputs`, and `paid_accounting` all `ok`;
3. the deployed OpenAPI schema still exposes `decision_context` on
   `RunRequest`;
4. one operator access code reaches `/api/access/check` with HTTP 200 without
   the code itself being written to an artifact;
5. the selected owner's run-history baseline and paid-operation ledger state
   are recorded before the first submission; and
6. the user gives fresh authorization for the three root runs, USD 0.05
   per-run soft stop, USD 0.12 study soft stop, and possible small in-flight
   overrun.

Failure of any preflight item means zero requests. A successful access check is
not paid-run authorization.

## Frozen execution protocol

1. Recompute the manifest SHA-256 from committed bytes and validate each body
   through the deployed public request schema.
2. Submit `DC01` exactly once, persist its run id before polling, and wait for a
   terminal state.
3. Inspect its status, progress, report, checkpoint state, source collection,
   evidence-gap shadow artifact, and usage before considering another request.
4. Stop the study if the run fails, cost is uninspectable, observed per-run cost
   exceeds USD 0.05, the deployed revision differs, or any unauthorized child,
   planner call, or supplementary search appears.
5. If the cumulative observed cost is still within the USD 0.12 boundary,
   repeat the same sequence for `DC02`, then `DC03`.
6. Re-read the owner history. The protocol may add no more than three root runs
   and no child runs.
7. Classify every criterion as `pass`, `fail`, `not_inspectable`, or
   `not_observed`. Missing output and a check that did not run are never passes.

Runs are sequential because a total soft stop cannot be enforced when three
full workflows are already in flight. No failed case may be replaced, retried,
resumed, or rerun under another code.

## Acceptance criteria

### Execution and public-boundary contract

1. Every admitted case reports the exact authorized `pipeline_revision`,
   reaches `completed`, creates no recovery child, and commits the ordinary
   seven-node checkpoint sequence without an error.
2. Public status and progress expose the exact `assessment_mode` and
   `decision_gate` frozen for that case in the manifest.
3. Every evidence-gap artifact records zero executed planner/tool calls, zero
   supplementary-search cost, and unchanged accepted-source hashes. A missing
   or failed shadow check is not a pass.
4. Cost is inspectable for every admitted case, no observed case exceeds the
   USD 0.05 per-run soft stop, and cumulative observed cost is no greater than
   USD 0.12. An already-admitted in-flight overrun is reported rather than
   hidden, but still fails the numerical criterion.

### Delivered-report contract

5. `DC01` names `orientation`, explicitly states that actor-specific
   `GO/NO_GO is not assessed`, and does not invent a decision owner, budget,
   timeline, jurisdiction, or success threshold.
6. `DC02` names `decision_context_incomplete`, explicitly states that
   actor-specific `GO/NO_GO is not assessed`, names all three missing core
   fields, and does not infer their values from the topic.
7. `DC03` names `decision_support`, addresses the supplied pharmaceutical R&D
   portfolio committee, target application, and funding decision, and ends
   with one operative `GO`, `NO_GO`, or `DEFER` conclusion whose conditions are
   tied to retrieved evidence.
8. All cases visibly distinguish supplied context from retrieved evidence,
   observed facts from analyst inference, and legal research from an FTO
   opinion. The unverified synthetic asset description must not be presented
   as independently verified.
9. Unsupported budget amounts and success thresholds remain `not established`.
   Only the supplied 90-day decision horizon and 12-month pilot horizon may be
   stated as actor-specific timing without cited evidence.
10. Context unique to `DC02` or `DC03` does not appear in `DC01`; fields absent
    from `DC02` are not silently copied from `DC03`. This is a run-isolation
    check, not evidence that the model has no memory in other architectures.

The primary canary passes only if all three cases are admitted and criteria
1-10 pass. A provider or retrieval failure is an operational failure, not a
prompt-compliance pass. A completed study with one contract violation is a
valid observation but a failed three-mode canary.

## Measurement limits fixed in advance

No person or automated check in this protocol will open the cited papers,
patents, market pages, or regulatory sources. Consequently the following stay
`not_evaluated` regardless of the structural verdict:

- source truth and factual correctness;
- commercial recommendation quality;
- whether `GO`, `NO_GO`, or `DEFER` is the right decision;
- target-user usefulness, adoption, time savings, or ROI;
- causal improvement over topic-only reports;
- performance on other topics, languages, providers, or contexts; and
- whether six agents are necessary.

The result document must preserve failed, partial, over-budget,
`not_inspectable`, and `not_observed` outcomes. Criteria and context values may
not be rewritten after the first provider request.

## Explicit exclusions

This study does not change the scoring formula, the evidence-confidence floor,
the non-blocking uncited-claim screen, prompt caching, source-summary scraping,
CrewAI, checkpoint identity, or the production-disconnected evidence-gap
executor. It adds no model memory and authorizes no autonomous Tool Calling.
