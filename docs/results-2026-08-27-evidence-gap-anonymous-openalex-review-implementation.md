# Result: anonymous OpenAlex source lock and Schema v2 review packet

**Date:** 2026-08-27

**Live execution:**
[`results-2026-08-27-evidence-gap-anonymous-openalex-live.md`](results-2026-08-27-evidence-gap-anonymous-openalex-live.md)

**Production connection authorized:** no

**Human value result:** not evaluated; the packet is blank

## Outcome

The exact anonymous OpenAlex execution from revision
`7bfe4eadbf2ead7549125e59d0156c9fa3c1bf94` now has a zero-network review
boundary. It does not reuse the credentialed eight-case Phase 4 source lock:
that older contract includes Lens and a different provider denominator. The
new boundary instead binds the one observed four-case run byte for byte.

The study-owner lock covers nine files:

- four aggregate source artifacts;
- `artifact-index.json`; and
- the D01-D04 case journals.

It also revalidates the fixture and four implementation identities, joins every
case journal back to the aggregate execution, recomputes provider cost from the
case audits, reconstructs every candidate/rejection row, and requires the blank
review denominator to remain exactly 1/2/3/3 candidates across D01-D04.

The source-lock SHA-256 is
`cf7e3ab126ee0665498c4b7538f26a1ae2554673db8cd4c8d3f48786c19433eb`.
The separate Schema v2 packet manifest SHA-256 is
`2177d40e723d83d78f2419d3e21d67044ba08fd5b78cc8683563edd316d95922`.
The lock remains outside the reviewer directory.

## Reviewer-visible contract

The packet carries all nine accepted candidate identities and the complete
frozen baseline context for each of the four cases. The reviewer must:

1. attempt every OpenAlex URL;
2. inspect available source content rather than judge from title alone;
3. assign one of `YES/YES`, `YES/NO`, `NO/N/A`, or
   `UNVERIFIABLE/UNVERIFIABLE`;
4. write a source-grounded note for every row;
5. declare external-source coverage, elapsed time, expertise and generative-AI
   use; and
6. use no substantive generated judgment if the result is to remain eligible.

An unavailable source is `UNVERIFIABLE`, not a silent negative. A partially
filled form, a substantive-AI declaration, an unattempted URL, a changed
identity, a changed baseline or changed source bytes cannot produce a value
headline.

## Empty-packet preflight

The generated blank packet was passed through the real summary boundary before
delivery. It reported:

- `protocol_status=incomplete`;
- `completed_row_count=0`;
- all nine row ids in `incomplete_row_ids`;
- every threshold as `not_evaluated`;
- `planner_trigger_study_eligible=false`; and
- `production_connection_authorized=false`.

This proves only that silence does not become a zero-error pass. It is not a
human review result.

## Validation

Fifteen focused zero-network tests cover the exact source identity, source-lock
authorization, 9-row/baseline packet seam, incomplete and ineligible states,
both remaining value gates, immutable summary output and production
disconnection. A baseline-drift defect was deliberately re-injected: the new
seam test failed because the changed packet was no longer rejected, then passed
again after restoring the guard.

Local verification passes 1,584 tests plus 639 subtests, latest Ruff, and the
CI Pylint exception-order subset. The CI-scope coverage run reports 87.28%,
above the unchanged 85% floor. It emitted nine inherited CrewAI SQLite
`ResourceWarning` messages, no `UserWarning`, and required no warning filter or
test relaxation.

The reviewer packet is local and gitignored at
`outputs/evidence-gap-openalex-anonymous-review-20260827/reviewer-packet/`.
Raw labels and declarations will not be committed to the public repository.

## Next gate

One eligible human reviewer must now complete the nine rows. Only a returned,
source-grounded packet can measure the two remaining frozen gates:

- directly irrelevant candidates must be no more than 5% of all nine accepted
  rows; and
- directly relevant, materially baseline-absent evidence must occur in at least
  three of four cases.

With nine rows, one directly irrelevant source already yields 11.1% and fails
the first gate. Even if both gates pass, the result authorizes only a separately
pre-registered planner-trigger precision study. It does not connect Tool
Calling to production.

## Explicit non-claims

Packet preparation does not establish source relevance, novelty, source truth,
provider-wide precision, planner precision, report improvement, user utility,
cost savings, an SLO or production Tool Calling readiness.
