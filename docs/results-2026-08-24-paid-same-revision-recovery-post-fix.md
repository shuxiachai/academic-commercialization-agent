# Result: repaired same-revision recovery completed end to end

**Date:** 2026-08-24  
**Pre-registration:**
[`prereg-2026-08-24-paid-same-revision-recovery-post-fix.md`](prereg-2026-08-24-paid-same-revision-recovery-post-fix.md)  
**Pre-registration commit:** `0f95c9b`  
**Repair integration:** PR #27, merge commit
`8c1b154f22e989421dd473fef893ffb7b312b7d8`  
**Production revision:** `682c892244d8b526e8a0bb27dece2beca88be0c8`  
**Source run:** `20260824T104449Z-00b232a5653883ba60afa9823050ccd0`  
**Child run:** `20260824T104647Z-83eb8ced32a82babeef51b5a4c25c540`  
**Result:** **PASS — the immutable child reused four validated nodes and
completed Writer, Reviewer, and Scorer**

## Decision

This provider-backed canary passed every frozen functional criterion. A source
run reached the exact same-revision prefix `retrieval`, `academic`, `patent`,
and `market`. Railway then restarted the existing production deployment
without a rebuild. The interrupted source retained that prefix, and the only
authorized recovery child reported `recovery.state=reused`, executed no new
academic, patent, or market provider requests, completed the three-node suffix,
served a non-empty report, and committed all seven checkpoints without a
persistence error.

This closes the narrow production question left by the two earlier non-passes:
the repaired typed-evidence hydration path can carry a real reused prefix
through the existing Writer guardrail and complete the workflow. It is one
successful canary, not a recovery-rate study.

## Relationship to the frozen non-passes

The [first same-revision canary](results-2026-08-24-paid-same-revision-recovery.md)
preserved a four-node prefix through restart, but its only child admission was
rejected by the owner's daily paid-operation cap. The independently frozen
[second-code follow-up](results-2026-08-24-paid-same-revision-recovery-follow-up.md)
then proved exact prefix reuse and zero repeated evidence-agent work, but its
child failed because checkpoint hydration restored raw evidence JSON without
the typed `EvidenceReport` values required by the Writer guardrail.

PR #27 repaired that exact seam. Reused evidence is now reconstructed as typed
context only after schema and evidence-integrity validation, while its original
raw bytes remain the model context. The earlier outcomes remain non-passes;
this result is a separately pre-registered post-fix observation and does not
rewrite them.

## Preconditions

Immediately before source admission:

- all seven GitHub Actions jobs for revision `682c892` were green;
- `/health` reported zero active runs and zero active paid operations;
- `/health/ready` returned `ready=true`, with LLM, search, outputs, and paid
  accounting all `ok`;
- the dedicated owner code authenticated successfully and its scoped history
  contained zero earlier runs;
- Railway deployment `7eb6d809-3f81-4677-ac0f-2688ad97be5e` was `SUCCESS`,
  with image
  `sha256:40d3e859e2a82139c30662b141bbdbad7bf8a3f1ed9ef66c7fb12e59931ac379`,
  one running instance, and `/app/outputs` mounted; and
- the deployed commit was the frozen repair revision
  `682c892244d8b526e8a0bb27dece2beca88be0c8`.

No production configuration, deployment identity, image, owner identity, or
topic changed after source admission. No retry, alternate code, replacement
source, BYOK bypass, or second child was used.

## Observed sequence

1. The source was admitted between `10:44:49.1545166Z` and
   `10:44:49.5254126Z` for the frozen topic, `solid-state batteries for
   electric vehicles`.
2. At `10:46:23.9942442Z`, both public run surfaces showed the source still
   running at `Agent 4 — Report Writing`, with 8 academic, 8 patent, and 7
   market sources. They agreed on `checkpointing.state=partial`, the exact
   four-node prefix, and no persistence errors.
3. Railway accepted the single no-build restart at
   `10:46:23.9971932Z`. Readiness was recorded again at
   `10:46:46.2896956Z`. Deployment id, commit, image, instance id, and output
   volume mount were unchanged.
4. The source became `failed` at the Writer stage and still exposed the exact
   four-node prefix with no checkpoint errors.
5. The only child was admitted between `10:46:47.8028995Z` and
   `10:46:48.2037849Z`.
