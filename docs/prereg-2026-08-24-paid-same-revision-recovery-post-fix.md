# Pre-registration: post-fix same-revision Railway recovery canary

**Frozen:** 2026-08-24, before any paid source is submitted
**Relationship to earlier canaries:** new repair-validation experiment, not a
retry, amendment, or reinterpretation of either frozen non-pass
**Repair integration:** PR #27, merge commit
`8c1b154f22e989421dd473fef893ffb7b312b7d8`
**Maximum attempts:** one new source run and, only if safely resumable, one
immutable child
**Soft spending stop:** `$0.10` estimated LLM cost across the source and child;
one already in-flight request may finish slightly above the stop

## Why another canary is necessary

The first production canary preserved a same-revision four-node checkpoint
prefix, but its only child admission was rejected by the owner's daily wallet
cap. The independently pre-registered follow-up then created a child and
proved real prefix reuse: retrieval plus all three evidence nodes were
byte-identical, and the reused evidence agents made zero new child provider
requests. That child still failed at the Writer guardrail because recovery
restored validated JSON as raw task context without reconstructing the typed
`EvidenceReport` values used to build the trusted source registry.

PR #27 repairs that exact seam. It reconstructs typed evidence only after
repeating schema and evidence-integrity validation, preserves the original raw
bytes, and fails closed on schema-invalid checkpoint JSON. The defect was
re-injected into the new seam test and reproduced the exact production error
before the repair was restored. Those are zero-network results; they cannot
turn either earlier production non-pass into a pass or establish that the paid
Writer/Reviewer/Scorer suffix now completes.

This canary asks only that remaining question. It is not a general checkpoint
benchmark and will not estimate a production recovery rate.

## Frozen question and hypothesis

After a real Railway process restart occurs only after a durable same-revision
prefix containing retrieval and all three evidence nodes exists, can one
immutable child:

1. reuse that exact validated prefix without new evidence-agent provider work;
2. restore the typed evidence context required by the real Writer guardrail;
3. complete Writer, Reviewer, and Scorer; and
4. publish a non-empty report plus all seven durable checkpoints?

The hypothesis passes only on an end-to-end completion satisfying every
criterion below. A child that merely reaches the Writer, or a report produced
through a cold start, is a non-pass.

## Frozen production revision

The candidate revision is the exact full Git SHA reported by Railway for the
first successful production deployment created by merging the PR that contains
this frozen file. It must contain `8c1b154` as an ancestor. The SHA will be
recorded before source admission and copied into the result artifact; this
protocol will not be edited merely to insert that observed value.

The same candidate SHA, deployment id, image id, and mounted output volume must
remain in use before admission and after the restart. If another revision is
deployed before source admission, the study stops without a paid run and needs
a new pre-registration. If the revision changes after admission, this study is
a non-pass and no replacement source is allowed.

## Frozen input and paid identity

- Topic: `solid-state batteries for electric vehicles`
- Language and weight profile: auto-detect
- Uploaded paper: none
- Provider mode: operator-funded DeepSeek with Railway's configured search
  provider
- Public service:
  `https://academic-commercialization-agent.up.railway.app`
- Required readiness: HTTP 200, `ready=true`, every readiness check `ok`, zero
  active runs, and zero active paid operations

Reusing the earlier topic is deliberate. It reduces retrieval variation while
changing only the recovery adapter under test; it is not a new calibration or
report-quality case.

One dedicated validated operator code must own both source and child. Before
admission, the study owner must confirm that the code has not funded a run or
PDF extraction since the current UTC-day ledger began, leaving at least two of
the configured three admissions available. The code and its hash must not be
written to logs, commands retained as artifacts, screenshots, protocol files,
or results. No admin substitution, alternate owner, or BYOK fallback is
allowed.

## Fixed protocol

1. Obtain separate user authorization for the `$0.10` soft stop and the
   controlled production restart. This pre-registration alone grants neither.
2. Confirm all seven CI jobs passed for the candidate revision. Record the
   GitHub run URL and candidate SHA.
3. Confirm Railway reports the candidate deployment as successful and its
   instance as running. Record deployment, image, instance, commit, and output
   volume identities.
