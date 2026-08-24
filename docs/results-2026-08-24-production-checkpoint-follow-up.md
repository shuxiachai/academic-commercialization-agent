# Production follow-up: checkpoint startup fix and cross-revision resume

**Date:** 2026-08-24
**Source run:** `20260824T004956Z-c2695db895655245d5a51bb636a1322f`
**Child run:** `20260824T041437Z-5aff37ad1034b000491f55f4ec298250`
**Deployment revision:** `ff63ea7` (PR #25)

## Why this run was made

The source run had collected eight academic, eight patent, and eight market
sources, then failed before its first provider request because CrewAI's
omitted `Task.context` sentinel was treated as iterable. PR #25 fixed that
startup seam. One operator-funded resume was authorized to check the paid
production path without starting a second unrelated assessment.

This was an operational follow-up, not a pre-registered checkpoint fault
experiment. The request was limited to one child and was not retried.

## Observed sequence

1. The resume endpoint accepted the failed source and created an immutable
   child.
2. The child inspected the source retrieval checkpoint and reported
   `identity.pipeline_revision` as a mismatch: the parent was produced before
   PR #25 and the child ran after it.
3. Recovery therefore remained explicitly `cold_start`, with zero reused
   nodes. The child recollected 8/8/8 sources instead of treating a stale
   checkpoint as valid.
4. Academic, patent, market, writer, reviewer, and scorer execution completed.
   All seven durable nodes, including retrieval, were committed without a
   checkpoint error.
5. The final report endpoint returned HTTP 200 with 17,705 characters.

## Measured result

| Measure | Observation |
|---|---:|
| Terminal state | `completed` |
| Elapsed time | 208 seconds |
| Provider requests | 7 |
| Total tokens | 102,485 |
| Estimated cost | $0.044635 |
| Sources | 8 academic / 8 patent / 8 market |
| Reused nodes | 0 |
| Recovery state | `cold_start` |
| Checkpoint state | `complete` |

The completed status exposed `report`, `scores`, `sources`, `notes`, `steps`,
and `grounding` artifacts. The quality reviewer reported `passed`; component
coverage was complete. Claim grounding completed with two checked claims,
zero ungrounded claims, and four market claims marked unverifiable. Those
small denominators do not establish report-wide factual correctness.

OpenTelemetry was active and supplied a trace id, but delivery remained
`attempted`, which is the project's documented OTLP acknowledgement boundary.

## What this establishes

- The PR #25 sentinel fix reaches the deployed paid provider path rather than
  succeeding only under mocks.
- A cross-revision source is not silently reused; the mismatch is observable
  in both recovery state and inspection reasons.
- A cold-start child can complete the full six-stage workflow and publish a
  report plus every checkpoint on Railway.

## What this does not establish

- It is not a successful checkpoint reuse result: zero nodes were reused.
- It is not production fault injection, a recovery rate, a latency or token
  saving, an exactly-once claim, or evidence that six stages are necessary.
- HTTP 200 from the report API verifies the client data seam, not visual
  browser rendering. Browser automation was unavailable because the local
  control runtime failed to start; no visual result is claimed.

A paid same-revision reuse result still requires a separately authorized
failure after a committed node followed by an immutable child resume.
