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
- fresh BYOK isolation and code-owner authorization;
- parent deletion immediately after the API returns `202`;
- a complete worker fault/restart path in which the child executes zero of six
  already-validated LLM nodes;
- propagation of checkpoint and recovery state through both API responses and
  the shipped browser.

The tests prove recovery mechanics without network or model spend. They do not
yet establish a production recovery-rate, token-saving, or cost-saving claim;
those numbers require controlled fault injection over real paid runs.
