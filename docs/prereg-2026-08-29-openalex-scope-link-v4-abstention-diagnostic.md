# Pre-registration: OpenAlex scope-link v4 abstention diagnostic

**Frozen:** 2026-08-29, after the W01-W08 live result was observed and
recorded, but before implementing this diagnostic packet or obtaining any
human labels for the 64 abstained candidates.

**Parent execution protocol:**
`docs/prereg-2026-08-28-openalex-scope-link-v4-live.md`

**Observed execution result:**
`docs/results-2026-08-29-openalex-scope-link-v4-live.md`

**Executed revision:**
`678254d66c599402811d04f9b2b91ff6977ac089`

**Production connection authorized:** no

## Status of this document

This is a post-outcome diagnostic pre-registration, not a retrospective change
to the W01-W08 value study. The original study failed its frozen mechanical
coverage gate at 0/8 accepted cases and remains `source_value=not_evaluated`.
Nothing in this diagnostic can rescue that result, authorize production, or
turn W01-W08 into an unseen validation set again.

The only still-unobserved quantity frozen here is the human interpretation of
the title and abstract text for every candidate that v4 abstained from.

## Observed facts available before human labels

The exact completed run contains eight candidates for each of W01-W08, for 64
candidate decisions in total. All 64 decisions are `ABSTAIN` and 63 include
`missing_scope_link`. Across the persisted decision traces:

- 33 candidates contain at least one exact required-group match;
- 8 contain at least one exact scope-group match;
- 20 contain at least one exact supporting-group match; and
- 1 contains a linked scope group but fails another frozen requirement.

These are deterministic trace counts. They do not say whether a paper is
relevant, whether a semantic relationship exists, or whether the abstract is
sufficient for a human judgment.

## Question

Does the 0/8 result primarily reflect:

1. OpenAlex retrieval noise;
2. relevant but target-relation-missing papers;
3. a semantic relationship present in the frozen text but missed by the exact
   same-segment rule; or
4. title/abstract evidence that is insufficient for classification?

## Frozen population and source identity

The diagnostic includes all 64 candidate evaluations. There is no sampling,
ranking, top-k selection, provider request, enrichment fetch, retry, redirect,
model call, or supplementary search.

The implementation must lock and revalidate all of these source files:

- `manifest.json`;
- `execution.json`;
- `candidates.csv`;
- the intentionally header-only `review.csv`;
- `artifact-index.json`; and
- `case-executions/W01.json` through `W08.json`.

The source lock must bind the exact file hashes recorded by the completed live
result. Packet preparation and result summarization must repeat that validation
and reject any drift.

## Label-blind packet boundary

The reviewer receives the frozen topic, baseline source context, candidate
title, abstract, publisher, publication date, DOI and URL. The editable label
file and reviewer-facing context must not expose:

- `ACCEPT` or `ABSTAIN`;
- abstention reasons;
- required, scope or supporting match provenance;
- same-segment link evidence;
- profile thresholds; or
- provider aboutness scores.

Those values remain in the source-locked execution and are joined only after
labels are returned. This blinding prevents `missing_scope_link` from telling
the reviewer what conclusion the diagnostic expects.

## Frozen labels

Every row requires five completed fields:

1. `direct_relevance`: `YES`, `NO`, or `UNVERIFIABLE`;
2. `semantic_scope_link`: `YES`, `NO`, `N/A`, or `UNVERIFIABLE`;
3. `baseline_novelty`: `YES`, `NO`, `N/A`, or `UNVERIFIABLE`;
4. `abstract_sufficient`: `YES` or `NO`; and
5. a source-grounded `review_note`.

The only valid combinations are:

- directly relevant `YES`, semantic link `YES` or `NO`, baseline novelty
  `YES` or `NO`, and abstract sufficient `YES`;
- directly relevant `NO`, semantic link `N/A`, baseline novelty `N/A`, and
  abstract sufficient `YES`; or
- `UNVERIFIABLE / UNVERIFIABLE / UNVERIFIABLE / NO`.

The reviewer judges only the frozen title and abstract against the visible
topic and baseline. Opening external URLs is optional and must be declared,
because this diagnostic measures the method's treatment of the text it
actually received rather than source truth beyond that text.

## Reviewer eligibility

The declaration records reviewer ID, complete-row confirmation, generative-AI
use, external-source checking, elapsed minutes, expertise, date and
limitations. `NONE` and `LANGUAGE_ONLY` are the only eligible generative-AI
states. A substantive AI declaration is retained but yields
`excluded_substantive_ai / not_evaluated`. Missing rows, a missing declaration,
or failure to confirm all rows cannot appear as a completed diagnostic.

`UNVERIFIABLE` is a valid observation and remains in the denominator; it is
never silently converted into a negative label.

## Frozen descriptive metrics

For an eligible complete return, the summarizer reports:

- relevant, irrelevant and unverifiable candidate counts;
- relevant-case and baseline-novel relevant-case coverage;
- semantic-link-present count;
- the count and rate of human semantic links paired with v4
  `missing_scope_link`;
- retrieval-noise and frozen-text-insufficiency rates;
- attribution counts by case; and
- the original v4 reason distribution.

The post-label attribution categories are:

- `semantic_relation_missed_by_v4`: relevant and human-linked, while v4
  recorded `missing_scope_link`;
- `other_gate_rejection_of_relevant_source`: relevant but not in the first
  category;
- `retrieval_noise`: directly irrelevant; and
- `frozen_text_insufficient`: unverifiable from the frozen text.

No pass/fail threshold is attached to these metrics. Their only purpose is to
choose a new hypothesis family. If a future v5 is built, it must be evaluated
on a newly frozen unseen challenge; W01-W08 may be development evidence only.

## Required zero-network verification

Tests must prove that:

- only the exact completed 64-row mechanical-failure execution can be locked;
- every source and case-journal byte is revalidated at lock, packet and summary
  boundaries;
- all 64 candidate identities and all eight baseline contexts reach the packet;
- editable and reviewer-facing packet content contains no v4 decision signal;
- blank rows are `incomplete`, never a zero-error result;
- identity drift, partial labels and invalid label combinations are rejected;
- substantive generated judgments remain retained but not evaluated;
- complete eligible labels join the hidden decision trace only at summary;
- the output always preserves `original_source_value_state=not_evaluated` and
  `production_connected=false`; and
- `pipeline_worker.py` imports none of the diagnostic, v4 method, runner or
  adapter modules.

After the focused tests pass, deliberately leak one v4 decision field into the
reviewer label boundary and confirm the packet-blinding seam test fails. Restore
the correct boundary before the full suite.

## Explicit non-claims

This diagnostic cannot establish provider-wide precision or recall, source
truth, planner-trigger precision, report improvement, user value, adoption,
ROI, an SLO, autonomous tool choice, or production Tool Calling. It cannot
change the already failed v4 source-value result.
