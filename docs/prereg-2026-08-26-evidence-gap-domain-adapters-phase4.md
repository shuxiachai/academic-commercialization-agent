# Evidence-gap domain adapters — phase 4 pre-registration

**Frozen:** 2026-08-26, before either domain adapter or its audit runner was
implemented

**Production connection authorized:** no

**Live provider requests authorized by this document:** no

**Frozen challenge:**
[`evidence_gap_phase4_domain_challenge.json`](../tests/fixtures/evidence_gap_phase4_domain_challenge.json)

## Why this experiment exists

The production-disconnected Phase 3 Tavily pilot completed its request,
quarantine and cost-accounting contract, but its returned review contained only
5/25 directly relevant candidates. The academic and patent cases each produced
0/5 directly relevant rows. Even if the ineligible review declaration were
ignored, the descriptive 80% wrong-source rate would fail the frozen 5% limit.

That result rejects one generic web-search adapter as an evidence source. It
does not establish that bounded Tool Calling itself has no value. Phase 4 tests
the narrower hypothesis that source-native, domain-specific APIs can generate
more selective academic and patent candidates without weakening the existing
executor, quarantine, or audit boundaries.

The production collector already uses OpenAlex and optionally Lens. These new
adapters are therefore **not** being presented as new production data sources.
They are isolated one-request implementations that let the bounded executor be
tested honestly. Reusing a retrying production client would hide requests from
the executor and make the experiment's budget claim false.

## Frozen question

Can one OpenAlex request for an academic gap and one claim-oriented Lens request
for a patent gap:

1. return every provider row through a strict, auditable schema boundary;
2. keep retry, redirect and result-page requests at zero inside the adapter;
3. preserve provider-reported cost when available and mark it uninspectable
   when it is not available;
4. improve candidate precision on a challenge that was not used in Phase 3;
   and
5. remain disconnected from the report workflow?

## Provider contracts frozen before implementation

### OpenAlex academic adapter

- One `GET https://api.openalex.org/works` request per invocation.
- The validated gap query is sent through `search`; `per-page` equals the
  validated result limit and is at most five for this challenge.
- `select` is limited to root-level work metadata needed for a candidate:
  work id, title, DOI, publication date, primary location, citation count and
  abstract inverted index.
- An `OPENALEX_API_KEY` is required for a live adapter. The key may appear only
  in the outbound query parameter required by the current API contract. It may
  not reach returned objects, artifacts, exception messages or logs.
- A successful envelope must contain `meta.cost_usd`. Missing cost is a failed,
  uninspectable response rather than a free request.
- A row without a usable record URL, title or reconstructable abstract is an
  explicit provider-row rejection. The adapter will not scrape a second page to
  fill the abstract.

The contract follows the current official OpenAlex documentation for
[authentication](https://developers.openalex.org/api-reference/authentication),
[work search](https://developers.openalex.org/api-reference/works/list-works),
and [root-field selection](https://developers.openalex.org/guides/selecting-fields).

### Lens patent adapter

- One `POST https://api.lens.org/patent/search` request per invocation.
- The request searches title, abstract and the documented singular `claim`
  query field, with title boosted and at least one branch required.
- The response is limited to Lens id, bibliographic title/publication data,
  abstract and claims. No patent page is fetched.
- `LENS_API_KEY` is required and may exist only in the Authorization header.
- Lens does not expose a trustworthy per-request monetary value in the response
  contract used here. Successful calls therefore report cost as
  `uninspectable`, never zero. Any future live study must be bounded by request
  count as well as a separately reviewed account limit.
- A candidate requires a usable title, Lens id and abstract. Claim text affects
  retrieval but is not mislabeled as an abstract or search snippet.

The request shape follows the current official Lens
[patent request](https://docs.api.lens.org/request-patent.html) and
[patent query examples](https://docs.api.lens.org/examples-patent.html).

### Shared boundary

- One adapter invocation equals exactly one outbound request.
- Adapters own no retry, redirect follow, result-page fetch or source
  registration. Retry ownership remains in the existing bounded executor.
- Every returned row is either a candidate or an inspectable rejection. Rows
  cannot disappear between the provider envelope and the execution audit.
- Providers that do not return a request id use a secret-independent,
  client-generated request fingerprint. The audit must label that identity as
  client-generated and must not call it provider-owned.
- Candidates remain unregistered until the existing URL allowlist, SSRF,
  evidence-domain, relevance and deduplication quarantine accepts them.
- The production worker must import neither domain adapter nor the experimental
  executor.

## Frozen challenge

The byte-frozen manifest contains eight previously unused topics: four
academic cases (`D01`–`D04`) and four patent cases (`D05`–`D08`). Each case has
one pre-authored query and a five-result limit. It is a disclosed diagnostic
challenge, not a representative sample or statistical benchmark.

The frozen fixture SHA-256 is
`f9eee1fcf2ff5acb75e9da840b94baa43e3b10f7e3136dec9886c3a572663a24`.
Any byte change creates a new experiment rather than silently updating this
one.

No model selects the provider or writes a query in this experiment. This
isolates adapter value from planner precision and avoids charging for an LLM
whose behavior is not under test.

## Acceptance criteria for the implementation PR

The implementation may merge while remaining production-disconnected only if:

1. all eight frozen cases validate in a zero-network dry run before an adapter
   can be constructed;
2. injected transports prove each adapter invocation performs exactly one
   request and follows zero redirects;
3. wrong tool/provider pairings fail before transport;
4. result limits, every provider row, request identity provenance, cost state,
   rejections and trace data reach the final executor seam;
5. missing keys, malformed envelopes, missing OpenAlex cost, redirects and
   over-limit responses are observably distinct and never reported as free;
6. secrets do not occur in serialized responses, artifacts or raised error
   text;
7. one hidden-retry defect and one row-accounting defect make targeted tests
   fail when reintroduced;
8. the full zero-network suite, latest Ruff, CI Pylint exception-order check and
   coverage gate remain green; and
9. the production worker remains disconnected by an import-boundary test.

## Criteria for a later, separately authorized provider run

A live run is not part of this implementation PR. Before any request, a later
protocol must bind to the exact fixture bytes and adapter revision, require a
new write-once output directory, cap the run at eight requests, and receive
explicit user authorization. OpenAlex reported cost and Lens uninspectable cost
must remain separate; they may not be summed into a falsely precise total.

After every quarantine-accepted candidate receives an independently declared
human label through a schema-v2 packet that exposes baseline context, the
domain strategy passes its value gate only if **both providers** satisfy:

- at least one quarantine-accepted candidate in at least 3/4 cases;
- wrong-source rate no greater than 5% of quarantine-accepted candidates; and
- at least one relevant, novel candidate in at least 3/4 cases.

Zero accepted candidates cannot pass. Incomplete review, inaccessible sources,
substantive generated labels, missing baseline context, or uninspectable
execution accounting remains a non-pass rather than an inferred success.

## Explicit non-claims

Passing implementation tests or a later challenge would not establish:

- autonomous Agent tool choice;
- planner trigger precision or recall;
- superiority over the deterministic production collector;
- improvement to final report quality or user decisions;
- a production SLO, recovery rate, latency or monetary saving; or
- permission to register supplementary candidates in a production report.

Until the later human-value gate and then a separate planner-trigger study pass,
the accurate description remains:

> The bounded Tool Calling executor has production-disconnected, one-request
> domain-adapter contracts for academic and patent evidence; production reports
> do not consume their candidates.
