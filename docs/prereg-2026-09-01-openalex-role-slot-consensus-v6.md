# Pre-registration: candidate-local role-slot consensus v6

**Frozen:** 2026-09-01, after the completed v5 Qwen failure diagnostic but
before implementing v6, calculating a v6 decision, opening development or
unseen labels, or requesting an OpenAlex or model response for Y01-Y08 or
Z01-Z08.

**Challenge fixture:**
`tests/fixtures/openalex_role_slot_v6_challenge.json`

**Raw fixture SHA-256:**
`f07c457f81fc5b198cb180874895410a4502b9fe3558c9e21c8b42a1f8240c85`

The implementation may read this file only after comparing the raw bytes with
this value.

**Production connection authorized:** no

**Live provider or model calls authorized:** no. This document authorizes only
the frozen method, challenge and future zero-network implementation. Any
OpenAlex or model call requires a separate authorization naming a merged
revision, provider, model, request limits and soft cost stop.

## Measured reason for a new method

v5 is sealed. Its W01-W08 development run produced zero final `KEEP` sources
and failed before X01-X08 could be opened. The post-outcome diagnostic joined
the already committed responses with one eligible human review and assigned
all 64 rows to a mechanical failure class:

- 37 stable abstentions;
- 16 rows exposed to one malformed all-row pass;
- five action disagreements;
- five role-set disagreements; and
- one post-consensus source-threshold rejection.

Among the 28 rows labelled directly relevant from the frozen title and
abstract, 12 were exposed to an invalid all-row pass. The underlying defect
was local: six candidate rows repeated one or more role IDs, but Pydantic
correctly rejected the complete batch and v5 therefore discarded 16 rows.
The remaining 16 relevant rows show that row-local parsing alone is not an
adequate successor: nine were stable model abstentions, four had role-set
disagreement, two had action disagreement and one failed a deterministic
candidate threshold. Qwen proposed `KEEP` for 17 of 56 candidates in the first
valid provider-order passes but only eight in the corresponding reverse-order
passes. This is observed order sensitivity, not evidence that either order was
correct.

These measurements use W01-W08 only as consumed development evidence. They do
not reopen v5, tune a threshold on W, validate v6, or reveal X01-X08. v6 gets
new development and unseen challenges.

## Frozen hypothesis

A semantic model can act as a bounded quote extractor more reliably than as a
source decision maker if the protocol removes free-form role lists and model
actions:

1. every candidate has one fixed positional slot for every code-owned role;
2. the model reports only `SUPPORTED` or `ABSTAIN` plus an exact source quote,
   and never reports `KEEP` or `ABSTAIN` for the candidate as a whole;
3. each candidate row and each role slot is validated independently, so one
   malformed row cannot erase unrelated rows;
4. three deterministic candidate orders are judged, and a role is authorised
   only when at least two passes independently return mechanically valid source
   quotes; and
5. candidate admission and bounded set cover remain deterministic Python
   decisions.

This is not a parser repair for v5. It changes the model task, pass count,
consensus rule, failure isolation and challenge identities. v5 artifacts and
X01-X08 remain historical and untouched.

## Frozen role-slot response contract

Each case receives exactly three batch calls over the same provider candidates:

1. provider result order;
2. reverse provider result order; and
3. lexicographic candidate-SHA-256 order.

The role order is identical in all three calls. Each role has a zero-based
`slot_index`, role kind and code-owned description. For each candidate the
model must return the candidate SHA-256 and exactly one object for every slot,
in slot order. A slot contains:

- `slot_index`;
- `state`, exactly `SUPPORTED` or `ABSTAIN`;
- `field`, exactly `title`, `abstract`, or `null`; and
- `quote`, an exact source-text span or `null`.

`SUPPORTED` requires a non-empty field and quote. `ABSTAIN` requires both to be
null. The model does not output role IDs, candidate actions, relevance,
novelty, truth, set selection or commercial conclusions. A fixed positional
slot removes the duplicate-role-ID language-generation failure without
allowing an unknown role to enter.

The top-level JSON object must identify the case and contain candidate rows.
JSON syntax failure or a case-identity mismatch invalidates that pass. Once the
top-level object is readable, rows are isolated:

- a missing, duplicate, unknown or malformed candidate row cannot authorise
  evidence;
- the expected candidate receives an explicit row state for every pass;
- unrelated expected rows continue through validation;
- an invalid slot is recorded and contributes no support, but cannot erase a
  different mechanically valid slot in the same row; and
- unknown rows and extra slots are counted and retained in the audit summary,
  never silently ignored.

Quote verification may normalise line endings and runs of Unicode whitespace
only. It may not stem, translate, paraphrase, use provider metadata, use human
labels or call another model. There is no retry, repair, redirect or fallback.

## Frozen consensus and evidence-set contract

A role becomes a verified candidate contribution only when at least two of the
three passes return valid `SUPPORTED` slots with quotes present in that
candidate's title or abstract. The two quotes may be different source spans;
both must verify. A one-pass assertion is visible as minority support and does
not authorise the role. A one-pass malformed or missing row can therefore be
tolerated only when the other two independently support the same role.

