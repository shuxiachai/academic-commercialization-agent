# Pre-registration: two-stage target-user decision pilot

**Registered:** 2026-08-26, before recruitment packets, target-user intake,
or follow-up labels exist

**Cost:** zero provider calls; frozen full-workflow reports only

**Planned slots:** two (`T01` and `T02`)

## Question

When an actual commercialization decision-maker reads one previously generated
production-workflow report in a topic they understand, what decision-useful
information does it add relative to their topic-only baseline, how much work
would they need to correct it, and would they choose to use this kind of report
again?

This is a small qualitative product pilot, not a topology experiment. It does
not compare the six-stage workflow with the monolith, ordinary ChatGPT, an
analyst team, or a freshly researched report. It cannot establish adoption,
ROI, decision accuracy, hallucination rate, or population-level product value.

## Why this is a separate study

The completed 2026-08-23 utility audit is closed. It contains twenty eligible
blinded judgments from five reviewers, but only one reviewer was an actual
target user. Adding new people to that denominator after seeing its 6:4 result
would invalidate the frozen design. This pilot therefore has new reviewer IDs,
a different question, separate artifacts, and no attempt to rescue or reinterpret
the failed topology criterion.

The pilot also answers a more relevant product question. A target user normally
receives one report and decides whether it helps; they do not compare two hidden
workflow architectures. The two-stage procedure preserves a topic-only baseline
without imposing a second 4,000-word report.

## Frozen source material

The source experiment is
`outputs/ablation/20260821T234300Z-7dd894ef`. The catalog contains the ten
benchmark topics already present in that experiment. For each topic, the source
report is the successful `full` cell at repetition 1. All ten such cells exist.

The coordinator lock records, before recruitment:

- topic number, topic text, and industry;
- source cell and frozen-evidence digest;
- source report path and SHA-256; and
- source metadata path and SHA-256.

No report is regenerated, shortened, translated, or selected because of a known
human preference. The exact delivered `commercialization_report.md` is used,
including its limitations and reviewer appendix, because this pilot measures the
delivered artifact rather than architecture blinding. The reports were generated
on 2026-08-21 from frozen evidence and must be described that way; they are not
fresh market research.

## Recruitment and fixed denominator

Two slots are registered: `T01` and `T02`. Eligible target roles are:

1. technology-transfer or research-commercialization staff;
2. investment, venture, or due-diligence personnel;
3. industry research, consulting, product-strategy, or commercialization staff;
4. founders or senior researchers with direct commercialization evaluation
   responsibility.

A technical reviewer without such responsibility is retained as a proxy but is
not counted in the target-user headline. Relevant experience and domain are
recorded instead of inferring expertise from a job title.

A person may replace a slot only if its intake has not started. No third slot is
added after either follow-up is seen. One eligible completion is reported as a
`single_target_user_observation`; two are a `descriptive_pilot_complete`. Neither
state means that the product passed a validation threshold.

## Two-stage procedure

### Stage 1: baseline before report exposure

Each reviewer receives only a topic catalog and an intake form. They choose one
topic based on direct professional familiarity before any candidate report is
sent. The form records:

- role category, experience band, domain, and AI-assistance declaration;
- selected topic and why it is relevant to their work;
- their current commercialization-assessment workflow;
- estimated minutes their normal process would require;
- topic-only `GO`, `NO_GO`, `DEFER`, or `UNCERTAIN` decision;
- topic-only confidence from 1 to 5; and
- information they would need before acting.

The coordinator locks the completed intake before creating Stage 2. Choosing a
familiar topic improves ecological relevance but introduces self-selection;
cross-topic outcomes therefore cannot be compared as if topics were randomized.

### Stage 2: frozen report and follow-up

The coordinator sends exactly the locked topic's report plus a follow-up form.
The reviewer records:

- decision and confidence after reading;
- decision usefulness, information gain, actionability, evidence trust, and
  recommendation acceptance from 1 to 5;
- reading minutes and estimated correction/revision minutes;
- `YES`, `MAYBE`, or `NO` willingness to use this report type again;
- whether no, some, or all cited sources were opened;
- factual-error state as `NOT_CHECKED`, `NONE_FOUND`, `ONE_FOUND`, or
  `TWO_PLUS_FOUND`;
- whether a potentially decision-changing error was found, with details;
- the most useful content, missing information, required corrections, and a
  concise rationale.

`NONE_FOUND` is invalid when no source was opened. A changed decision is not
treated as a more correct decision. Estimated normal-process and revision times
are self-reports, not instrumented productivity measurements.

## AI use, privacy, and source checking

The requested procedure is no generative AI for substantive judgments.
Translation or clerical assistance is retained with disclosure. A form that
declares substantive AI-generated judgment remains in the audit trail but is
excluded from the human target-user summary.

Reviewers are identified publicly only by `T01` or `T02`. Names, employers,
contact details, and exact job titles are not collected in the public artifact.
Anonymous aggregate publication requires explicit consent. Declining consent
does not erase the private operational record, but that row cannot appear in a
public case study.

Opening external sources is optional because this pilot primarily measures
workflow utility. Source truth is `not_evaluated` unless the reviewer actually
opens sources. Report-internal plausibility must never be described as verified
factual accuracy.

## Analysis and reporting

There is deliberately no pass/fail product threshold at this sample size. The
result reports every eligible reviewer separately and, only when both complete,
descriptive counts or medians for:

- post-report decision and whether it changed;
- confidence delta;
- five utility ratings;
- reading and estimated revision time;
- willingness to use again;
- citation-check coverage and factual-error state; and
- blocking-error observations and requested corrections.

The public result must disclose slot count, eligible target-user count, role
mix, AI use, source-opening coverage, missing forms, topic self-selection, and
the age and frozen nature of the reports. It may state exact observations such
as “2/2 target users rated usefulness at least 4/5” only if that is what the
locked forms say. It may not generalize those observations to target users as a
population.

## Artifact and implementation boundaries

The implementation must remain zero-network and must:

- freeze all ten source and metadata hashes before intake;
- keep the source lock outside every reviewer delivery directory;
- create Stage 1 without any report body or report path;
- refuse Stage 2 until one complete, valid intake selects a catalog topic;
- materialize exactly one locked report per reviewer;
- preserve reviewer, topic, source, and delivered-report hashes at every seam;
- distinguish not started, incomplete intake, report not materialized,
  incomplete follow-up, proxy-only, AI-excluded, single-user, and complete-pilot
  states;
- reject changed identifiers, duplicate rows, invalid enum combinations, source
  drift, report drift, and output overwrite; and
- keep any public summary separate from private free-text responses.

After implementation tests pass, the selected topic or delivered report hash
will be deliberately changed. A boundary test must fail before the artifact is
restored. This pre-registration must remain an earlier commit than packet
implementation and every human response.
