# Result: same-revision Railway restart reached recovery admission only

**Date:** 2026-08-24
**Pre-registration commit:** `2f48232`
**Production revision:** `f9e3b611779af1e3148cad1d5552758bd67ea274`
**Source run:** `20260824T064715Z-e18f9f219ecb6dc974cee792deefe0df`
**Child run:** none
**Result:** **NON-PASS — the recovery child was not admitted**

## Decision

Do not claim paid same-revision checkpoint reuse from this canary. The source
reached the frozen four-node boundary, the production restart preserved that
prefix on the Railway volume, and the source became safely resumable. The one
allowed resume request was then rejected before child creation because this
owner had already reached the configured daily limit of three operator-funded
paid operations.

That rejection is a correct wallet boundary, not a damaged checkpoint. It also
means the canary stopped before the seam it was meant to measure. No replacement
source, alternate access code, BYOK bypass, or second resume attempt was used.

## Frozen protocol

The [pre-registration](prereg-2026-08-24-paid-same-revision-recovery.md) was
committed and pushed before the source was submitted. It fixed:

- benchmark case 03, `solid-state batteries for electric vehicles`;
- deployment revision `f9e3b61`;
- a minimum prefix of retrieval plus all three evidence nodes;
- one source, one child, no retries;
- a `$0.10` soft LLM-cost stop;
- a Railway restart without rebuild as the production fault.

The draft PR containing that record passed all seven CI jobs before the paid
source began.

## Observed sequence

1. Immediately before submission, `/health` reported zero active runs and zero
   active paid operations. `/health/ready` returned `ready=true`; LLM, search,
   outputs, and paid accounting were all `ok`. Railway reported deployment
   `c6f944cd-bd26-4942-ae70-458a431e1fb8` as `SUCCESS`/`RUNNING` at the frozen
   commit.
2. The source was admitted at `2026-08-24T06:47:15Z`.
3. Retrieval committed at `06:48:21.241880Z`, patent at `06:48:34.783627Z`,
   market at `06:48:41.766719Z`, and academic at `06:48:43.613136Z`.
4. At `06:48:43.955233Z`, both the source state and the persisted manifests
   showed exactly `retrieval, academic, patent, market`. The source was still
   running in `Agent 4 — Report Writing`; its event stream showed all three
   evidence agents finished and the writer started.
5. Railway accepted an immediate restart without rebuild and returned the same
   deployment id. The first recorded post-restart readiness success was
   `06:49:29.494031Z`. This 45.5-second interval begins at boundary observation,
   not at proven unavailability, and is not an outage or SLO measurement.
6. After restart, Railway still reported the same deployment, instance, image,
   and commit. The source was `failed`, not completed, while both status APIs
   still exposed the exact four-node prefix with no checkpoint errors.
7. The only resume request returned HTTP 429: `3 operator-funded paid
   operations already admitted today`. It returned no child id. The sanitized
   durable ledger confirmed schema 1, date `2026-08-24`, and one anonymous
   count of 3.
8. The subsequent run list contained the source and no child. `/health` again
   reported zero active runs and zero active paid operations.

## Evidence summary

| Measure | Observation |
|---|---|
| Source terminal state | `failed` after restart |
| Source stage | `Agent 4 — Report Writing` |
| Sources | 8 academic / 8 patent / 7 market |
| Persisted prefix | retrieval + academic + patent + market |
| Manifest revision | `git:f9e3b611...` on all four nodes |
| Checkpoint errors | none |
| Railway revision after restart | unchanged (`f9e3b611...`) |
| Readiness after restart | HTTP 200, all four checks `ok` |
| Resume response | HTTP 429 daily paid-operation cap |
| Child run/provider calls | none; admission stopped before child creation |
| Source checkpoint usage | `null` on all four manifests |
| Exact source tokens/cost | `not_inspectable`, not zero |
| Report | none, because no child executed the suffix |

The source manifest `usage` fields being null is consequential: the three
completed provider-backed evidence nodes certainly ran, but their partial
tokens and cost cannot be reconstructed from the persisted checkpoint record.
The `$0.10` stop therefore cannot be evaluated as an exact total. The one
failed resume admission did not start a provider call.

## Pre-registered criteria

| Criterion | Result |
|---|---|
| Eligible prefix visible while source was running | pass |
| Same revision and readiness after Railway restart | pass |
| Source terminal and one child accepted | **fail** — source terminal, child rejected |
| Child reports exact contiguous-prefix reuse | not run |
| Reused nodes absent from child provider execution | not run |
| Child completes report and all seven checkpoints | not run |
| Exact source + child cost stays within soft stop | not inspectable |

The aggregate verdict is non-pass because the protocol has no partial-pass
threshold.

## What this establishes

- A real restart of the deployed Railway service preserved the four committed
  source manifests on the mounted volume.
- The restarted API derived the interrupted source as failed and exposed the
  same checkpoint state through both client status surfaces.
- Paid-operation accounting survived the restart and failed closed before an
  over-cap recovery could create a child or reach a provider.

## What remains open

Paid same-revision reuse is still unmeasured. A future, separately authorized
follow-up could resume this existing failed source after the UTC ledger resets,
provided production still runs the exact same revision and the protocol is
frozen separately. It must not be described as a retry of this non-pass or as
evidence that the source cost was below the stop.

This result does not support exactly-once execution, token/cost/latency savings,
a Railway recovery rate or SLO, report correctness, or six-stage necessity.
