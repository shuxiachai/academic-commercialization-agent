# Erratum: OpenAlex precision-v2 unseen fixture duplicate phrase

**Date:** 2026-08-27
**Affected protocol:**
[`prereg-2026-08-27-openalex-precision-v2.md`](prereg-2026-08-27-openalex-precision-v2.md)

## What was found

The fail-closed U01-U08 preflight rejected the frozen challenge before adapter
construction. In U02, the `rare_earth_free` supporting group contained both
`rare earth free` and `rare earth-free`. The frozen matcher applies NFKC
normalization and tokenizes punctuation, so those two strings are the same
normalized phrase. Allowing both would violate the profile invariant that one
concept cannot be counted twice through spelling variants.

This was a fixture-authoring defect, not a provider, candidate, or result
observation. No OpenAlex request, model call, output reservation, precision
decision, or human label existed when it was found.

## Preserved and corrected identities

The original challenge file remains byte-for-byte unchanged:

- `tests/fixtures/openalex_precision_v2_challenge.json` SHA-256:
  `355782bbe40278f44cb76f650d57fbb13be6b9097bfecb6e101815a24c47ea8b`.

A separate correction lock records the only admissible transformation:

- `tests/fixtures/openalex_precision_v2_unseen_correction.json` SHA-256:
  `ac4a0cdfdbd18c688cba2e7edf340b0089f1402a5c549d56804dcab0231bfd84`;
- source case/group: U02 / `supporting_groups` / `rare_earth_free`;
- exact expected phrases: `rare earth free`, `rare earth-free`,
  `lanthanide free`; and
- exact replacement: `rare earth free`, `lanthanide free`.

The loader first verifies both file hashes, then requires the exact case,
group, and before-value before applying the replacement. It refuses unknown,
retargeted, reordered, or additional corrections. The semantic concept,
topic, query, request limit, acceptance rule, and source-value gates do not
change; only a token-identical duplicate is removed.

## Consequence

U01-U08 remain an unseen challenge. This erratum authorizes neither a live
request nor a production connection, and it supplies no evidence about source
truth, precision, recall, novelty, report value, planner quality, or user
utility. Any live run still requires separate authorization against the merged
implementation revision, the frozen eight-request cap, and the cost soft stop.
