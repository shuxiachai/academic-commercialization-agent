# Pre-registration: role-slot v6 failure diagnostic

Date: 2026-09-01

## Decision recorded before implementation

The bounded Y01-Y08 role-slot v6 development run is already falsified. It
stopped at the registered Qwen cost boundary after 21 of 24 calls, and two
mechanical gates are mathematically unreachable even under an optimistic Y08
completion. This diagnostic cannot change that result, reopen Y01-Y08, open
Z01-Z08, or authorize production Tool Calling.

The original v6 pre-registration nevertheless requires every provider
candidate to receive a label-blind human review after a mechanical failure.
The provider layer is complete even though the model layer is not: eight
anonymous OpenAlex requests returned eight candidate rows per case, for 64
candidate rows and zero provider rejections. This follow-up therefore measures
the value and role coverage of the frozen provider population already on disk.
It performs no search and no model call.

This document is committed before the diagnostic implementation. The
implementation may enforce this contract; it may not change the questions or
turn descriptive observations into a qualification gate after labels arrive.

## Frozen source identity

The source execution was produced from merged revision
`d23ffd54bb171d1030f5531a7d57bd6eedc5d853` and recorded on public parent
revision `9b5c9524a42ae3e3f73055314246cdfca649919d`. Its local source directory is:

`outputs/experiments/2026-09-01-openalex-role-slot-v6-Y-live-d23ffd54`

The diagnostic must reject any byte drift from these core artifacts:

| Artifact | SHA-256 |
|---|---|
| `manifest.json` | `543c5300f36e7e1f498f66cb51fba88eebefea07e93ada817de15e7291178e17` |
| `execution.json` | `fbd5f42adffeb714937845fcf5f887bd6291989d308fce587da227be63f6754c` |
| `provider-rows.csv` | `c7926e4ae228d3fc16580885ce5b6208a0dc176c39b2650aba6ff833b22bbb8b` |
| `artifact-index.json` | `c7a6472d3d32d990e7f3de5470f8eec3af1963bc15207144e7f994e4f844d38a` |

The implementation must also verify every file named by the 56-entry artifact
index before parsing semantic content. A matching index file without matching
indexed bytes is not a valid source. The eight provider journals and eight
case-execution journals must agree with the aggregate execution and CSV.

The original execution correctly reports `source_lock_readiness=not_ready`
because its full model audit is incomplete. The diagnostic may create a new,
explicitly diagnostic-only source lock only when the provider boundary itself
is complete at 8/8 cases and 64/64 candidates. That exception must never be
accepted by the v6 qualification source-lock path or production code.

## Frozen diagnostic questions

The diagnostic asks only these questions:

1. How many frozen OpenAlex candidates directly address each declared topic,
   and how much retrieval noise is present among inspectable rows?
2. Which code-owned required, scope and supporting roles are supported by each
   frozen title and abstract, and which of those roles have title support?
3. Relative to the synthetic frozen baseline exposed in the packet, which
   directly relevant rows add material evidence?
4. For the 56 candidates with three completed model passes, where do the hidden
   v6 consensus roles disagree with the returned human role labels?
5. Using only returned human role labels and the already frozen deterministic
   selection contract, in how many cases did the retrieved population contain
   a covering set of at most three sources?
6. Are failed cases better explained by retrieval noise, unsupported consensus
   roles, missed supported roles, or an absent covering set?

These are descriptive failure-surface measurements. There is no diagnostic
pass threshold, and no answer can rescue v6 or qualify a successor method.

## Label-blind reviewer boundary

The packet must expose every provider candidate exactly once and include:

- case ID, topic and frozen query;
- the synthetic frozen baseline context;
- the code-owned required, scope and supporting role IDs and descriptions;
- provider result index and candidate SHA-256;
- title, abstract, URL, DOI, publisher, publication date and summary source;
- blank fields for direct relevance, baseline-relative novelty, frozen-text
  sufficiency, supported role IDs, title-supported role IDs and a grounded
  review note; and
