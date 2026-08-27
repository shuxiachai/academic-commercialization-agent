# Pre-registration: provider-assisted OpenAlex claim-scope candidate v3

**Frozen:** 2026-08-27, before any OpenAlex response was requested for V01-V08.

**Authority:** implementation and zero-network dry-run only. This document does
not authorize a live provider request, a production import, a report-workflow
connection, or a change to the existing precision-v2 result.

## Why a different method is needed

The precision-v2 unseen run returned 40 OpenAlex rows across U01-U08:

| Observation | Count |
|---|---:|
| Provider rows | 40 |
| Provider-schema/abstract rejections | 9 |
| Legacy quarantine rejections | 8 |
| Rows evaluated by precision v2 | 23 |
| `ACCEPT` | 5 |
| `ABSTAIN` | 18 |
| Abstentions carrying `missing_required_groups` | 18 |
| Cases with at least one acceptance | 3/8 |

This establishes a mechanical failure mode: all 18 v2 abstentions missed at
least one exact required phrase. It does **not** establish that those rows were
relevant. No human source-truth review was performed on the 23 rows, so lowering
the exact-conjunction threshold against them would tune to an unknown label.

The provider rejection count also exposes a separate retrieval-budget problem:
works without a reconstructable abstract consumed 9 of 40 bounded result slots.
The next request contract therefore asks OpenAlex for `has_abstract:true`
rather than trying to fetch missing abstracts after the request. A second fetch
would violate the one-request budget.

## Provider-native signal, not provider truth

OpenAlex documents that Works search covers title, abstract and full text and
uses stemming and stop-word removal:
<https://help.openalex.org/api/searching/>. Hand-writing a larger synonym list
inside the query would therefore duplicate provider behavior without making
the downstream decision auditable.

OpenAlex also exposes Works `topics` and `keywords`. Topics are assigned from
work metadata by a classifier, while keywords are derived from topic
assignments and carry scores:

- <https://help.openalex.org/data/works/attributes/>
- <https://help.openalex.org/data/topics/>
- <https://help.openalex.org/data/keywords/>

Those fields can describe document aboutness, but they do not prove a paper's
claim and may be wrong. Candidate v3 treats them as a bounded secondary channel
whose contribution is visible in every decision.

## Frozen candidate rule

Every case declares independent required and supporting concept groups. Each
group has two vocabularies:

1. `text_phrases`, matched as complete Unicode-normalized token sequences in
   the title or abstract;
2. `provider_terms`, matched as complete token sequences in OpenAlex topic or
   keyword labels whose score is at least `0.55`.

A candidate is `ACCEPT` only when all of the following hold:

1. every required concept group matches through either channel;
2. at least one required group matches source text;
3. at least one required group matches the title;
4. at most one required group is supported only by provider aboutness;
5. at least two supporting groups match.

Otherwise the action is `ABSTAIN`, with explicit reasons. There is no `DROP`
action. Every match records the exact title phrases, abstract phrases, provider
label, provider field, score and frozen term that matched. Candidate identity
includes the evidence row and all provider aboutness metadata.

This design permits one semantic bridge such as a provider label for an alias
that is absent from the abstract, while preventing provider labels alone from
authorizing an apparently relevant paper.

## Frozen request contract

Each attempted case permits exactly one anonymous OpenAlex Works request:

- `search=<frozen query>`;
- `filter=has_abstract:true`;
- `per-page=8`;
- `select` includes the existing evidence fields plus `topics` and `keywords`;
- no API key;
- no redirect following, internal retry, result-page fetch or enrichment;
- every returned row must become either a candidate or an explicit provider
  rejection, with complete row indices and provider-reported USD accounting.

OpenAlex documents `has_abstract` as a Works filter and root-field `select`:
<https://help.openalex.org/api/filtering/> and
<https://help.openalex.org/api/selecting-fields/>. A future live runner must
still freeze its own transport and implementation hashes before it may rely on
this request shape.

## Unseen challenge

The byte-frozen fixture is
`tests/fixtures/openalex_claim_scope_v3_challenge.json`, SHA-256
`f8084328d56fed9c5b2aaafa1eb2225b0798d30266cc12c34522e1cd1243be86`.
Its eight topics were not used in D01-D04 or U01-U08:

| ID | Frozen topic |
|---|---|
| V01 | Near-field thermophotovoltaic conversion with nanophotonic gap control |
| V02 | Photocatalytic methane coupling to ethylene under ambient conditions |
| V03 | Focused-ultrasound drug delivery across the blood-brain barrier |
| V04 | Silicon-photonic FMCW LiDAR with integrated lasers |
| V05 | Electrochemical lithium extraction from geothermal brines |
| V06 | Passive-radiative-cooling textiles for personal thermal management |
| V07 | Spray-induced RNA silencing for fungal crop disease control |
| V08 | Biomass-aerogel interfacial solar evaporation for desalination |

The preflight must produce eight distinct collection, plan, profile and
idempotency identities while opening zero sockets. Case order, result limit,
request fields, profiles and source-value gates are part of the raw-byte lock.

## Future live and human-value gates

A separately authorized complete observation may make at most eight requests.
It is a candidate only if a provenance-locked human review later establishes:

1. at least one v3-accepted candidate in at least 6/8 cases;
2. at least one relevant and novel candidate in at least 6/8 cases;
3. a wrong-source rate no greater than 5% among evaluated candidates;
4. every attempted source was reviewed;
5. no substantive generative AI produced the review judgments.

Failure is a result. No profile, score floor, case, query or gate may be edited
after a provider response. Failed cases may not be replaced or rerun.

## What any future result may and may not establish

Even a pass would be evidence only for candidate-source value on these eight
frozen academic cases. It would not establish source truth beyond the review,
report improvement, planner-trigger precision, production reliability,
commercial value, adoption, or a general OpenAlex precision rate.

Until both live execution and an eligible human review pass, the correct state
is `not_evaluated`. `pipeline_worker.py` must remain disconnected from the new
gate, adapter and any later runner.
