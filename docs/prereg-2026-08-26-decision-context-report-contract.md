# Pre-registration: decision context and report-contract implementation

**Registered:** 2026-08-26, after the internal baseline census and before code
or prompt changes for this feature

**Implementation evaluation cost:** zero provider calls

## Question

Can the product carry an optional decision context through every durable and
public boundary, distinguish an orientation brief from actor-specific decision
support without guessing, and instruct the existing Writer and Reviewer to
produce a prioritized gated plan without changing the calibrated score?

This implementation study does not ask whether the resulting advice is correct
or useful. Those claims require a separately authorized provider-backed canary
and later target-user review.

## Frozen context contract

The optional `DecisionContext` contains seven bounded, non-secret fields:

- `asset_description`;
- `target_application`;
- `decision_owner`;
- `decision_type`;
- `jurisdiction`;
- `time_horizon`; and
- `constraints`.

Whitespace-only values normalize to absent. Unknown fields are rejected. The
four core fields are asset, application, owner, and decision type. The system
derives exactly one state:

- `orientation`: no decision-context field was supplied;
- `decision_context_incomplete`: at least one field was supplied but one or
  more core fields are absent; or
- `decision_support`: all four core fields are present.

The mode is code-derived, never supplied by the client. Missing context never
blocks an assessment. It changes what the report is allowed to claim.

## Frozen behavior

For every mode, the topic remains the retrieval query and the scoring formula,
weight profile, evidence-confidence floor, source validation, and six-node
topology remain unchanged.

The Writer receives the normalized context as explicitly untrusted data. Under
the fifth existing top-level report section it must state the applicability
mode and provide:

1. one primary commercialization route;
2. alternatives and why they are not primary;
3. the responsible decision owner, or `not established`;
4. evidence still needed and measurable pass thresholds;
5. cost and time state, using `not established` when evidence is absent;
6. stop or kill criteria; and
7. a `GO`, `NO_GO`, or `DEFER` decision only in `decision_support` mode.

In `orientation` and `decision_context_incomplete`, the report must say that an
actor-specific go/no-go decision is not assessed. It may still propose general
next steps, but it must not invent an owner, budget, timeline, jurisdiction, or
decision threshold. The Reviewer may correct decision framing that contradicts
the code-derived mode, but the new screen remains precision-first and does not
turn an otherwise validated paid report into a failed run.

## Identity and observability boundaries

The normalized context is persisted inside the non-secret `RunSpec`; therefore
it contributes to retrieval and task checkpoint identities. Recovery cannot
reuse a report produced for a different decision owner or decision. Existing
version-1 specs remain readable and behave as orientation runs.

Status exposes only a deterministic decision gate: mode, supplied field names,
missing core field names, and whether actor-specific go/no-go output is allowed.
It does not duplicate the user's free text into another public artifact. A run
that predates the feature reports an absent gate rather than a fabricated pass.

## Offline acceptance criteria

The implementation passes only if zero-network tests demonstrate all of the
following seams:

1. API normalization and rejection of unknown or oversized context fields;
2. browser payload to API request;
3. API request to durable `RunSpec`;
4. `RunSpec` context to checkpoint input identity;
5. worker context to CrewAI Writer and Reviewer inputs;
6. mode and decision gate to both status endpoints; and
7. orientation compatibility when context is omitted.

The feature must also leave all pre-existing tests and latest Ruff green. After
the fix, one context-propagation seam will be deliberately removed or mutated;
the new boundary test must fail before the implementation is restored.

## Future paid canary boundary

No provider call is authorized by this document. A future pre-registration may
freeze three topics representing orientation, incomplete context, and complete
decision support. It must define structural criteria before execution, cap
cost, and keep report usefulness and factual correctness as `not_evaluated`
until humans or source checks actually evaluate them.

## Explicit exclusions

This work does not:

- change any score or calibration baseline;
- make the uncited-claim screen blocking;
- add prompt caching or scrape more abstracts;
- upgrade CrewAI;
- connect the evidence-gap executor to production; or
- claim adoption, ROI, time savings, decision accuracy, or six-agent necessity.