The code derives a provisional candidate disposition from each valid pass for
the order-stability audit. The model never emits that disposition. Final
candidate admission uses only consensus roles and the fixture's frozen source
requirements:

1. at least one required role;
2. at least one scope or supporting role; and
3. at least one consensus role supported by a title quote in at least two
   passes.

The deterministic selector considers at most three admitted sources. A set
must cover every required role, at least one scope role and at least one
supporting role. It chooses the smallest valid set, then the lowest provider
index tuple, then candidate SHA-256. No model tie-break, profile relaxation,
second query or provider-metadata fallback is allowed.

## New Y01-Y08 development qualification

Y01-Y08 are new, byte-frozen development identities. A repository search of
the parent `main` revision found none of their exact topic strings. They are
not an unseen validation claim: once any Y request is sent, all Y identities
are consumed development evidence.

The runner must use one anonymous OpenAlex Works request per attempted case,
`has_abstract:true`, at most eight provider rows and no redirect, retry,
supplementary fetch or second query. It may then use at most three
`qwen3.5-plus` calls per attempted case, with thinking disabled, temperature
zero and JSON Object mode. The maximum complete development run is eight
OpenAlex requests and 24 model calls. Every outbound request requires a future
explicit authorization.

All development gates are conjunctive:

1. all attempted provider and model calls have inspectable request, returned
   model, token, cost and latency identities;
2. no top-level model pass is malformed or contract-invalid;
3. at least 95% of expected candidate-pass rows are locally valid;
4. at least 80% of candidates have the same code-derived provisional
   disposition in all three passes; malformed or missing rows count against
   this denominator;
5. at least one selected evidence set exists in at least 6/8 cases;
6. an eligible label-blind human review finds relevant, baseline-novel set
   evidence in at least 6/8 cases;
7. human-confirmed role and set coverage passes in at least 6/8 cases;
8. no more than 5% of selected sources are directly irrelevant;
9. no more than 5% of consensus role assignments are unsupported; and
10. every provider candidate, pass, slot, quote check, candidate decision and
    selected source reaches the audit and review boundaries.

Every provider candidate must be human reviewed even after a mechanical gate
failure. The review packet remains label-blind and exposes the frozen baseline,
topic, role descriptions, title and abstract while hiding model slots,
consensus roles and selected sets until aggregation. The reviewer must attempt
every source and declare substantive generative-AI use. An incomplete or
ineligible review is `not_evaluated`, not a pass.

Any failed development gate seals v6. Y may be diagnosed but not tuned and
rerun into a pass. A successor would require a new method and challenge.

## Unseen Z01-Z08 challenge

Z01-Z08 are byte-frozen but remain unopened until every Y gate passes and a
separate authorization names the exact merged implementation revision. A
repository search of the parent `main` revision found none of their exact topic
strings. Once any Z request is sent, all Z identities are consumed even if the
run stops later.

The provider, model, request, response, consensus, selection and human-review
contracts are identical to Y. The unseen gates are the same ten conjunctive
gates. No Y-derived prompt, threshold, role or parser change may be applied
after seeing Y outcomes while retaining the v6 identity; such a change starts
a successor method and requires a fresh unseen challenge.

X01-X08 remain reserved historical v5 identities. v6 does not open, rename or
reuse them.

## Implementation and falsification requirements

Before any live Y or Z call, the zero-network implementation must:

- verify the exact committed raw-byte SHA-256 above before JSON parsing or case
  expansion;
- validate unique method, case, query, role, pass-order and idempotency
  identities;
- freeze prompt, parser, quote verifier, consensus, selector, runner and
  adapter hashes;
- persist a complete manifest before constructing an OpenAlex or model client;
- commit each provider response and model-call journal before a later request;
- preserve each expected candidate and role slot through the serialized audit
  boundary, including malformed and missing states;
- prove one malformed candidate row does not erase a valid neighbouring row;
- prove an invented quote and a one-pass quote cannot authorise a role;
- prove the model has no candidate-action field and cannot select a source;
- prove all three candidate orders actually cross the outbound seam;
- prove deterministic set-cover tie-breaking and the three-source ceiling;
- assert that production modules do not import v6; and
- re-inject at least the whole-batch invalidation and computed-but-undelivered
  defects, confirm their seam tests turn red, then restore the implementation.

The implementation phase must run the complete zero-network suite, latest Ruff
and narrow Pylint, then record a separate result. Offline success establishes
only a tested disconnected contract, not semantic quality or Tool Calling
completion.

## Explicit non-claims

This pre-registration does not authorise model or OpenAlex calls, private-label
access, production import, report connection or planner trigger. Future Y or Z
success would still not establish OpenAlex-wide precision or recall,
literature-wide novelty, source truth beyond the review, inter-rater agreement,
report improvement, decision correctness, adoption, ROI, latency, an SLO,
autonomous tool choice or completed production Tool Calling.

`pipeline_worker.py` must remain disconnected from every v6 kernel, fixture,
adapter, runner, preflight and review module.
