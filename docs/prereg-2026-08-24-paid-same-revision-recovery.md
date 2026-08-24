# Pre-registration: paid same-revision Railway recovery canary

**Frozen:** 2026-08-24, before either paid operation  
**Study type:** one operator-funded production fault/recovery canary  
**Production revision:** `f9e3b611779af1e3148cad1d5552758bd67ea274`  
**Maximum attempts:** one source run and, only if it is safely resumable, one child  
**Soft spending stop:** `$0.10` total estimated LLM cost; one in-flight request
may finish slightly above the stop

## Question

After a real Railway process restart occurs only after a durable contiguous
checkpoint prefix exists, can a fresh immutable child on the **same deployed
revision** reuse that prefix and complete the remaining paid workflow without
executing the already-validated nodes again?

The offline 30-unit audit already established the storage and worker mechanics.
The earlier production follow-up established only fail-safe cross-revision
invalidation: it reused zero nodes. This canary is intentionally limited to the
one missing provider-backed seam. It is not another reliability benchmark.

## Frozen input and deployment

- Topic: `solid-state batteries for electric vehicles`
- Language: auto-detect
- Weight profile: auto-detect
- Uploaded paper: none
- LLM/search credentials: operator-funded Railway configuration; secrets and
  the access code are never copied into the study record
- Public service: `academic-commercialization-agent.up.railway.app`
- Railway project: `refreshing-solace`
- Railway service: `academic-commercialization-agent`
- Required deployment revision before the source starts and after the restart:
  `f9e3b611779af1e3148cad1d5552758bd67ea274`

The topic is benchmark case 03, which completed three of three frozen baseline
runs and stayed inside its pre-declared TRL interval. Choosing an already
stable retrieval topic reduces the chance that this recovery experiment spends
money while answering a source-availability question instead.

## Fixed protocol

1. Confirm `/health/ready` returns HTTP 200 with `ready=true`, the latest
   Railway deployment is `SUCCESS`/`RUNNING` at the required commit, and no
   other paid operation is active.
2. Submit exactly one operator-funded source run. Poll its public status; do
   not infer progress from elapsed time or UI copy.
3. The fault boundary is eligible only while the source is still `running` and
   `checkpointing.committed_nodes` contains, at minimum, `retrieval`,
   `academic`, `patent`, and `market`. Record the complete observed list; a
   later contiguous node that commits before the restart is allowed and must
   also be accounted for.
4. Immediately request a Railway **restart without rebuild**. This deliberately
   terminates the API and its child worker through the production shutdown
   path. It must not create a deployment with a different commit.
5. Wait for `/health/ready` to recover, then re-read Railway deployment state
   and verify the commit is unchanged.
6. Re-read the source. It must be terminal, not completed, and must retain an
   intact retrieval checkpoint. If it completed before the restart, never
   reached the eligible boundary, or becomes uninspectable, the canary is
   invalid and no replacement source is allowed.
7. Submit exactly one immutable child through
   `POST /api/runs/{source_id}/resume` with the same owner code. No retry is
   allowed if admission or execution fails.
8. Poll the child to a terminal state. Fetch both status surfaces, the report
   endpoint, and persisted checkpoint evidence. Record absent evidence as
   `not_inspectable`, never as zero.

## Pass criteria

The canary passes only if every condition below is observed:

1. The eligible committed prefix was visible before the restart and the source
   was not already terminal.
2. Railway returned to `SUCCESS`/`RUNNING` on the exact same commit, and the
   readiness endpoint returned HTTP 200 after the restart.
3. The source became terminal without reporting a completed assessment, and
   the resume endpoint accepted one immutable child.
4. The child reports `recovery.state=reused`. Its `reused_nodes` equal the
   longest contiguous reusable prefix observed in persisted source manifests,
   include at least `retrieval`, `academic`, `patent`, and `market`, and its
   `next_node` is the first missing task.
5. No node named in `reused_nodes` appears as a newly executed provider node in
   the child evidence. Missing execution or usage evidence makes this criterion
   uninspectable and therefore non-passing.
6. The child reaches `state=completed`, publishes a non-empty report through an
   HTTP 200 endpoint, and finishes with `checkpointing.state=complete` and all
   seven nodes committed.
7. Source plus child estimated cost remains at or below the `$0.10` soft stop,
   except for a documented overshoot caused by a request already in flight.

There is no partial pass. A completed child with zero reused nodes is a
fail-safe cold start, not a successful recovery result.

## Abort and no-retry rules

- Abort before submission if the production revision, readiness, or paid-slot
  checks do not match the frozen conditions.
- Do not restart the service unless the eligible checkpoint boundary is
  visible on the source while it is still running.
- Do not create a child if the source is completed, still running after the
  service returns, lacks a reusable retrieval checkpoint, or the observed
  source cost has already crossed the soft stop.
- Do not start a second source or child to turn an operational failure into a
  cleaner result. The failure is the result.

## Evidence to retain

- source and child run IDs and their public capability URLs;
- UTC timestamps for admission, eligible boundary, restart, readiness return,
  resume admission, and terminal child state;
- Railway deployment and instance IDs plus commit hashes before and after;
- source and child status/progress payloads;
- the persisted checkpoint node list, inspection reasons, and per-node usage
  when available;
- child report HTTP status and report length;
- observed provider requests, tokens, and estimated cost, with missing partial
  source accounting labelled explicitly.

Credentials, owner hashes, raw provider bodies, and absolute host paths are not
study artifacts.

## Claims this canary cannot support

Even a pass does not establish exactly-once provider execution, a Railway SLO,
an incident recovery rate, general token/cost/latency savings, report factual
correctness, or the necessity of six stages. It establishes only that this one
same-revision production restart reused its validated prefix and completed its
remaining suffix under the frozen conditions.
