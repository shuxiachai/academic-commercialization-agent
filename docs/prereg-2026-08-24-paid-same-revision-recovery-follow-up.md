# Pre-registration: second-code same-revision Railway recovery canary

**Frozen:** 2026-08-24, before the new paid source is submitted
**Relationship to the first canary:** independent follow-up, not a retry or an
amendment
**Production revision:** `f9e3b611779af1e3148cad1d5552758bd67ea274`
**Maximum attempts:** one new source run and, only if safely resumable, one
immutable child
**Soft spending stop:** `$0.10` total estimated LLM cost; one in-flight
request may finish slightly above the stop

## Why this is a separate experiment

The first pre-registered canary ended as a non-pass after its only child
admission was rejected by that owner's daily paid-operation cap. Its result is
frozen in `results-2026-08-24-paid-same-revision-recovery.md` and will not be
rewritten.

The study owner has now supplied a second validated operator code. A code-owned
run cannot change owner identity at recovery, so that code cannot resume the
first source. This follow-up must create a new source owned by the second code
and use that same code for its only child request. Neither the code nor its
hash is retained in study artifacts.

## Frozen question

After a real Railway process restart occurs only after a durable contiguous
checkpoint prefix exists, can a fresh immutable child owned by the same second
code reuse that prefix on the exact same deployed revision and complete the
remaining paid workflow without executing already-validated nodes again?

## Frozen input and preconditions

- Topic: `solid-state batteries for electric vehicles`
- Language and weight profile: auto-detect
- Uploaded paper: none
- Provider mode: operator-funded DeepSeek with Railway's configured search
  provider
- Public service:
  `https://academic-commercialization-agent.up.railway.app`
- Required revision before source admission and after restart:
  `f9e3b611779af1e3148cad1d5552758bd67ea274`
- Required readiness: HTTP 200, `ready=true`, all readiness checks `ok`,
  zero active runs, and zero active paid operations

The topic remains benchmark case 03 so retrieval instability is less likely to
consume the one allowed attempt before the recovery seam is reached.

## Fixed protocol

1. Confirm readiness, zero active work, and the exact Railway deployment
   revision before admission.
2. Submit exactly one new operator-funded source with the second code.
3. Poll both public status surfaces. The restart boundary is eligible only
   while the source is still `running` and the committed prefix contains at
   least `retrieval`, `academic`, `patent`, and `market`.
4. Immediately restart Railway without rebuild. Record every node visible at
   the boundary; an additional contiguous node that races to commit must be
   included in the expected prefix.
5. Wait for readiness, then verify the deployment commit is unchanged.
6. Re-read the source. It must be terminal, not completed, and expose an intact
   retrieval checkpoint. Otherwise stop with no replacement source.
7. Submit exactly one recovery child with the same second code. Do not retry
   any rejected or failed admission and do not use another identity or BYOK.
8. Poll the child to a terminal state and retain both status surfaces, report
   response, checkpoint manifests, recovery inspection, provider execution
   evidence, and usage. Missing evidence is `not_inspectable`, never zero.

## Pass criteria

The follow-up passes only if all conditions hold:

1. The source was running with the eligible committed prefix before restart.
2. Railway and readiness returned on the exact frozen revision.
3. The source became terminal without completion and exactly one child was
   admitted.
4. The child reports `recovery.state=reused`; `reused_nodes` equal the
   longest validated contiguous prefix and include retrieval plus all three
   evidence nodes.
5. Reused nodes are absent from newly executed child provider work. If
   execution evidence cannot establish this, the criterion does not pass.
6. The child completes, serves a non-empty report, and commits all seven
   checkpoints with `checkpointing.state=complete`.
7. Inspectable source-plus-child cost remains within the soft stop except for a
   documented single in-flight overshoot.

There is no partial pass. A cold start, an admission rejection, a completed
source, an invalid checkpoint, an uninspectable execution boundary, or an
incomplete child is a non-pass.

## Abort and claim limits

- No second source or child is allowed.
- No access-code substitution, BYOK bypass, rebuild, or production code change
  is allowed after the source is admitted.
- Do not restart before the eligible prefix is publicly visible.
- Do not merge PR #27 or otherwise deploy a new revision before this follow-up
  reaches a terminal result.
- Even a pass supports only this one provider-backed same-revision recovery
  observation. It does not establish exactly-once execution, a production SLO
  or recovery rate, general savings, report correctness, or six-stage
  necessity.
