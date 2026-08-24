# Node-level checkpoint recovery

Long assessments make several paid provider calls. A process crash after a
validated node used to discard every completed result, so the only recovery
option was a full rerun. The recovery contract now persists validated outputs
at the task boundary and starts an immutable child run from the longest safe
prefix.

This is a runtime reliability feature, not a result cache. It does not change
the six-stage topology, prompts, guardrails, score formula, retrieval rules, or
the benchmark baseline.

## Contract

Every API run writes a non-secret `.run-spec.json` before its worker starts.
The contract freezes the topic, requested language, weight profile, and the
bounded paper contribution (when present). Provider credentials are never
fields in this file; a resumed BYOK run must supply fresh credentials.

After validation, each node publishes a content-addressed payload and a
manifest under `outputs/<run_id>/checkpoints/<node>/`:

```text
retrieval -> academic -> patent -> market -> writer -> reviewer -> scorer
```

The first three LLM tasks still execute in parallel. The order above is the
logical recovery order used by CrewAI's sequential task scheduler.

A checkpoint is reusable only when all of these still match:

- immutable run input and the validated evidence collection;
- the node's explicit task/agent projection and non-secret model identity;
- every declared upstream output hash;
- pipeline revision and UTC collection date;
- manifest schema, output length, content hash, and expected JSON/Markdown
  payload form.

The implementation deliberately projects fields instead of serializing
CrewAI's runtime objects. CrewAI 1.14.7 includes `BaseLLM.api_key` in its model
state, so using its native serializer would put credentials at risk.

## Recovery lifecycle

`POST /api/runs/{run_id}/resume` accepts only a failed, cancelled, or timed-out
run with a readable RunSpec and a committed retrieval checkpoint. It creates a
new run id and never rewrites the failed source. Before the worker starts, the
API copies the source checkpoints into the child's private `.resume-source/`
snapshot; deleting or pruning the parent after the `202` response therefore
cannot invalidate the child.

The worker validates retrieval first and then restores only the **longest
contiguous matching task prefix**. The first missing, mismatched, or corrupt
node ends reuse; that node and every later node execute normally. Arbitrary
non-contiguous reuse was rejected because CrewAI 1.14.7 has no supported
scheduler contract for it and reproducing callback, context, tracing, and
rate-limit semantics would require a second executor.

For the academic, patent, and market nodes, recovery also reconstructs the
`EvidenceReport` object that the live evidence guardrail attaches. It repeats
both Pydantic schema validation and the node-prefix evidence-integrity checks,
while preserving the checkpoint text in `TaskOutput.raw`; CrewAI therefore
receives byte-identical model context and the deterministic Writer guardrail
receives the trusted typed source registry it expects. A JSON payload that
passes storage-format checks but fails this typed validation is reported as
`corrupt` with `payload_schema`, and reuse stops at that node rather than
silently presenting unvalidated raw text as evidence.

Every reused checkpoint is republished into the child, making the child
independently resumable. A Reviewer fallback that merely ships the Writer's
validated draft is not recorded as a Reviewer checkpoint: the review did not
happen. A scorer that completes through the bounded fallback path is committed
because its own guardrail still ran.

## API and credentials

```bash
curl -X POST http://localhost:8000/api/runs/<failed-run-id>/resume \
     -H 'Content-Type: application/json' \
     -H 'X-Access-Code: <the-source-owner-code>' \
     -d '{}'
```

For BYOK, send a fresh complete credential set in the JSON body:

```json
{
  "llm_provider": "deepseek",
  "llm_api_key": "...",
  "serper_api_key": "..."
}
```

Credentials cross only the child subprocess environment. They are absent from
argv, RunSpec, checkpoint manifests, checkpoint payloads, and status files.
Code-owned runs require the same owner code (or the admin code) for mutation;
sharing a read-only capability URL does not grant recovery or deletion rights.
Ownerless BYOK runs have no separate server-side identity, so their random run
id remains their mutation capability and fresh BYOK keys are still required.

Resume admission uses the same global concurrency, BYOK concurrency, and daily
operator-funded limits as a new run. A resume is potentially paid work even
when every node is expected to match, so it never bypasses that boundary.

## Observable states

Both `/api/runs/{id}` and `/api/runs/{id}/progress` expose separate fields:

- `checkpointing.state`: `partial`, `complete`, or `degraded`, plus committed
  nodes and persistence errors;
- `recovery.state`: `not_requested`, `cold_start`, `reused`, or `unavailable`,
  plus the source id, reused nodes, first node still requiring execution, and
  explicit inspection results.

The browser shows reused-stage counts and checkpoint degradation. It offers
the resume action only for a terminal failure that reports a committed
retrieval checkpoint. "No reusable checkpoint" and "recovery not requested"
therefore cannot be mistaken for a successful cache hit.

## Failure boundary

Atomic publication protects an existing checkpoint from torn writes, but this
system does **not** claim exactly-once provider execution. A process can die
after a provider accepted or returned a response and before the validated
output manifest became durable. Retrying that node is at-least-once at the
external provider boundary and can incur one duplicate call.

Checkpoint disk failure is non-blocking for report delivery: a paid,
guardrail-validated report is not discarded because an auxiliary write failed.
The run is marked `checkpointing.degraded` so the loss of future recoverability
is visible rather than presented as success.

