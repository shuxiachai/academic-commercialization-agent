# Decision Context canary: Reviewer zero-target follow-up

**Date:** 2026-08-27
**Affected run:** `20260826T124329Z-cfd5dc20e750ae6048e3dd503e577960` (`DC01`)
**Scope:** operator diagnosis and zero-network regression repair only

## Why this is an erratum

The frozen paid-canary result correctly recorded the Reviewer fallback root
cause as `not_inspectable`: the public response exposed only
`failure_type=Exception`, and no operator log had been exported when that
result was written. This follow-up adds evidence obtained later. It does not
rewrite the frozen 7/10 result, authorize a paid rerun, or turn a post-study
diagnosis into evidence that the canary passed.

## Operator evidence

The Railway volume retained the run's `process.log`. An operator retrieved
only that file through a temporary workspace SSH key, inspected the relevant
run line, removed the remote key, and deleted the local private-key material.
The raw log is not committed because it is an operational artifact rather than
part of the frozen public study packet.

The sanitized terminal exception was:

```text
Task failed guardrail validation after 1 retries. Last error:
Correction 2 target occurs 0 times; each find value must identify exactly one passage.
```

The failure was therefore not Decision Context parsing, Pydantic conversion,
source retrieval, or provider response formatting. The Reviewer returned a
structured correction whose exact `find` text was absent from the already
validated Writer draft. The old guardrail rejected the whole plan, including
other uniquely matched corrections, and the normal fallback delivered the
validated Writer draft unchanged.

A zero-network search of retained local process logs found no second comparable
`target occurs 0 times` event. This is one provider-backed production
observation, not an incident rate.

## Narrow repair

The correction policy now distinguishes two materially different cases:

- **zero matches:** the correction cannot mutate the validated draft, so that
  item is left unapplied while other exact corrections in the same plan remain
  eligible;
- **multiple matches:** the plan remains blocking, because selecting a passage
  would risk changing the wrong text.

Heading edits, malformed plans, ambiguous targets, citation regressions,
invented source IDs, structural failures, and disclaimer failures remain
blocking. A skipped zero-match item is appended to deterministic Reviewer Notes
and reaches `quality_review.status=partial` with an unapplied count. The web
reliability panel renders that state as a warning. It is never promoted to
`passed`.

The regression test was first run against the old implementation and failed at
the guardrail boundary. After the repair, targeted tests cover the correction
application seam, worker status persistence, API payload contract, and browser
warning state. No paid request was used for this repair.

## What this does not establish

This follow-up does not establish:

- a production fallback rate or correction-miss rate;
- Reviewer accuracy, source truth, or report usefulness;
- that the frozen Decision Context canary passed;
- provider compatibility beyond the already observed run; or
- post-fix production effectiveness without a separately preregistered and
  authorized canary.
