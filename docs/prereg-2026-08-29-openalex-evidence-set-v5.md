# Pre-registration: OpenAlex quote-grounded evidence-set candidate v5

**Frozen:** 2026-08-29, after the completed scope-link v4 abstention
diagnostic but before implementing this candidate, calculating any v5
decision, calling a semantic judge, or requesting an OpenAlex response for
X01-X08.

**Challenge fixture:**
`tests/fixtures/openalex_evidence_set_v5_challenge.json`

**Raw fixture SHA-256:**
`f0c4cc86593f54a36040cf1b7d95b42207726b9323172b7dccae2df47ca5a521`

**Production connection authorized:** no

**Model or live provider calls authorized:** no. This document authorizes only
the frozen hypothesis and future zero-network implementation. Any model call,
OpenAlex request, or use of private development labels requires a separate
authorization naming the merged revision, requested model, request limits and
soft cost stop.

## Why v5 changes the unit of evidence

The prior candidates exposed two different failure classes:

- precision v2 retained sources in only 3/8 unseen cases and stopped before
  human review;
- claim-scope v3 retained sources in 7/8 cases, but one of 13 human-reviewed
  sources was directly irrelevant, so its 7.69% wrong-source rate exceeded the
  frozen 5% maximum; and
- scope-link v4 accepted zero of 64 OpenAlex rows across W01-W08. Its frozen
  6/8 coverage gate therefore failed before source-value review.

The separately pre-registered v4 diagnostic then reviewed all 64 abstentions
without reopening that result. From title and abstract text, one eligible
reviewer found 28 directly relevant rows and 36 retrieval-noise rows. Every
case had at least one relevant, baseline-novel source. Five rows supported the
target semantic link, and v4 missed four of the five. This single-reviewer,
title/abstract-only result is diagnostic rather than source truth, but it is
enough to reject another exact-phrase threshold edit as the next hypothesis.

The decisive representation error is that v4 asked one paper to state the
whole commercialization topic in one sentence. Literature evidence is often
distributed: one source establishes the technology, another establishes the
deployment scope, and a third supplies performance or risk evidence. v5
therefore evaluates quote-grounded role contributions per source and then
selects a bounded evidence **set**. It does not lower the v4 threshold, rescue
v4, or treat W01-W08 as unseen validation.

## Frozen hypothesis

A bounded semantic judge can recover useful relation recall without silently
authorizing unsupported evidence when all of the following are enforced:

1. the judge sees only a candidate identity, title, abstract and code-owned
   role descriptions;
2. every asserted role carries a source-text quote that can be mechanically
   verified;
3. two order-reversed passes agree on `KEEP` and on the exact role IDs;
4. disagreement, malformed output or an unverifiable quote becomes `ABSTAIN`;
   and
5. a deterministic set-cover step selects at most three complementary sources
   for a case.

The model is a proposal mechanism under a deterministic evidence boundary. It
does not establish relevance, novelty or correctness; the frozen human-review
stage remains the source-value authority.

## Frozen semantic-judge contract

The requested provider is DeepSeek, the requested model is `deepseek-chat`,
and the API base is `https://api.deepseek.com`. The future runner must record
the requested identity, provider-returned model identity, prompt hash, response
hash, token usage, cost basis, latency and trace ID for every call. An absent or
inconsistent returned model identity is an inspectability failure, not a pass.
The model alias may change behind the provider endpoint; this protocol makes
that limitation observable rather than claiming bitwise model reproducibility.

Each case receives exactly two batch judgments over the same candidates:

- pass one uses provider order;
- pass two reverses provider order;
- temperature is zero;
- no previous decision, OpenAlex topic/keyword, provider score, v4 trace,
  human label or human note is visible; and
- the only candidate actions are `KEEP` and `ABSTAIN`.

For every `KEEP`, the judge must return the role IDs it believes the source
supports and one title-or-abstract quote for each role. Quote verification may
normalize line endings and runs of Unicode whitespace only; it may not stem,
translate, paraphrase or use provider metadata. A candidate survives only if
both parsed passes return `KEEP`, name the same role IDs, and supply a valid
quote for every role. Unparseable output, missing rows, duplicate candidate
identities, pass disagreement or quote failure produces `ABSTAIN` and remains
visible in the audit artifact.

Disposition agreement is the fraction of provider candidates for which both
passes return the same parsed action and, for `KEEP`, the same role IDs.
Malformed, missing or quote-invalid output counts as disagreement. Two passes
are a repeatability probe, not proof that the model is correct or independent.

## Frozen evidence-set contract

Candidate identities bind the raw title and abstract. A surviving candidate
must contribute:

1. at least one required role;
2. at least one scope or supporting role; and
3. at least one role grounded by a title quote.

For each case, the deterministic selector enumerates sets of at most three
surviving candidates. A valid set must cover every required role, at least one
scope role and at least one supporting role. It chooses the smallest valid set,
then the lexicographically smallest provider-index tuple, then candidate
SHA-256. If no valid set exists, the case abstains. There is no model-selected
tie break, profile relaxation, second query, source-page enrichment or fallback
to v4 provider metadata.

## Development qualification on consumed W01-W08

W01-W08 and their labels are consumed evidence. They may be used once as a
disclosed **development qualification** because they explain the failure class;
they may never be described as v5 validation. The implementation must lock the
exact public 64-row artifact and the private human-review artifact before
opening labels. The semantic judge must run label-blind, and labels may be
joined only after every model response and set decision has been committed.

