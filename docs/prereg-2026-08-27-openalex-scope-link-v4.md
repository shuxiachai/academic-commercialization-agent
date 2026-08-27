# Pre-registration: OpenAlex scope-link candidate v4

**Frozen:** 2026-08-27, after the completed claim-scope v3 review but before
implementing this candidate, calculating any v4 decision, or requesting an
OpenAlex response for W01-W08.

**Challenge fixture:**
`tests/fixtures/openalex_scope_link_v4_challenge.json`

**Raw fixture SHA-256:**
`f4267c6a79c0bb8a685664de5086e4cfff59ebac1b352cbb56c2277957a55cc3`

**Production connection authorized:** no

**Live provider requests authorized:** no. Any live execution requires a
separate authorization naming a merged revision, request cap and soft stop.

## Why another representation is needed

Claim-scope v3 completed one eligible human review over 13 accepted sources.
Twelve were directly relevant and baseline-novel; one was directly irrelevant.
The resulting 7.69% wrong-source rate exceeded the frozen 5% maximum even
though accepted-case and novel-relevant coverage both passed at 7/8.

This is not evidence that the provider-score floor should move. The failed
source satisfied the two required process/application groups and enough
optional supporting groups while omitting the topic-defining material scope.
The representation allowed a generic performance group to substitute for a
named material, route or operating context. Raising an additive count would
not express that relationship and would be post-result threshold tuning.

V01-V08 are sealed failure evidence. Their rows and labels may explain the
failure class, but they may not be replayed to select phrases, thresholds or
profiles for v4, and they may not be rerun and described as unseen validation.
The v4 fixture instead freezes eight different topics. A repository search of
the parent `main` revision found none of the eight exact topic strings before
the fixture was added.

## Frozen scope-link rule

The candidate is a deterministic, role-structured source gate. It does not use
an embedding model or an LLM relevance judge: neither has a calibrated
precision boundary in this project, and either would make the decisive source
admission less inspectable while adding a paid or heavyweight dependency.
"Scope link" here means an explicit relation between code-owned concept roles,
not a claim of general semantic understanding.

Each profile contains three disjoint kinds of concept group:

1. **required groups** describe the central technology and result. Exact title
   or abstract text may satisfy them; an OpenAlex topic or keyword with score
   at least `0.55` may bridge at most one;
2. **scope groups** describe the topic-defining material, route, platform or
   operating context. They can be satisfied only by exact source text; and
3. **supporting groups** describe measurements, mechanisms or secondary
   context. They can be satisfied only by exact source text.

Matching uses Unicode NFKC normalization, case folding and complete token
sequences. One normalized phrase may not belong to two independent groups.
Provider metadata cannot satisfy scope or supporting groups.

A candidate is `ACCEPT` only when all of the following hold:

1. every required group matches through text or the bounded provider channel;
2. at least the profile's frozen number of required groups matches exact text;
3. no more than the frozen number of required groups is provider-only;
4. at least the frozen number of scope groups and supporting groups matches
   exact source text;
5. at least the frozen number of scope groups is **linked** to an exact
   required group in the same title or the same abstract sentence; and
6. the title contains at least the frozen number of exact required-or-scope
   group anchors.

Otherwise the action is `ABSTAIN` with explicit reasons. There is no `DROP`,
profile relaxation, model fallback, source-page fetch or second request. Every
link must expose the field, sentence index, required group, scope group and the
exact phrases that established it. Candidate identity binds the evidence text
and all provider aboutness metadata; profile identity binds every phrase and
threshold.

## Frozen request contract

A future run may reuse the existing production-disconnected OpenAlex response
contract, but not its v3 decision:

- one anonymous Works request per attempted case;
- `search=<frozen query>`;
- `filter=has_abstract:true`;
- `per-page=8`;
- selected fields include the evidence fields, `topics` and `keywords`;
- no API key, redirect, internal retry, enrichment fetch or model call; and
- every provider row becomes a candidate or an explicit provider rejection,
  with complete row indices and provider-reported USD accounting.

The v4 preflight must import neither the adapter nor a transport. A later live
runner must freeze the adapter, method, fixture and runner bytes before output
reservation or adapter construction.

## Unseen W01-W08 challenge

| ID | Frozen topic |
|---|---|
| W01 | Agricultural-waste hard-carbon anodes for sodium-ion grid batteries |
| W02 | Continuous-flow cell-free enzymatic synthesis of rare HMOs |
| W03 | Plasma-assisted ammonia cracking with earth-abundant catalysts |
| W04 | Scaffold-free acoustic bioprinting of vascularized organoids |
| W05 | Copper-free electrochemical nitrate-to-ammonia conversion in wastewater |
| W06 | Marine-degradable PHA barrier coatings for paper food packaging |
| W07 | Event-camera robotic soft-fruit harvesting with tactile grippers |
| W08 | Bioleaching recovery of rare earths from coal fly ash |

The fixture freezes case order, queries, result limits, all concept roles,
thresholds, the request contract and value gates. A preflight must produce
eight distinct collection, plan, profile and idempotency identities while
opening zero sockets.

## Source-value gates

The thresholds remain unchanged rather than being weakened after v3:

1. at least one accepted candidate in at least 6/8 cases;
2. at least one relevant and baseline-novel candidate in at least 6/8 cases;
3. no more than 5% directly irrelevant accepted candidates;
4. every attempted source reviewed; and
5. no substantive generative AI producing the human judgments.

A mechanically completed run with fewer than six accepted cases stops before
human review because no labels can rescue its all-gates result. Missing source
truth remains `not_evaluated`, never zero error.

## Implementation and falsification requirements

Before any provider request:

- validate the raw fixture hash before JSON parsing or case expansion;
- fail closed on duplicate roles, duplicate normalized phrases and impossible
  thresholds;
- expose exact group and sentence-link provenance after serialization;
- prove provider-only scope cannot authorize a source;
- prove concepts in different abstract sentences do not create a false link;
- assert that all v4 modules remain absent from `pipeline_worker.py`;
- re-inject a missing-scope-link defect and confirm the seam test turns red;
- run the complete zero-network suite, latest Ruff and narrow Pylint; and
- record implementation results without claiming source value.

## Explicit non-claims

Dry-run success would establish only deterministic identities and the intended
contract. Even a later source-value pass would not establish OpenAlex-wide
precision or recall, literature-wide novelty, source truth beyond the review,
planner-trigger precision, report improvement, decision correctness, adoption,
ROI, latency, an SLO, autonomous tool choice or production Tool Calling.

`pipeline_worker.py` must remain disconnected from the v4 gate, preflight,
adapter, any future live runner and any review module.
