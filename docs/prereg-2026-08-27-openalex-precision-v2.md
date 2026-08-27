# OpenAlex precision-v2 conjunctive evidence gate — pre-registration

**Frozen:** 2026-08-27, after reading the completed nine-row development
review but before implementing the candidate, calculating its decisions, or
making any request for the unseen challenge

**Challenge fixture:**
`tests/fixtures/openalex_precision_v2_challenge.json`

**Raw fixture SHA-256:**
`dd1dde0f47a884c5f811684b3b4efe4e0408af5e175d5d698cc272d14bff527e`

**Production connection authorized:** no

**Live provider requests authorized:** no; any unseen execution requires a
separate authorization naming the merged revision, request cap and soft stop

## Why a different method is being tested

The first anonymous OpenAlex study completed four one-request cases and an
eligible nine-row human review. Five candidates were directly relevant and
four were not, so the 44.4% wrong-source rate failed the frozen 5% ceiling.

The failure is not a threshold problem. The current quarantine adds one point
for every topic word and two for every bigram, then accepts academic rows at a
score of three. That rule allowed two D03 sources to accumulate broad words
such as `synthetic`, `metabolic` and `pathway` without cell-free carbon
fixation. It also allowed two D04 reviews to accumulate `perovskite`, `silicon`
and `stability` without jointly supporting tandem-module degradation under the
named environmental stress.

Raising the same numeric threshold after seeing those rows would be
case-dependent tuning and would not express which evidence relationship is
required. Precision v2 therefore tests a different representation: explicit
conjunctive concept groups with abstention.

## Development and validation are separated

The nine labelled rows are development evidence only. Their source identities
are frozen in the fixture:

- `labels.csv` SHA-256:
  `aaff469be0e10698a5464611343823e91b4f7256b8a881ed6361f3b27d56b296`;
- `candidates.csv` SHA-256:
  `91d148f97320582fe29987ff2ef139f7e3cb3d53ab2473ef1ac4ad3119805006`;
- four case-journal hashes are recorded under `development_source`; and
- denominator: nine quarantine-accepted rows across D01-D04, with five
  `relevant=YES` and four `relevant=NO`.

The candidate may be designed from these rows, but no metric on them can be
reported as held-out precision or provider performance. The independent
challenge is U01-U08. Repository search found no prior occurrence of their
eight exact topics before this fixture was frozen. No provider result or human
label for U01-U08 has been observed.

## Frozen candidate contract

Each trusted, code-owned profile contains:

1. two or more **required groups** whose phrases represent distinct core
   concepts;
2. two or more **supporting groups** that represent route, application,
   operating condition or measured outcome;
3. `minimum_supporting_groups`; and
4. `minimum_title_required_groups`.

Text matching is deterministic and model-free. Candidate title and abstract
are Unicode-normalized, case-folded and split into alphanumeric tokens. A
phrase matches only a complete token sequence; substring matching and semantic
expansion are forbidden. A group matches when any of its frozen alternative
phrases matches.

The candidate emits only:

- `ACCEPT` when every required group matches title plus abstract, at least the
  frozen number of supporting groups matches, and the title contains the
  frozen number of required groups; or
- `ABSTAIN` otherwise, with missing group IDs and matched group IDs recorded.

`ABSTAIN` does not assert that a paper is irrelevant. There is no automatic
`DROP`, no model fallback, no source-page fetch, no threshold relaxation and no
topic-specific exception outside the frozen profiles.

Profiles are experimental trusted inputs. The current phase does not authorize
a model to invent or modify concept groups. Measuring whether a planner can
produce safe profiles is a later experiment that can start only after unseen
source value passes.

## Development prediction and falsification

The code must make every D01-D04 decision without receiving a human label or
review note. Labels join only after all decisions exist. The development
candidate qualifies to face U01-U08 only if all of the following hold:

1. all nine source identities and all four case journals match their frozen
   hashes;
2. all five relevant rows are `ACCEPT`;
3. all four directly irrelevant rows are `ABSTAIN`;
4. every one of D01-D04 retains at least one relevant candidate; and
5. every decision and aggregate reaches a write-once JSON/CSV output seam.

This gate is deliberately strict because the profiles were authored after the
failure was visible. Passing it proves only that the implementation expresses
the intended development rule; failing it records the candidate as failed and
stops the unseen study. No threshold or profile is changed after calculation.

## Unseen challenge

U01-U08 cover eight previously unused academic topics spanning polymers,
cryogenics, ocean carbon removal, infrared devices, vaccines, construction
materials, clinical ML and transient electronics. Each case freezes one query,
one precision profile and a result limit of five.

A later live runner, if separately implemented and authorized, must preserve:

- anonymous OpenAlex only, with no configured API key;
- exactly one request per attempted case and no retry, redirect, enrichment
  fetch or model call;
- at most eight requests and forty provider rows;
- provider-reported cost and per-case write-once journals;
- every provider rejection, precision-v2 abstention and accepted row; and
- `production_connected=false` and `report_workflow_connected=false` at every
  artifact seam.

The live runner must freeze its implementation hashes before credentials,
output reservation or adapter construction. This document does not authorize
building a shortcut around the existing source lock or human-review intake.

## Frozen unseen value gates

Only a complete, source-locked, eligible human review can calculate the gates:

1. at least one precision-v2 accepted candidate in at least 6/8 cases;
2. no more than 5% of accepted candidates labelled directly irrelevant;
3. at least one directly relevant, materially baseline-absent candidate in at
   least 6/8 cases;
4. every accepted URL attempted and every accepted row labelled; and
5. no substantive generative-AI judgment in the review.

Zero accepted rows, unavailable sources, missing accounting, source drift,
incomplete labels or an ineligible reviewer declaration is a non-pass, never a
zero-error result. Passing all gates would authorize only a separately
pre-registered planner-trigger study. It would not authorize report mutation
or production Tool Calling.

## Tests and defect re-injection

Before any live request:

- schema limits, duplicate groups and duplicate normalized phrases fail closed;
- token-sequence matching is tested against substring and punctuation traps;
- decision order and every matched/missing group survive serialization;
- development file drift, missing rows, duplicate rows and label leakage fail;
- output paths are write-once;
- `pipeline_worker.py` remains disconnected; and
- at least one original wrong-source defect is re-injected so the new seam test
  demonstrably turns red before restoration.

The complete zero-network suite, latest Ruff and narrow Pylint remain required.
Tests may not ignore warnings, skip failures or weaken existing assertions.

## Explicit non-claims

Development success, unseen dry-run success, or even a later source-value pass
does not establish OpenAlex-wide precision, retrieval recall, source truth,
planner-trigger precision, report improvement, user utility, adoption, cost
savings, latency, an SLO, autonomous tool choice or production readiness.