All development gates must pass before any X01-X08 provider request is eligible:

1. candidate-disposition agreement is at least 90%;
2. at least four of the five human-inferred semantic-link rows survive;
3. at least 6/8 cases retain relevant, baseline-novel evidence;
4. at most one selected source is directly irrelevant; and
5. every candidate, pass, quote check and selection decision is persisted.

A failure seals the v5 candidate. It may be analysed, but W01-W08 may not be
tuned and replayed into a pass. Any successor requires a new hypothesis and a
new challenge.

## Unseen X01-X08 challenge

A repository search of the parent `main` revision found none of these eight
exact topic strings before the fixture was added. This is an exact-string
claim, not a claim that the broad scientific domains were never discussed.

| ID | Frozen topic |
|---|---|
| X01 | Redox-active polymer electrodes for electrochemical carbon dioxide capture from flue gas |
| X02 | DNA-origami nanopores for single-molecule protein sensing |
| X03 | Rare-earth-free magnetocaloric materials for hydrogen liquefaction |
| X04 | Electrochemical ocean alkalinity enhancement for durable carbon dioxide removal |
| X05 | Reprocessable vitrimer composites for recyclable wind-turbine blades |
| X06 | Microbial electrosynthesis of acetate from industrial carbon dioxide emissions |
| X07 | Chip-scale optomechanical accelerometers for inertial navigation |
| X08 | Cold-plasma seed priming for drought-resilient cereal crops |

The fixture freezes order, exact queries, role descriptions, result limits,
request behavior, judge behavior, selection behavior and both gate sets. Once
any X case sends a provider or model request, all eight case identities are
consumed even if the run later fails.

## Frozen provider contract

A future unseen run may use the existing production-disconnected anonymous
OpenAlex response contract, but not a v2, v3 or v4 admission decision:

- one Works request per attempted case, at most eight requests total;
- `search=<frozen query>`, `filter=has_abstract:true`, `per-page=8`;
- topics and keywords are retained for audit but are inadmissible to v5;
- no API key, redirect, internal retry, supplementary fetch or second query;
- every provider row becomes a candidate or an explicit provider rejection;
  and
- provider row indices, request identity, latency and provider-reported usage
  remain complete even when a later case fails.

The model-call ceiling is 16: two batch calls for each of eight cases. There is
no hidden retry or malformed-output repair call. A future authorization may set
a lower request or cost ceiling but may not raise these limits without replacing
this protocol.

## Unseen source-value gates

All gates are conjunctive:

1. at least one selected source set in at least 6/8 cases;
2. at least one relevant, baseline-novel source in at least 6/8 cases;
3. human-confirmed set coverage in at least 6/8 cases;
4. no more than 5% directly irrelevant selected sources;
5. no more than 5% unsupported role assignments among selected sources;
6. candidate-disposition agreement of at least 90%;
7. every provider candidate reviewed and every source URL attempted; and
8. no substantive generative AI producing the human judgments.

The human packet must be label-blind: it exposes the frozen baseline, topic,
role descriptions, title and abstract for every provider candidate, but hides
v5 actions, quotes, selected sets and model traces until aggregation. Reviewers
label direct relevance, baseline novelty and supported roles from the source.
The checker then derives wrong-source rate, unsupported-role rate and set
coverage from those labels. A source that cannot be opened remains visibly
unverified; silence is not a pass.

All provider candidates are reviewed even if the mechanical coverage gate has
already failed. The v4 run showed that stopping at a mechanical failure leaves
the cause unidentified. This additional diagnostic obligation does not relax
the all-gates result or permit production connection.

## Implementation and falsification requirements

Before any development model call or unseen provider request:

- verify the raw fixture hash before JSON parsing or case expansion;
- validate unique case, role, query and candidate identities;
- freeze prompt, parser, quote verifier, selector, runner and adapter hashes;
- persist a complete manifest before constructing an OpenAlex adapter or model
  client;
- commit each pass response and its usage before allowing the next call;
- preserve every provider row and every model disposition through the review
  boundary;
- scrub credentials and fail closed on uninspectable request or cost state;
- prove provider metadata and prior human labels cannot reach the judge;
- prove a computed role or selected source cannot disappear at serialization;
- prove reversed order is actually sent on pass two;
- prove an invented or paraphrased quote cannot authorize a role;
- prove deterministic set-cover tie breaking and the three-source ceiling;
- assert that production modules do not import v5 code; and
- re-inject at least the quote-bypass and computed-but-undelivered defects and
  confirm their seam tests turn red before restoring the implementation.

The implementation phase must run the complete zero-network suite, latest Ruff
and narrow Pylint, then record a separate result. Passing offline tests would
establish only contract implementation, not model quality or source value.

## Explicit non-claims

This pre-registration does not authorize a model call, an OpenAlex request,
private-label access, production import, report connection or planner trigger.
Future development or unseen success would still not establish OpenAlex-wide
precision or recall, literature-wide novelty, source truth beyond the review,
inter-rater agreement, report improvement, decision correctness, adoption,
ROI, latency, an SLO, autonomous tool choice or completed production Tool
Calling.

`pipeline_worker.py` must remain disconnected from the v5 judge, selector,
preflight, adapters, runners and review modules.