4. Confirm `/health` and `/health/ready` meet the frozen preconditions, then
   perform only the read-only owner-code preflight described above.
5. Submit exactly one new operator-funded source with the frozen topic and
   dedicated code.
6. Poll both public status surfaces. The restart boundary becomes eligible
   only while the source remains `running` and the committed contiguous prefix
   includes `retrieval`, `academic`, `patent`, and `market`.
7. Immediately restart the existing Railway deployment without a rebuild.
   Record every node visible at the boundary. A later contiguous node that
   races to durable commit before shutdown becomes part of the expected prefix
   rather than being discarded from the observation.
8. Wait for readiness and verify the exact candidate SHA, deployment, image,
   and output volume are unchanged.
9. Re-read the source. It must be terminal without completion and expose an
   intact retrieval checkpoint. If it completed, remained running, lost the
   root checkpoint, or reports degraded persistence, stop without a child.
10. Submit exactly one recovery child with the same dedicated code. Do not
    retry a rejected or failed admission.
11. Poll the child to a terminal state. Retain both status surfaces, the report
    response, sources, steps, grounding, scorecard, checkpoint manifests,
    recovery inspection, provider execution evidence, and all available usage.
12. Recheck health and active paid-operation counts after the child terminates.

## Pass criteria

The canary passes only if all conditions hold:

1. The source was running with an eligible committed prefix before restart.
2. Railway returned on the exact frozen candidate revision, deployment id,
   image id, and mounted output volume. A replacement process instance is
   allowed because process replacement is the fault boundary under test.
3. The source became terminal without completion and exactly one child was
   admitted.
4. The child reports `recovery.state=reused`; `reused_nodes` exactly equal the
   longest validated contiguous prefix observed after restart and include
   retrieval plus all three evidence nodes.
5. Every reused LLM node records zero new child provider requests and zero new
   child tokens. Missing execution evidence is `not_inspectable`, not zero, and
   does not pass this criterion.
6. The real Writer guardrail accepts restored typed evidence context; the child
   completes Writer, Reviewer, and Scorer rather than failing or silently
   omitting one of those stages.
7. The child reaches `completed`, serves a non-empty report at HTTP 200, and
   exposes report, scorecard, sources, steps, notes, and grounding artifacts.
8. All seven checkpoints are committed with
   `checkpointing.state=complete`, no checkpoint persistence error, and both
   public status surfaces agree on checkpoint and recovery state.

There is no partial pass. A cold start, mismatched revision, rejected child,
missing execution evidence, incomplete suffix, empty or unavailable report,
or degraded checkpoint state is a non-pass.

## Spending evidence and claim boundary

The `$0.10` value is an operational soft stop, not a pass criterion. The hard
cost controls are one source, at most one child, no paper extraction, and no
retry. The prior completed cold-start child cost `$0.044635`; the prior reused
child reached the Writer for `$0.014576`. Those observations make the stop a
reasonable planning bound, but neither predicts this run.

Interrupted source checkpoint manifests currently carry `usage=null`, so total
source-plus-child cost may remain uninspectable after a restart. If so, the
result must say `not_inspectable`; it must not infer zero source cost, compute a
percentage saving, or treat the soft stop as empirically verified. Any value
visible from an external provider ledger may be reported separately with its
own provenance.

Even a pass supports only one provider-backed observation that the repaired
same-revision path reused one validated prefix and completed its suffix. It
does not establish exactly-once provider execution, a recovery rate, Railway
availability or SLO, latency improvement, general token or cost savings,
report correctness, or the necessity of six stages.

## Abort rules

- No paid request is permitted without a later explicit user authorization.
- No second source, second child, alternate access code, BYOK bypass, or topic
  substitution is allowed.
- Do not restart before the eligible prefix is visible or while another paid
  operation is active.
- Do not change code, configuration, provider, model, search service, or daily
  wallet policy after source admission.
- Do not merge or deploy another revision until the source and child, if any,
  reach the frozen terminal boundary.
- A concurrent user run, inability to prove code budget, unhealthy readiness,
  changed deployment identity, or missing audit surface stops the experiment
  before the next paid action.
- A failed criterion is recorded as a non-pass. It is not repaired in place or
  retried under this protocol.
