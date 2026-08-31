# Pre-registration amendment: role-slot consensus v6 development runner

**Frozen:** 2026-09-01, on top of phase-one revision
`10351fef80090e9a8bf8ed88ee8240698f9939d2`, before implementing the runner
or its model adapter, constructing a provider client, opening a private label,
or sending any Y01-Y08 or Z01-Z08 request.

**Parent method:**
[`prereg-2026-09-01-openalex-role-slot-consensus-v6.md`](prereg-2026-09-01-openalex-role-slot-consensus-v6.md)

**Challenge fixture:**
`tests/fixtures/openalex_role_slot_v6_challenge.json`

**Raw fixture SHA-256:**
`f07c457f81fc5b198cb180874895410a4502b9fe3558c9e21c8b42a1f8240c85`

**Production connection authorized:** no

**Live provider or model calls authorized:** no. This amendment authorizes
only a zero-network runner, adapter and artifact implementation. A later paid
Y01-Y08 run requires a separate user authorization naming the exact merged
revision, provider, model, request ceilings and cost stops. Z01-Z08 remain
unavailable until every frozen Y gate passes.

## Why this phase is separate

The phase-one implementation proved that a malformed candidate row can be
contained locally, exact quotes can be checked mechanically, three pass orders
can be joined deterministically, and every computed role can reach one case
audit. It deliberately imported no provider or model adapter. That result
therefore did not prove the more dangerous paid-call boundaries:

- the frozen method is durable before a credential or network client exists;
- one adapter invocation equals one potentially billable request;
- every spent request and its accounting are durable before a later request;
- every OpenAlex row, model pass, candidate row and role slot reaches a final
  artifact even when a neighbouring value is malformed; and
- an interrupted or uninspectable call cannot be reported as free or passed.

The historical v5 runner already establishes useful transport patterns, but
its two all-candidate response models are part of the failure that v6 replaces.
This phase may reuse strict one-request and write-once mechanics. It may not
reuse v5's batch parser, model-owned candidate actions, two-pass consensus,
consumed W01-W08 inputs, reserved X01-X08 inputs, or post-outcome labels.

## Frozen development scope

Only Y01-Y08 may enter the development runner. Z01-Z08 may be byte-checked and
expanded by the existing zero-network preflight, but a live runner must reject
the unseen cohort before adapter construction. W01-W08 and X01-X08 remain
historical and cannot enter the v6 artifacts.

A complete development attempt may perform at most:

- eight anonymous OpenAlex Works requests, one for each Y case; and
- 24 sequential `qwen3.5-plus` requests, the three frozen candidate orders for
  each case that retained at least one valid provider candidate.

The ceilings are upper bounds, not a requirement to spend. A case with no
valid provider candidate records that state and makes no model call. No retry,
redirect, second query, result-page fetch, semantic repair, fallback, recovery,
parallel call, model substitution or supplementary search is permitted.

## Frozen anonymous OpenAlex contract

The runner must reuse the existing abstract-bearing anonymous OpenAlex Works
response contract rather than introducing a new parser. Each case request:

1. uses the frozen query and Evidence-gap plan identity from phase one;
2. requests `has_abstract:true`, at most eight rows and only the committed
   Works fields;
3. sends no API key and refuses to start when `OPENALEX_API_KEY` is configured;
4. invokes an injected no-redirect, no-retry transport exactly once;
5. requires provider-reported USD accounting and a complete provider-row index;
6. retains candidates and provider rejections separately; and
7. writes the complete provider journal before the first model call for that
   case or any later OpenAlex request.

OpenAlex topics and keywords may remain in the provider response because the
reused parser accounts for them, but they cannot enter a v6 model prompt,
quote check, role consensus, admission decision or set-cover decision. Only
the title, reconstructed abstract, provider index and candidate identity enter
the semantic method.

## Frozen Qwen one-request contract

The v6 adapter is a new historical profile rather than an edit to the sealed
v5 adapter. Every model request must:

1. use `POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`;
2. authenticate only with `DASHSCOPE_API_KEY` in the outbound bearer header;
3. request and accept exactly `qwen3.5-plus`;
4. put `enable_thinking=false` at the top level of the raw JSON body;
5. use JSON Object mode, temperature `0`, non-streaming output and
   `max_tokens=8000`;
6. use a 120-second transport timeout persisted in the request identity;
7. contain the exact phase-one system and user prompt for one of the three
   frozen candidate orders; and
8. invoke its transport once with no redirect, retry, repair, fallback,
   endpoint override, model switch or hidden formatting call.

The response is usable only after validating one non-empty choice, exact
returned-model identity, finish reason, prompt/completion/total token
arithmetic, nested cached tokens, locally reproducible conservative cost,
latency, response identity and raw-content hash. Environment price overrides
must remain disabled for this experiment.

A parseable identity failure may retain only safe returned-model, usage and
latency observations. It may not persist rejected semantic content. Any
potentially spending request without inspectable usage and cost makes model
cost `uninspectable` and stops the run. A syntactically or contract-invalid
semantic JSON object after a transport-successful response remains a completed,
accounted call: it is persisted and converted by the phase-one kernel into an
explicit unavailable pass without repair.

## Frozen request identities and ordering