- one reviewer declaration covering completeness, generative-AI use, external
  source checks, elapsed time, expertise, date and limitations.

Until labels are returned, the packet and its manifest must hide:

- every model request, pass, slot, quote and response;
- consensus-supported roles and support counts;
- provisional or final candidate actions and abstention reasons;
- selected sources, case actions and gate outcomes; and
- OpenAlex aboutness metadata or any diagnostic attribution derived from the
  hidden execution.

Reviewer-visible identity and context fields are immutable. Rows may be
reordered, but missing, duplicated, extra or altered identities must fail the
summary boundary. Supported-role values must be JSON arrays containing only
role IDs declared for that case; title-supported roles must be a subset of
supported roles. Every non-empty row requires a substantive review note.

## Review eligibility and observable states

The review evaluates the exact frozen title and abstract text. Opening external
sources is encouraged and must be declared, but it is not required for this
text-bound diagnostic. The resulting claims must distinguish frozen-text
judgment from external source truth.

Only `NONE` or `LANGUAGE_ONLY` substantive generative-AI use is eligible. The
summary must expose mutually distinct states:

- blank or partially returned rows/declaration: `incomplete / not_evaluated`;
- substantive generated judgments: `excluded_substantive_ai / not_evaluated`;
- reviewer did not confirm all rows: `not_inspectable / not_evaluated`; and
- complete eligible return: `complete / evaluated_diagnostic_only`.

No state may be named `pass`, and every result must keep
`production_connection_authorized=false`, `z_cohort_authorized=false`, and
`v6_rescue_authorized=false`.

## Frozen aggregation rules

Metrics may be computed only after a complete eligible review. They must retain
all 64 rows in the population and report at least:

- inspectable, directly relevant, directly irrelevant and unverifiable counts;
- retrieval-noise and frozen-text-insufficiency rates with explicit
  denominators;
- relevant and baseline-novel candidate and case counts;
- human-supported role and title-supported role counts;
- for the 56 model-observed candidates, role-level true-positive,
  false-positive, false-negative and true-negative counts plus precision and
  recall when their denominators exist;
- human-coverable case IDs under the frozen one-required, one-context,
  one-title-anchor candidate admission and three-source set-cover contract;
- hidden v6 selected case IDs, missed human-coverable cases, model-selected
  cases without human cover, and model-unobserved cases; and
- an attribution count that keeps retrieval noise, frozen-text insufficiency,
  consensus false positives, consensus false negatives and absent covering
  sets distinct.

The deterministic human set-cover projection must use the same maximum of
three sources and the same smallest-set, provider-index, candidate-SHA ordering
as v6. It is a diagnostic projection from human labels, not a rerun of the
model and not an alternative qualification result.

## Implementation and falsification requirements

Before a packet is handed to a reviewer, the zero-network implementation must:

- verify the four exact core hashes and all 56 indexed file hashes;
- validate the committed Pydantic manifest, execution and provider journals;
- prove all eight cases and all 64 provider candidates reach both the packet
  manifest and labels CSV;
- prove model, consensus and selected-set fields cannot cross the reviewer
  boundary;
- report a blank packet as `not_evaluated`, never zero-error success;
- reject source drift, artifact-index drift, context drift, duplicate rows,
  unknown role IDs, invalid role subsets and substantive-AI review;
- join hidden model traces only inside the post-return summary seam;
- assert that `pipeline_worker.py` cannot import the diagnostic; and
- re-inject at least one hidden-decision leak and one computed-but-not-
  serialized candidate defect, confirm their tests fail, then restore the
  implementation.

The implementation phase must run the focused tests, complete zero-network
suite, latest Ruff and narrow Pylint. It may generate a blank packet locally,
but no private human label may be invented or inferred by code.

## Explicit non-claims

This diagnostic does not establish source truth, OpenAlex-wide precision or
recall, literature-wide novelty, inter-rater agreement, a successor method,
report improvement, decision correctness, user utility, stable cost or
latency, an SLO, autonomous tool choice, or completed production Tool Calling.
It sends no data off the machine and imports nothing into the production
workflow.
