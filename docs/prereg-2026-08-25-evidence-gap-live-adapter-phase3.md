# Evidence-gap live provider adapter — phase 3 pre-registration

**Frozen:** 2026-08-25, before the phase-3 provider adapter, manifest, or
runner was written  
**Production connection authorized:** no  
**Live provider requests authorized by this document:** no — execution still
requires a separate, explicit user authorization with a monetary soft stop

## Question

Can the production-disconnected phase-2 executor call Tavily through an adapter
that performs exactly one HTTP request, exposes provider credit usage and
request identity, maps malformed provider rows to inspectable rejections, and
keeps every result quarantined behind the existing URL, domain, relevance,
deduplication, and source-registration boundary?

This is a **provider-compatibility pilot**, not a production Tool Calling test.
The five source collections and their gap intents are frozen fixtures rather
than newly observed production gaps. The experiment therefore cannot estimate
planner trigger precision, user value, report-quality improvement, or a
production success rate.

## Measurement before implementation

The existing data was remeasured before this protocol was written:

- the 30 stored benchmark collections remained 9 `eligible` and 21 `no_gap`;
- all 18 observed signals remained `authority_category_missing`;
- the input collections were unchanged and zero supplementary calls ran; and
- the phase-2 adversarial challenge remained 14/14 exact dispositions, 14/14
  deterministic replays, and at most two simulated attempts per case.

Those nine eligible collections are a development set, and their original
retrieval already searched the corresponding authority endpoints. Reusing
them as evidence of novel search value would therefore be circular.

## Frozen provider contract

The adapter will use Tavily's `POST https://api.tavily.com/search` endpoint.
The request contract is frozen as follows:

1. `search_depth` is explicitly `basic`; `auto_parameters` is false.
2. `include_answer`, `include_raw_content`, and `include_images` are false.
   The adapter retrieves ranked metadata and snippets only; it does not fetch
   result pages.
3. `include_usage` is true, and the response must contain both `usage.credits`
   and `request_id`. A successful response without either field is a failed,
   uninspectable attempt rather than a free request.
4. `max_results` equals the already validated call's `result_limit` and may
   not exceed ten.
5. `include_domains` is chosen from code-owned allowlists for the capability.
   User or model text cannot add a domain.
6. One adapter invocation performs one HTTP request. It has no hidden retry,
   redirect follow, answer generation, extraction request, or page fetch.
   Retry ownership remains in the phase-2 executor.
7. The existing call idempotency key remains the local attempt identity.
   Tavily does not promise provider-side idempotency, so the study makes no
   exactly-once claim.
8. Provider result rows are parsed independently. A malformed row cannot
   discard a valid sibling row, and every dropped row reaches the audit with a
   stable rejection code.
9. The adapter never logs, serializes, hashes into an artifact, or returns the
   API key.

Tavily's official documentation currently defines basic Search as one credit
and pay-as-you-go as USD 0.008 per credit. The pilot freezes the conservative
pay-as-you-go rate of **USD 0.008 per observed credit**, even if the account's
free allowance makes the actual invoice lower. This prevents a free-tier run
from being represented as evidence that the operation has no economic cost.

## Frozen five-case pilot manifest

Each case has one synthetic, immutable `SourceCollection`, one deterministic
gap signal, and one pre-authored `GapSearchIntent`. No planner model runs.
Every case receives an executor attempt limit of one, so the complete pilot can
perform at most five provider requests and five basic-search credits.

| ID | Capability | Topic and frozen gap |
|---|---|---|
| L01 | `academic_search` | Engineered cutinases for enzymatic PET textile recycling; academic retrieval failed |
| L02 | `patent_search` | Closed-pore hard-carbon anodes for sodium-ion batteries; patent retrieval failed |
| L03 | `market_search` | Solid-state transformers for medium-voltage data centres; market retrieval failed |
| L04 | `authority_search` | AI-enabled retinal screening medical devices; FDA/regulatory evidence missing |
| L05 | `authority_search` | Personalised neoantigen mRNA vaccines for pancreatic cancer; clinical-registry evidence missing |