6. The child reported `recovery.state=reused`, the exact four reused nodes,
   four `reusable` inspections, and `next_node=writer`; Writer was correctly
   reported as missing and therefore required execution.
7. The child reached `completed` / `Done` in 102 seconds. It committed
   retrieval, academic, patent, market, writer, reviewer, and scorer, with
   `checkpointing.state=complete` and no persistence errors.
8. The report endpoint returned HTTP 200 with 33,081 UTF-8 bytes. Report,
   scores, sources, notes, steps, grounding, and consistency artifacts were all
   exposed.
9. Final health again reported zero active runs and zero active paid
   operations.

## Provider execution and cost evidence

The completed child's usage artifact was internally complete:

| Stage | Requests | Tokens | Estimated cost |
|---|---:|---:|---:|
| Academic | 0 | 0 | $0.000000 |
| Patent | 0 | 0 | $0.000000 |
| Market | 0 | 0 | $0.000000 |
| Writer | 1 | 22,813 | $0.008013 |
| Reviewer | 2 | 42,165 | $0.018430 |
| Scorer | 1 | 23,802 | $0.007150 |
| **Child total** | **4** | **88,780** | **$0.033593** |

The three reused evidence agents therefore performed zero new child provider
work, while every required suffix stage did execute. The child estimate uses
the repository's built-in May 2026 price table.

The interrupted source exposed `usage=null`. Total source-plus-child usage and
cost are therefore **`not_inspectable`**. The `$0.033593` child value is not the
experiment total, and the `$0.10` authorization was an operational soft stop,
not an empirically verified cost ceiling or a pass criterion. No percentage
token, cost, or latency saving can be computed from this observation.

## Pre-registered criteria

| Frozen criterion | Observation | Result |
|---|---|---|
| Eligible four-node prefix visible while source ran | Both public surfaces agreed; no checkpoint errors | pass |
| Same deployment revision survives the no-build restart | Deployment, commit, image, instance, and volume were unchanged | pass |
| Source terminates without completion and exactly one child is admitted | Source failed at Writer; one child only | pass |
| Child validates and reuses the exact contiguous prefix | `reused` with four reusable inspections and `next_node=writer` | pass |
| Reused evidence agents perform no new child provider work | 0 requests and 0 tokens for all three | pass |
| Typed evidence reaches the Writer and the suffix completes | Writer, Reviewer, and Scorer all committed | pass |
| Child completes and serves all required artifacts | `completed`; report HTTP 200; required artifacts present | pass |
| All seven checkpoints are committed and both surfaces agree | `complete`, seven nodes, no errors | pass |

The aggregate functional result is **PASS**.

## Report-quality observations are not recovery criteria

The deterministic quality review passed, and consistency reported zero
blockers and zero warnings. Claim grounding completed, but it checked only one
claim, marked zero as ungrounded, and left five market claims unverifiable.
That is an explicit coverage limitation, not evidence that every report claim
was verified and not a reason to reinterpret the recovery criterion.

## Evidence-retention limitation

The local audit bundle retains the source and child status/progress responses,
admission and restart boundaries, platform identity before and after restart,
all child artifacts, HTTP response metadata, and the final summary. The
application's public surfaces expose checkpoint state, committed-node lists,
and per-node recovery inspections, which are the observations used by the
frozen pass criteria.

Raw checkpoint manifest and payload files were not exported from the Railway
volume during this canary because the production API intentionally does not
serve those internal files and no temporary SSH credential was introduced
during the frozen run. Consequently an external reader of the retained bundle
cannot independently recompute the checkpoint content hashes; the exact-prefix
claim relies on the deployed runtime's normal manifest validation plus the
public `reused` inspections. This collection limitation is disclosed rather
than silently represented as raw-manifest evidence.

## What this establishes

- One real same-revision Railway restart preserved a validated four-node
  prefix.
- One immutable child reused that prefix without new evidence-agent provider
  requests.
- The repaired typed-context seam passed the real Writer guardrail and the
  remaining Writer/Reviewer/Scorer suffix completed.
- The completed child independently committed all seven checkpoints and served
  its report and audit artifacts.

## What this does not establish

This single canary does not establish exactly-once provider execution, a
production recovery probability, Railway availability or SLO, latency
improvement, general token or cost reduction, total experiment cost, report
correctness, user value, or the necessity of the six-stage architecture. Those
claims require different experiments and denominators.
