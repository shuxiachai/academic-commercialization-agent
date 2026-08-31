# Analysis plan: Qwen evidence-set v5 failure diagnostic

**Frozen:** 2026-08-31, after the schema-4 W01-W08 development run failed
its mechanical agreement gate and after the two schema-invalid raw responses
had been qualitatively inspected, but before calculating any 64-row join with
the completed human labels.

**Outcome blindness:** no. This is a disclosed post-outcome diagnostic plan,
not a validation pre-registration. The aggregate v5 failure, its 38/64
agreement count, the final candidate reason counts, the earlier human totals
of 28 directly relevant and five semantic-link rows, and duplicate role IDs in
the two invalid responses were already known when this plan was written.

**Production connection authorized:** no.

**Network, model, retrieval, repair or recovery calls authorized:** no.

## Question

Which observable boundary most often prevented the frozen Qwen v5 development
run from retaining human-labelled relevant evidence:

1. a whole-batch invalid pass;
2. stable model abstention;
3. action instability between provider order and reversed order;
4. role-set instability between two KEEP decisions; or
5. a deterministic post-consensus rule?

The result is descriptive. These classes are observable failure surfaces, not
causal estimates. In particular, one invalid response makes every candidate
in that batch unusable even when some raw candidate rows look salvageable.

## Frozen inputs

The public mechanical source is the ignored local directory
`outputs/2026-08-31-openalex-evidence-set-v5-qwen-schema4-development-7a2d73e/`.
The diagnostic must verify the complete artifact index before parsing any
semantic response. At minimum, these externally recorded identities must
match:

- executed revision: `7a2d73ea9f5d1b4af47e2c6d93aa86999c4711db`;
- requested and returned model: exactly `qwen3.5-plus` for all 16 calls;
- manifest SHA-256:
  `df47b0b53003f8347952d2391a9ab9976ff0bdd2cae637018b8d7f69ee29f7a2`;
- execution SHA-256:
  `697472f570f43f9131639244cb19efb79e41fb7941fbf44bc56a79714109d39d`;
- candidate-decision SHA-256:
  `5e958cac0e487e740ae1da23611db12c6f04be1f4d323eaead69cae96b8cce26`;
- 16/16 completed calls, 8/8 completed cases and 64/64 persisted candidate
  decisions; and
- zero OpenAlex requests, retries, recoveries, planner, report or production
  connections.

The private human source is the completed, previously eligible W01-W08
scope-link v4 abstention diagnostic. The tool receives these paths explicitly;
the public repository does not contain or discover them. It must lock:

- source-lock SHA-256:
  `8a9747f4240fc7c529d8d8f2a737fb21b502579ad2f69c19587bf093cabba7af`;
- packet-manifest SHA-256:
  `68e15abdca46f4a65d33a75aedaa9a0eac2112a90a8b1e6eb1d00e71e59b8616`;
- completed labels SHA-256:
  `a2a3a16f74d2a7d8790ca90669702c423b0c24a83ccbf779ca5867cbe6338f55`;
- normalized reviewer declaration SHA-256:
  `5c7686d413f4f3050316950899e7f1806ff2a2a0065eacf0bf39e942917d863d`;
- 64 completed rows with unique `(case_id, candidate_sha256)` identities;
- `reviewed_all=YES`, `generative_ai_use=NONE`, and
  `external_sources_checked=NONE`; and
- the already published totals of 28 directly relevant, 36 directly
  irrelevant and five human-inferred semantic-link rows.

Every label row must match the mechanical packet on case ID, provider index,
candidate SHA, topic, title and URL. A hash, identity, declaration or context
drift aborts the diagnostic; it never becomes an empty or partial result.

## Frozen mutually exclusive classification

Every one of the 64 candidates receives exactly one class, in this order:

1. `invalid_pass_exposure`: either persisted pass is not `valid`;
2. `stable_abstain`: both valid passes return `ABSTAIN`;
3. `action_instability`: one valid pass returns `KEEP` and the other
   `ABSTAIN`;
4. `role_instability`: both valid passes return `KEEP` but the exact role-ID
   sets differ;
5. `post_consensus_rejection`: both valid passes return `KEEP` with identical
   role-ID sets, but deterministic quote/contribution checks return `ABSTAIN`;
6. `stable_keep`: both valid passes agree and the deterministic candidate
   action is `KEEP`.

The diagnostic must reject any row that fits none or more than one class. It
must preserve the final v5 action and abstention reasons rather than inventing
an alternative decision.

## Invalid-response shape probe

For an invalid persisted pass, raw provider content may be parsed only to
describe shape. The probe records whether it is JSON, whether case ID,
candidate order and row coverage match the request, and whether duplicate role
IDs occur within a candidate. It may not deduplicate roles, repair output,
re-run the v5 parser, construct a counterfactual KEEP, or alter the candidate
classification. A shape observation is not evidence that the response would
otherwise have passed quote or selection checks.

## Frozen outputs

The row-level artifact stays private because it joins human labels to provider
outputs. The public result may contain aggregate counts only. Both must report:

- counts by failure class overall;
- counts by failure class among directly relevant and directly irrelevant
  rows;
- counts by failure class among the five human semantic-link rows;
- per-case class counts;
- pass-one and pass-two KEEP counts only where that pass was valid;
- invalid-pass shape observations;
- the number and identities of rows joining successfully; and
- `production_connected=false`, `report_workflow_connected=false`,
  `planner_trigger_connected=false`, and `x_challenge_opened=false`.

The largest class among the 28 directly relevant rows is labelled the
`dominant_observed_failure_surface`; a tie is `mixed`. This label is descriptive
and does not authorize a v6 design.

## Falsification and seam tests

The implementation must prove that:

- changing any indexed mechanical artifact is rejected before label parsing;
- changing label context while retaining candidate IDs is rejected;
- a missing or duplicated candidate cannot change a denominator;
- an ineligible reviewer declaration cannot produce metrics;
- every computed class reaches both the row artifact and aggregate boundary;
- invalid-pass rows cannot be silently reclassified from raw content; and
- production modules do not import the diagnostic.

After implementation, one boundary defect must be re-injected so a new test
turns red before the correct code is restored. The complete zero-network suite,
latest Ruff and narrow Pylint must pass.

## Non-claims and stopping rule

This diagnostic cannot rescue v5, reopen W01-W08, open X01-X08, lower the 90%
gate, estimate source truth, establish causality, validate a repaired parser,
authorize another paid call, or connect Tool Calling to production. Its only
decision use is choosing whether a separately proposed v6 should investigate
response-schema robustness, judge abstention, order stability, or whether this
line of work should stop.

## Input-identity amendment before calculation

The first real invocation validated every mechanical hash and all four private
hashes, then stopped before label joining or output creation because the raw
returned declaration encoded `external_sources_checked` as `0`. The existing
review intake had already preserved that raw file and normalized the owner's
confirmed meaning to the allowed value `NONE` in
`reviewer-packet/reviewer_declaration.csv`. This plan initially named the raw
declaration hash even though the frozen eligibility rule above requires
`NONE`; those two requirements were inconsistent.

The diagnostic therefore uses the already archived normalized declaration
whose hash is recorded above. It does not modify the raw return, infer a new
answer, change any label, or relax declaration eligibility. No diagnostic
row, aggregate, model call, network request, or output file existed before
this amendment.