The manifest will store the complete collection and plan identities plus their
SHA-256 values. It is a disclosed compatibility challenge, not a random or
held-out sample of real user runs.

## Execution authorization and budget

The runner must default to dry-run and open no socket. A live run must require:

- an explicit `--execute-live` switch;
- `TAVILY_API_KEY` from the process environment, never a command argument;
- a new output directory that does not already exist;
- the frozen USD 0.008-per-credit accounting rate; and
- a separately supplied soft stop of at least USD 0.04 and no more than
  USD 0.05.

Before each case, the runner must reserve one remaining credit. It stops before
the request if the projected conservative total would exceed the soft stop.
Failures are not retried in this pilot. A transport failure with unknown usage
is `uninspectable`; it is never silently counted as zero cost.

The protocol itself does not authorize those requests. The user must approve
the live run after reviewing the implementation and exact frozen manifest.

## Artifacts and human review

The live runner writes a new directory once with:

- `manifest.json`: frozen case and identity hashes;
- `execution.json`: complete executor and provider audit payloads;
- `candidates.csv`: every returned, adapter-rejected, quarantine-rejected, and
  accepted row at the public artifact seam; and
- `review.csv`: accepted candidates with blank `relevant`, `novel`, and
  `review_note` fields for post-run inspection.

An incomplete review is not a pass. Automated checks may establish request
budget, schema, and quarantine behavior, but `wrong-source rate` and `novel
validated evidence yield` remain `not_inspected` until every accepted candidate
has a completed human label.

## Acceptance criteria for the implementation PR

The code may merge while still production-disconnected only if:

1. the existing zero-network suite, latest Ruff, CI Pylint exception ordering,
   and the 85% coverage floor remain green;
2. injected transports prove that one adapter call performs exactly one HTTP
   request with the frozen body and code-owned domains;
3. provider usage, request id, provider-row rejection, latency, cost, and trace
   data reach the final execution artifact;
4. a one-attempt executor limit prevents retry even for a retryable provider
   failure;
5. dry-run, missing-key, malformed-usage, redirect, and budget-stop paths open
   zero unintended requests and remain observably distinct;
6. the five-case manifest and all generated artifact schemas reject unknown
   fields and identity drift;
7. the production worker still imports neither the phase-2 executor nor the
   Tavily evidence adapter; and
8. reintroducing one hidden-retry defect and one provider-row accounting defect
   makes their targeted tests fail before the defects are removed.

## Criteria for the separately authorized live pilot

The provider-backed pilot is a compatibility pass only if:

- all five manifest identities validate before the first request;
- no more than five HTTP requests and five credits are observed;
- conservative incremental cost is no more than USD 0.04;
- every successful response exposes `request_id` and credit usage;
- zero policy-rejected or schema-invalid rows enter accepted evidence;
- all failures, empty results, and uninspectable usage remain distinct; and
- at least one accepted candidate reaches the human-review packet.

After complete human review, the exploratory value thresholds are:

- wrong-source rate no greater than 5% of accepted candidates; and
- novel relevant evidence in at least 3 of 5 cases.

Missing either threshold blocks production connection. Passing them still does
not satisfy the earlier 90% planner-trigger-precision requirement, because this
pilot injects frozen intents and has no negative planner cases.

## Explicit non-claims

Whether this implementation or pilot passes or fails, it does not establish:

- autonomous Agent tool selection;
- planner precision or recall;
- improvement to a commercialization report;
- production latency, reliability, SLO, or adoption;
- actual invoice cost below the conservative credit estimate; or
- permission to merge supplementary evidence into `validated_sources.json`.

Until a later independently labelled study meets every production threshold,
the accurate description remains:

> A bounded Tool Calling executor has a production-disconnected, single-request
> Tavily adapter and an auditable live-provider compatibility protocol; the
> report workflow remains zero-call shadow mode.
