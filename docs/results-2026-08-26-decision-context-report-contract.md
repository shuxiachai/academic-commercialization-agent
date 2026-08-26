# Result: decision context and decision-ready report contract

**Date:** 2026-08-26
**Protocol:** [`prereg-2026-08-26-decision-context-report-contract.md`](prereg-2026-08-26-decision-context-report-contract.md)
**Provider calls and cost:** 0 / USD 0

## Outcome

The offline implementation criteria passed. A submission can now carry a
bounded optional `DecisionContext` from the browser and API into the immutable
RunSpec, checkpoint identity, Crew input, and both public run-status endpoints.
The code derives one of three states: `orientation`,
`decision_context_incomplete`, or `decision_support`. Clients cannot supply or
override that state.

The change does not establish that a generated decision is correct or useful.
No model generated a report during this implementation study, no source was
opened, and no target user evaluated the changed output.

## Implemented contract

- The seven optional fields are asset description, target application,
  decision owner, decision type, jurisdiction, time horizon, and constraints.
- Unknown fields and values beyond their bounded lengths are rejected by the
  public request model before paid admission. Layout-only whitespace is
  normalized, and an empty object shares the same identity as omission.
- All four core fields are required for `decision_support`. Partial input does
  not block the run; it produces `decision_context_incomplete`. Omission remains
  backward-compatible orientation mode.
- RunSpec schema version 2 persists the normalized context. Version-1 specs
  remain readable and derive orientation mode.
- The context contributes to checkpoint input hashes. The worker passes it to
  CrewAI only through the Writer/Reviewer input placeholders; retrieval and the
  scoring formula are unchanged.
- The Writer contract now requires one primary route, secondary alternatives,
  an owner state, evidence thresholds, cost/time state, and stop criteria. It
  permits `GO`, `NO_GO`, or `DEFER` only in decision-support mode.
- Reviewer Rule 7 may correct decision framing that contradicts the code-derived
  mode. It remains a bounded correction-plan stage and does not become a new
  heuristic report blocker.
- Public status records only mode, supplied field names, missing core field
  names, and whether actor-specific go/no-go output is permitted. It does not
  duplicate the submitted prose into status.json.
- The web client exposes the fields in a collapsed optional panel, explains the
  applicability boundary in English and Chinese, and clears accepted context
  only after a successful submission.

## Acceptance evidence

| Frozen seam | Result |
|---|---|
| API normalization and unknown/oversized rejection | passed |
| browser fields to JSON request contract | passed |
| API request to immutable RunSpec | passed |
| RunSpec to checkpoint identity | passed |
| worker RunSpec to `crew.kickoff(inputs=...)` | passed |
| decision gate through status and progress endpoints | passed |
| omitted context and version-1 compatibility | passed |

Verification after restoration of the final implementation:

- affected zero-network subset: **138 passed plus 79 subtests**;
- complete zero-network suite: **1,540 passed plus 632 subtests**;
- CI-equivalent coverage: **87.23%**, above the frozen 85% floor;
- latest Ruff: passed; and
- narrow CI Pylint exception-order/unreachable checks: passed.

The API subset initially depended on the deployment's `DAILY_CAP=3` value.
That was a test-isolation defect, not a production-cap defect: mock concurrency
tests can admit more than three operations by design. Their fixtures now set
the unrelated daily cap to zero, reset the in-process durable-ledger cache, and
restore every prior value after each test. Production accounting and its
dedicated limit tests were not relaxed.

## Defect re-injection

After the new suite passed, the single line that merges
`spec.decision_crew_inputs()` into the Crew input was temporarily removed. The
worker seam test failed at the actual boundary with:

```text
KeyError: 'assessment_mode'
```

The line was restored and the same test passed. This demonstrates that the
test does not stop at Pydantic persistence; it detects a context value that is
stored correctly but never reaches model execution.

## Claim limits and next evidence

This result proves an offline execution and observability contract only. Prompt
instructions do not prove model compliance, and Reviewer fallback means an
unperformed review is still explicitly possible. The deterministic decision
gate measures context completeness, not evidence truth, commercial accuracy,
adoption, ROI, time saved, or superiority over the topic-only workflow.

The next admissible experiment is the separately authorized three-mode paid
canary described by the protocol. Its criteria must be frozen before provider
work and must keep factual correctness and user value as `not_evaluated` until
source checks or human review actually measure them.
