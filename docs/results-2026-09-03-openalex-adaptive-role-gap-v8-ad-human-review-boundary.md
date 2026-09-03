# Adaptive role-gap v8: AD unseen human-review boundary

**Date:** 2026-09-03 (Australia/Sydney)

**Status:** implemented; exact private packet prepared; human labels pending

**Production connection authorized:** no

## Outcome

The completed AD01-AD08 provider run is now bound to an AD-specific source
lock and a route- and lane-blind Schema v2 human-review packet. The boundary
rebuilds the exact write-once run rather than trusting its aggregate counts:
it verifies the artifact-index bytes, recomputes all thirty-eight indexed file
hashes, validates every Pydantic artifact, rebuilds the lane journals, route
journals, case portfolios and aggregate CSV rows, and confirms that the
provider-created review fields remain blank.

The packet contains all 67 DOI/OpenAlex-deduplicated candidates and all eight
frozen baseline/role contexts. It exposes no anchor/closure membership,
provider rank, duplicate occurrence, mechanical route, selected closure role,
computed coverability, aggregate result or answer key. Hidden provenance can
be joined only after every label and the reviewer declaration validate.

Preparing and summarizing the packet made zero network requests and zero model
calls. The blank packet correctly reports `incomplete / not_evaluated`, with
0/67 completed rows, no route assessment and no gate metric.

## Frozen identities

- executed revision:
  `b54fa22666805f8d0de0ff7e26c42af88b641615`
- challenge fixture SHA-256:
  `0be98f249bfd1eaf891cd3c20903b9d6ae4cd2d6431282ee32e82298a2d8ecc7`
- AD runner SHA-256:
  `1f188fbdef225e0f6407b24a2ddbf40b66f5425ff9013021b5e94e0f176ccffa`
- artifact-index SHA-256:
  `01b3193d60d7405388b6d624da543131e18e67d13910bdb42f74e42e21af6e8f`
- private source-lock SHA-256:
  `ac4aa3027e0675e7c24528b999a2d0113654703fbb2ad763913f3ecd814b0be8`
- private packet-manifest SHA-256:
  `f017b1d993f6c47acf974959b8de4214856aac3589c3856dddc081859489248f`
- private blank-label CSV SHA-256:
  `18f5454c2accad3aed01168ec592025bd604647011d2e663538a028680747e21`
- private blank declaration SHA-256:
  `eb17b0ae23599575afcd9a68ad6a6d64644d4c0001fd10cdabb853a3f3ee1a31`

Raw titles, abstracts, source lock and working labels remain in the private
notes repository. They are not committed to this public repository.

## Implementation evidence

The AD review module is a separate audit snapshot. It does not generalize or
modify the consumed AC review implementation. In particular, it freezes the
seven closure cases explicitly: AD01, AD02 and AD04-AD08. AD03 is the only
abstention and is deliberately in the middle of the ordered cohort, so the AC
shortcut `CASE_IDS[:-1]` is invalid.

Sixteen focused zero-network tests cover exact source reconstruction, the
non-positional route set, all-candidate delivery, reviewer blinding, blank and
ineligible states, all six conjunctive gates, source/packet/label/declaration
drift, and production-import isolation. Two required defects were re-injected:

1. replacing the explicit closure set with `CASE_IDS[:-1]` made the AD03/AD08
   seam fail with both a missing AD08 closure and an invented AD03 closure;
2. inserting `frozen_route_decision` into the blind row projection made the
   packet-boundary test fail.

After restoration, the focused suite passed 16/16. The complete suite passed
1,980 tests plus 657 subtests, latest Ruff and the narrow Pylint check passed,
and the Chromium smoke journey reported zero external and paid-provider
requests. The local Docker daemon was unavailable; the pull request's Linux
Docker job is therefore the authoritative container-build check.

## Next decision

An independent reviewer must complete all 67 rows and the declaration without
seeing the source lock or hidden route/lane provenance. The unchanged strict
summarizer will then compute the same six conjunctive gates used for AC.

Until that return is complete and eligible, AD source value, route accuracy,
closure value and role coverability remain `not_evaluated`. Even a six-gate AD
pass would authorize only separately pre-registered planner-trigger,
disabled-path and report-value studies. It would not authorize production
Tool Calling.

## Non-claims

This boundary establishes immutable lineage, reviewer blinding and a strict
zero-label state for one consumed AD run. It does not establish candidate
relevance, novelty, full-text truth, recall, inter-rater agreement, report
improvement, user utility, planner-trigger precision or production readiness.
