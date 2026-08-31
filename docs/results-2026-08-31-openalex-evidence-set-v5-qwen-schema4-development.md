# Qwen schema-4 evidence-set v5 development result

Date: 2026-08-31
Status: execution completed; frozen mechanical development gate failed
Production connection: not authorized and not performed

## Question

The earlier schema-3 Qwen run stopped on its second request because the frozen
60-second transport timeout expired. Schema 4 persisted a 120-second bound at
every request and artifact seam. This run asked a narrower question: can the
unchanged quote-grounded, order-reversed two-pass evidence-set v5 method finish
under that bounded transport contract and satisfy its pre-registered
development gates?

## Authorization and frozen boundary

The owner authorized one run on exact merged revision
`7a2d73ea9f5d1b4af47e2c6d93aa86999c4711db` with:

- exact model `qwen3.5-plus`;
- the consumed W01-W08 development packet, not the unseen X01-X08 challenge;
- at most 16 sequential calls in a fresh output directory;
- a USD 0.20 soft stop;
- no retry, redirect, repair, fallback, recovery, supplemental search, or
  production connection.

The final zero-network preflight verified the exact revision, schema 4, 8/8
case identities, 64/64 candidate identities, 16/16 prompt and timeout
identities, and a 120-second timeout for every request. It made zero network or
model calls.

## Execution and accounting

| Observation | Result |
|---|---:|
| Completed calls | 16/16 |
| Completed case decisions | 8/8 |
| Persisted candidate decisions | 64/64 |
| Returned model identity | 16/16 exactly `qwen3.5-plus` |
| Total tokens | 74,874 |
| Cached tokens | 0 |
| Conservative known cost | USD 0.113971 |
| Observed request latency | 25.897-49.900 seconds; median 29.680 seconds |
| Retries / recovery calls | 0 / 0 |

The latency values describe only these 16 requests. They are not a percentile,
an SLO, or evidence that 120 seconds is generally optimal.

The artifact index contained 27 files. Recomputing every indexed SHA-256 found
zero mismatches. The schema-4 manifest, all 16 call journals, all eight case
decisions, and the execution record validated through the committed Pydantic
contracts. The configured provider key occurred in zero persisted artifacts.
Planner, report, and production connection flags all remained false.

## Frozen mechanical result

The two order-reversed passes agreed on only 38 of 64 candidate dispositions:
`59.375%`, below the pre-registered `>= 90%` gate. W01 pass 2 and W07 pass 1
returned schema-invalid semantic payloads. The per-case agreement counts were:

| Case | Agreement |
|---|---:|
| W01 | 0/8 |
| W02 | 6/8 |
| W03 | 7/8 |
| W04 | 8/8 |
| W05 | 7/8 |
| W06 | 7/8 |
| W07 | 0/8 |
| W08 | 3/8 |

The deterministic join therefore emitted 0 `KEEP` and 64 `ABSTAIN` decisions;
all eight case-level set selections abstained with `no_valid_candidates`.
Candidate-level abstentions comprised 37 `judge_abstained`, 16
`judge_pass_invalid`, five `judge_action_disagreement`, five
`judge_role_disagreement`, and one `insufficient_context_roles`.

## Decision

The schema-4 transport hypothesis passed: the exact model completed all 16
bounded calls with inspectable accounting and durable artifacts. The semantic
method failed its first conjunctive development gate. Label-dependent gates
cannot make an all-gates protocol pass after this failure, so X01-X08 must not
be opened and evidence-set v5 must not be connected to production Tool Calling.

W01-W08 are consumed development evidence. They must not be tuned on, replayed
and described as validation, or rescued by lowering the frozen threshold. A
future zero-network label join may be useful only as a disclosed failure
diagnostic; it cannot reverse this protocol decision. No further provider call
is authorized by this record.

The raw request and response artifacts remain in the ignored local output
directory
`outputs/2026-08-31-openalex-evidence-set-v5-qwen-schema4-development-7a2d73e/`.
They are not committed because they contain provider-generated text rather than
source-controlled decision evidence.