The manifest must commit all eight OpenAlex calls and all 24 possible model
requests before either adapter is constructed. For each Y case, model calls
remain sequential in this order:

1. `provider_order`;
2. `reverse_provider_order`; and
3. `candidate_sha256_order`.

Each request identity binds the method, case, order, input SHA-256, prompt
SHA-256, exact model, endpoint, timeout, maximum output tokens and production-
disconnection flags. The actual serialized outbound candidate order must be
checked against the persisted input immediately before transport. An internal
list with the correct order is not evidence if the request body carries a
different order.

## Write-once crash and accounting boundary

The implementation must reject an existing output directory. For a new path,
the required sequence is:

1. verify raw fixture and every transitive implementation hash before output
   reservation;
2. create the output directory and write a complete manifest;
3. only then construct the OpenAlex and Qwen adapters or resolve credentials;
4. write each OpenAlex request/response/failure journal before a model call or
   later provider request;
5. write each model request/response/failure journal before another model
   request;
6. after all available passes for a case, write the complete deterministic
   case audit before the next case; and
7. write execution, provider-row, candidate/slot and artifact-index outputs.

The runner records its observed self-hash because embedding its own expected
hash would be recursive. The merged revision named by a future authorization
binds that observed runner. Every other behavior-bearing dependency must have
an expected committed SHA-256 checked before output reservation.

The execution keeps OpenAlex and Qwen accounting separate. Each provider has
`not_observed`, `known` and `uninspectable` states where applicable. A numeric
total is forbidden when any potentially spending request in that provider is
uninspectable. The runner checks a provider-specific soft stop before a later
request, while acknowledging that one in-flight request may exceed it.

The implementation accepts at most USD 0.01 as the anonymous OpenAlex soft
stop and at most USD 0.25 as the Qwen soft stop. The Qwen ceiling is a bounded
engineering limit, not a prediction: the consumed v5 run observed USD
0.113971 for 16 different calls, and v6 permits 24 calls with a different
response shape. A later authorization may choose lower stops.

## Final artifacts and states

Every output model uses `extra="forbid"` and validates totals against its child
journals. The final boundary must retain:

- all provider candidates and provider rejections in exact provider-index
  order;
- every attempted model request and safe response/accounting state;
- all three expected pass identities, including unavailable passes;
- every expected candidate row and fixed role slot for each available pass;
- every quote-verification result, local failure reason, provisional action,
  role consensus, final candidate action and selected source; and
- separate provider, model, mechanical-gate, human-review and production-
  connection states.

`completed` means all eight provider cases reached a durable terminal journal
and every model call made possible by those provider candidates reached a
durable terminal journal. It does not mean a mechanical or human gate passed.
Transport or accounting failure is `partial`. A complete execution calculates
the frozen non-human gates without opening private labels:

- top-level pass contract validity;
- candidate-pass local-valid-row rate;
- code-derived provisional-disposition unanimity;
- selected-set case coverage; and
- serialized boundary completeness.

Human relevance, novelty, role support and wrong-source gates remain
`not_evaluated`. A later label-blind review packet must include every provider
candidate even if the mechanical gates fail. This phase may expose a source-
lock-ready state but cannot open labels or announce a source-value result.

## Required zero-network evidence

Before any paid Y authorization, tests must prove:

1. the real dry-run verifies Y01-Y08, all request identities and all dependency
   hashes while constructing no adapter and opening no socket;
2. the manifest exists before either injected adapter factory runs;
3. a provider journal exists before the first model call for that case;
4. each model journal exists before the next model call and each case audit
   exists before the next provider call;
5. the three actual outbound request bodies carry the three frozen candidate
   orders;
6. top-level, candidate-row and role-slot malformed states remain distinct and
   one bad row or slot cannot erase a valid neighbour;
7. every provider candidate and rejection reaches the aggregate boundary;
8. every computed candidate and role-slot value reaches the final serialized
   boundary rather than stopping in memory;
9. provider or model identity, accounting, timeout and cost failures make no
   retry and cannot produce a false pass or false zero cost;
10. configured OpenAlex credentials, existing output paths and unseen-cohort
    execution fail before adapter construction;
11. the raw Qwen body contains top-level `enable_thinking=false`, exact model,
    JSON Object mode, temperature zero, 8000 output tokens and the frozen
    timeout identity;
12. `pipeline_worker.py` and every production entry point import no v6 kernel,
    runner or experimental adapter; and
13. the complete zero-network suite, latest Ruff and narrow Pylint pass.

At least two paid-boundary defects must be re-injected and observed red before
restoration: moving manifest persistence after adapter construction, and
dropped or reordered candidate/slot data at the final client artifact. The
phase-one whole-batch, quote and set-cover tests remain required and cannot be
weakened or skipped.

## Explicit non-claims

This amendment does not authorize or perform a provider request, model call,
private-label read, review aggregation, report insertion, planner trigger or
production import. Passing the runner tests would establish only a durable,
bounded and inspectable disconnected execution contract. It would not
establish model compliance, semantic accuracy, source truth, OpenAlex precision
or recall, Tool Calling value, report improvement, user utility, cost or
latency stability, an SLO, autonomous tool choice, or completed production Tool
Calling.

`pipeline_worker.py` must remain disconnected from the v6 kernel, fixture,
preflight, runner, adapters, outputs and any later review module.
