# Results: two-stage target-user decision pilot

**Completed:** 2026-08-26
**Provider cost:** USD 0; the study reused one frozen 2026-08-21 report
**Registered denominator:** two fixed slots, both complete and eligible
**Study status:** `descriptive_pilot_complete`

## Question and boundary

The pre-registered question was whether one previously generated report adds
decision-useful information for actual commercialization decision-makers,
relative to a topic-only baseline recorded before report exposure. This was not
a comparison with ordinary ChatGPT, an analyst team, or the one- and four-node
ablations. There was no pass threshold at this sample size.

The result contains two descriptive observations. It does not establish
adoption, ROI, decision accuracy, hallucination rate, time savings, or
population-level product value.

## Integrity checks

- The protocol, two-slot denominator, ten-topic catalog, source lock, and report
  hashes were committed before recruitment.
- Both reviewers selected topic 08, `quantum computing for drug discovery`,
  before seeing any report. Topic choice was self-selection, not randomization.
- Both received the same frozen report from cell `065-08-full-r1`, SHA-256
  `20b6986877d53314bc49376ae9099374ee53a3095e676c450e20b8a56cb8c45d`.
- Both qualified as target users, completed both stages, consented to anonymous
  aggregate publication, and declared no substantive generative-AI use.
- Each returned Stage 2 form used natural-language `no` where schema v2
  required `NONE`. The original files remain byte-preserved in the private
  audit repository; separate owner-coded copies make the direct semantic mapping
  `no -> NONE`. No outcome field or free-text judgment was changed.
- Neither reviewer opened an external paper, patent, or market source. Source
  truth is therefore `not_evaluated`, not “no errors found.”

## Registered outcomes

| Measure | Observed result |
|---|---:|
| Complete eligible observations | 2 / 2 |
| Decision changes | 0 / 2 |
| Baseline to post-report decision | `DEFER -> DEFER` for both |
| Confidence | 3/5 -> 4/5 for both |
| Median decision usefulness | 3 / 5 |
| Median information gain | 3 / 5 |
| Median actionability | 2 / 5 |
| Median evidence trust | 2 / 5 |
| Median recommendation acceptance | 2 / 5 |
| Median reading time | 57.5 minutes |
| Median estimated revision time | 420 minutes |
| Would use again | `MAYBE`: 2; `YES`: 0; `NO`: 0 |
| Decision-blocking error | `YES`: 1; `NO`: 1 |
| External-source checking | `NONE`: 2 |

Both reviewers had estimated 240 minutes for their normal initial workflow.
Adding reading and estimated revision yielded 535 minutes for T01 and 420
minutes for T02. These are self-reported, differently framed estimates rather
than instrumented task times, but they provide no evidence of time savings.

## What the report did and did not do

The common positive signal was orientation. Both reviewers found value in the
separation between current NISQ limitations and conditional opportunities under
future error-corrected hardware, the hybrid quantum-classical framing, and the
explicit absence of direct deployment evidence. The report increased confidence
in an already cautious `DEFER` decision; it did not move either reviewer toward
commercialization.

The common correction themes were:

1. define a specific academic asset, product, buyer, and decision owner rather
   than assessing a broad sector;
2. require reproducible same-workload comparisons with the strongest classical,
   GPU, and hybrid baselines, including accuracy, wall-clock time, total cost,
   scaling assumptions, independent replication, and prospective wet-lab work;
3. add customer discovery, workflow integration, willingness-to-pay, deployment,
   pricing, unit-economics, team, and capital evidence;
4. separate modelled market estimates and company-wide quantum revenue from
   observed drug-discovery demand and attributable revenue;
5. treat patent white space as a search hypothesis until claims, families,
   assignees, jurisdictions, legal status, and professional FTO review exist; and
6. replace a broad recommendation list with one prioritized option, alternatives,
   quantified milestones, evidence thresholds, owners, costs, and kill criteria.

Both reviewers also identified an internally checkable age inconsistency: a
2018 publication is about eight, not more than ten, years old in 2026. Because
neither opened sources, this observation is not converted into a citation-error
rate or a broader factual-accuracy claim.

## Product implication

The report currently behaves more like an evidence-linked orientation brief
than a decision-ready commercialization memorandum. The next product work should
not add more agents or broader prompts. It should narrow the assessed asset and
decision context, distinguish observed evidence from inference more visibly,
downgrade patent and market extrapolations, and produce a prioritized gated plan
with explicit stop conditions.

A future value study needs more independently recruited target users, more than
one self-selected topic and report, external-source checking or a separate truth
study, and longitudinal evidence that users return or act differently. The
current two observations should remain visible even though they are less
promotional than a success headline.

## Artifacts

- [Pre-registration](prereg-2026-08-26-target-user-decision-pilot.md)
- [Operator guide](target-user-decision-pilot-guide.md)
- [Form-timing erratum](errata-2026-08-26-target-user-pilot-form-enums-and-ai-timing.md)
- [Consent-safe public JSON](results-2026-08-26-target-user-decision-pilot.json)

The private repository retains byte-preserved returns, owner-coded copies,
free-text responses, and the strict private result. The public JSON contains no
free text.