## Verification

The zero-network suite covers the storage and client seams separately:

- corrupt, stale, mismatched, and path-escaping manifests;
- contiguous-prefix restoration and child republishing;
- a real pinned CrewAI kickoff whose provider double raises if hydration is
  ignored;
- restored evidence reaches the real Writer guardrail as typed source context;
- schema-invalid evidence JSON fails closed as a corrupt checkpoint instead of
  being reused;
- fresh BYOK isolation and code-owner authorization;
- parent deletion immediately after the API returns `202`;
- a complete worker fault/restart path in which the child executes zero of six
  already-validated LLM nodes;
- propagation of checkpoint and recovery state through both API responses and
  the shipped browser.

The tests prove individual recovery seams without network or model spend. A
separate [pre-registered process fault audit](prereg-2026-08-23-checkpoint-fault-recovery.md)
then exercised the complete worker boundary over ten frozen evidence inputs and
three post-commit crash points. Its [result](results-2026-08-23-checkpoint-fault-recovery.md)
was 30/30 recovered children, 90 committed task executions skipped by children,
and zero duplicated task executions. Parent run-id paths were absent while the
children ran, and all detached parent tree hashes remained unchanged.

That audit used deterministic local task outputs. It establishes the offline
mechanics, not a production recovery rate, provider token/cost reduction,
latency improvement, Railway SLO, or exactly-once execution. Those claims still
require a separately authorized paid fault injection.

### Production observation: cross-revision resume is a cold start

A separately authorized Railway follow-up on 2026-08-24 created one child
from the failed pre-PR-25 run. The child completed the paid workflow, but its
retrieval inspection rejected reuse because `identity.pipeline_revision` did
not match. It therefore reported `cold_start`, reused zero nodes, recollected
8/8/8 sources, and completed in 208 seconds with 102,485 tokens and an
estimated cost of $0.044635.

This closes the post-fix paid startup question and demonstrates fail-safe
cross-revision invalidation. It does not close paid checkpoint reuse or
production fault injection. The exact run ids, artifact checks, and limits
are recorded in
[the production follow-up result](results-2026-08-24-production-checkpoint-follow-up.md).

### Production observation: same-revision restart preserved the prefix

A second pre-registered Railway canary reached a four-node prefix
(`retrieval`, `academic`, `patent`, and `market`) while the source was
still running, then restarted the service without a rebuild. Railway returned
the same deployment, image, instance, and `f9e3b61` revision. After readiness
returned, the interrupted source was failed and both public status surfaces
still reported the exact prefix with no checkpoint errors.

The only recovery request was rejected with HTTP 429 before child creation
because the owner had reached the configured three-operation daily paid cap.
No alternate code, BYOK bypass, replacement source, or retry was used. The
result is therefore a **non-pass** for paid same-revision reuse: it establishes
real restart persistence and fail-closed paid admission, but no child executed
the remaining suffix. The four manifests also stored `usage=null`, so source
tokens and cost are not inspectable and must not be presented as zero.

The frozen protocol, exact timeline, run and deployment identities, and claim
limits are recorded in
[the same-revision canary result](results-2026-08-24-paid-same-revision-recovery.md).

### Production observation: reuse exposed a typed-context seam

An independently pre-registered follow-up used a second validated owner code
for both a new source and its immutable child. After another same-revision
restart, the child reported `recovery.state=reused` with the exact four-node
prefix and `next_node=writer`. Source and child output hashes matched for
every reused node. Child usage recorded zero requests for the academic, patent,
and market agents, then two Writer requests.

The child did not complete. Both Writer attempts failed the final-report
guardrail with `No validated evidence sources are available in task context.`
The live evidence guardrails populate `TaskOutput.pydantic` with validated
`EvidenceReport` objects. Recovery restored the same validated JSON into
`TaskOutput.raw` but did not reconstruct those typed values, while the
final-report guardrail deliberately trusts only typed evidence when building
its allowed-source registry. Raw model context was therefore present, but
guardrail context was empty.

This remains a non-pass for end-to-end paid recovery, despite directly
observing same-revision prefix reuse and zero repeated evidence-agent requests.
Source checkpoint usage remained null, so total experiment cost is also
uninspectable.

The recovery adapter subsequently added typed hydration with repeated schema
and evidence-integrity validation. The regression suite now feeds three
restored production-shaped `EvidenceReport` values into the actual Writer
guardrail, and separately proves that schema-invalid JSON stops reuse as
`corrupt`. This is code-level, zero-network repair evidence only; no post-fix
paid canary has completed the remaining suffix. See the
[frozen production result](results-2026-08-24-paid-same-revision-recovery-follow-up.md)
for the original observation and its claim limits.

### Pending observation: post-fix end-to-end suffix

The next production observation is frozen in the
[post-fix same-revision protocol](prereg-2026-08-24-paid-same-revision-recovery-post-fix.md).
It allows one source and at most one immutable child under a `$0.10` soft
spending stop. The deployed revision and owner identity must remain constant,
and a failed or rejected action cannot be retried. Total interrupted-source
usage may remain uninspectable, so cost is an operational bound rather than a
functional pass criterion.

This protocol has not run. It grants no spending or restart authorization and
does not change the two frozen non-pass results above.
