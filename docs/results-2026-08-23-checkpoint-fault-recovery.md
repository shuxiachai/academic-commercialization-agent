# Result: checkpoint fault-recovery audit

**Run:** 2026-08-23  
**Pre-registration commit:** `2bd0518`  
**Harness commit:** `35cba6e`  
**Result:** **PASS — 30/30 units**  
**Model/API cost:** `$0.00` (deterministic local doubles; exporters and provider
credentials removed from child environments)

## Decision

Retain the node-level checkpoint and immutable-child recovery design. Under the
frozen offline protocol, every hard-terminated worker resumed from exactly the
durable contiguous prefix, no committed task was executed again by its child,
and every child reached the normal terminal worker boundary.

This result closes the offline recovery-mechanics question. It does not close
the production-provider question: no token, dollar, latency, exactly-once, or
Railway recovery-rate claim follows from this audit.

## Protocol actually run

The experiment used the ten canonical `validated_sources.json` files from the
30-run benchmark corpus. Their exact hashes and the pass/fail rules were frozen
in the [pre-registration](prereg-2026-08-23-checkpoint-fault-recovery.md) before
the harness was implemented or executed.

For each fixture, a real `pipeline_worker.main` process was paused after one of
three checkpoint callbacks had returned, then terminated by its controller:

- after `academic` (one committed task);
- after `market` (three committed tasks);
- after `reviewer` (five committed tasks).

The controller copied the checkpoint tree into the child's private
`.resume-source/` snapshot, renamed the parent out of its original run-id path,
and launched a fresh worker. Retrieval, telemetry, and model execution were
replaced with deterministic local doubles. The production checkpoint store,
identity matching, CrewAI hydration seam, status writer, and final artifact path
were not replaced.

## Results

| Boundary | Units | Parent task executions | Child task executions | Committed task executions skipped by child | Duplicate task executions |
|---|---:|---:|---:|---:|---:|
| after `academic` | 10/10 | 10 | 50 | 10 | 0 |
| after `market` | 10/10 | 30 | 30 | 30 | 0 |
| after `reviewer` | 10/10 | 50 | 10 | 50 | 0 |
| **Total** | **30/30** | **90** | **90** | **90** | **0** |

Across all 30 units:

- 30/30 parent processes reached the selected durable manifest and exited
  non-zero after controller termination;
- 30/30 child processes exited zero with `stage=Done` and `done=true`;
- 30/30 recovery records exposed the exact expected `reused_nodes`,
  `next_node`, and per-node `reusable` inspection states;
- 30/30 child execution logs contained exactly the expected suffix;
- 30/30 children finished with all seven manifests and
  `checkpointing.state=complete`;
- 30/30 detached parent trees retained the same content hash before and after
  child execution;
- 0 committed task nodes appeared in both a parent and its child execution log.

The full matrix completed in approximately 2 minutes 19 seconds on the study
machine. The sanitized row-level result is committed in
[`checkpoint-fault-recovery-offline-v1.csv`](../evals/checkpoint_recovery/checkpoint-fault-recovery-offline-v1.csv).
Its final column anchors each row to the ignored local `unit.json` record without
publishing absolute paths, process logs, or the underlying evidence collection.

## Independent recheck and negative control

After execution, `checkpoint_fault_audit.py --check` rebuilt the verdict from
the 30 persisted unit records and returned 30/30 again. The checker never reads
the producer's stored `passed` value when deciding a unit.

The negative control copied one successful record in memory, left its stored
`passed=true`, inserted `market` into the child's execution suffix, and declared
`market` as duplicated. The checker rejected it for both the wrong suffix and
the non-empty duplicate set. The test suite also keeps this defect reinjection
as a permanent regression test.

## Limits

The study deliberately says nothing about:

- a crash after a provider response but before manifest publication;
- real provider timing, token accounting, retry semantics, or cost savings;
- Railway restarts, storage durability, or a production recovery SLO;
- report quality, evidence truth, topology value, or user utility;
- non-contiguous checkpoint reuse.

The next optional evidence step is one separately authorized paid DeepSeek
canary. It should inject the fault only after a durable checkpoint, preserve the
same immutable-child protocol, and report observed calls/tokens/cost rather than
projecting the offline 90-node skip count into dollars.

