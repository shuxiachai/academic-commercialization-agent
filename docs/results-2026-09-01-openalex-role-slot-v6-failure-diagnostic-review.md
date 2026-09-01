# Result: role-slot v6 failure diagnostic human review

**Completed:** 2026-09-01

**Status:** `complete / evaluated_diagnostic_only`.

**Authority:** descriptive interpretation of the 64 frozen Y01-Y08 OpenAlex
titles and abstracts by one independent human reviewer. This result cannot
repair the failed v6 gates, open Z01-Z08, validate a successor, establish
source truth, or authorize production Tool Calling.

## Why this review exists

The v6 development run was already irrecoverably failed after 21 of 24 Qwen
calls. Even perfect Y08 outputs could not reach either the frozen candidate
unanimity or selected-case coverage gate. The OpenAlex boundary was complete,
however, so the original protocol still required a label-blind review of all
64 provider candidates to distinguish retrieval, role-assignment, admission,
and incomplete-execution failure surfaces.

The packet exposed each frozen topic, query, synthetic baseline, code-owned
role description, title, abstract, and bibliographic identity. It hid every
Qwen pass, consensus role, candidate action, selected set, and automated
failure attribution until after the completed return was validated.

## Eligible return

One anonymous human reviewer completed all 64 rows in 40 minutes and declared:

- all rows reviewed: `YES`;
- substantive generative-AI use: `NONE`;
- external sources checked: `NONE`;
- expertise: not supplied; and
- limitations: not supplied.

The project owner explicitly confirmed that the return was completed by a
human. The returned declaration used `2026/9/1`, while the strict schema
requires ISO `YYYY-MM-DD`. The two returned files were preserved byte for byte
in the private audit archive before only that date was normalized to
`2026-09-01`. No label, note, candidate identity, reviewer identity, elapsed
time, AI-use declaration, external-source declaration, expertise field, or
limitation field was changed.

The zero-network summarizer revalidated the exact source lock, 56 indexed
artifacts, packet manifest, all 64 candidate identities, allowed role IDs, and
title-role subset rule. The result is complete with no method issue and no
incomplete row.

## Frozen-text source result

| Measure | Result |
|---|---:|
| Completed rows | 64 / 64 |
| Directly relevant | 13 / 64 (20.31%) |
| Directly irrelevant retrieval noise | 51 / 64 (79.69%) |
| Unverifiable from frozen text | 0 / 64 |
| Relevant and baseline-novel candidates | 13 |
| Cases with a baseline-novel relevant candidate | 6 / 8 |
| Cases with a human-covering evidence set | 3 / 8 |
| Human-coverable cases | Y04, Y05, Y06 |
| Model-observed candidates | 56 / 64 |

Only Y04, Y05, and Y06 contained a set of at most three candidates that met
the frozen role-coverage contract under the human labels. Each of those cases
was coverable by one candidate. Five cases had no human-covering set, so the
frozen run could not have met its 6/8 selected-case gate even with perfect
model judgments over the same candidate pool.

The 13 relevant and baseline-novel candidates occurred in Y01, Y02, Y04, Y05,
Y06, and Y08. A relevant paper is therefore not automatically a sufficient
role-covering evidence set. Y08 was not observed by the model because the
pre-registered soft stop ended the run before its three calls.

## Hidden-trace comparison

The hidden v6 traces were joined only after the eligible return.

| Candidate admission over 56 observed rows | Count |
|---|---:|
| True positive | 9 |
| False positive | 7 |
| True negative | 38 |
| False negative | 2 |

This is a derived 56.25% candidate-admission precision and 81.82% recall on
the consumed diagnostic set. The model selected Y03, Y04, Y05, and Y06. It
covered all three human-coverable cases but also selected Y03, for which the
human labels found no valid covering set.

| Role assignment over observed candidate-role slots | Count |
|---|---:|
| True positive | 93 |
| False positive | 14 |
| True negative | 163 |
| False negative | 10 |
| Precision | 86.92% |
| Recall | 90.29% |

Fourteen observed candidates contained at least one consensus role unsupported
by the reviewer, while ten omitted at least one human-supported role. These
counts may overlap and are candidate-level diagnostics, not independent error
rates.

Title anchors were precision-first but incomplete: 27 true positives, two
false positives, 229 true negatives, and 22 false negatives produced 93.10%
precision and 55.10% recall. This supports retaining title evidence as a
high-precision signal, but not using it as the sole role-support requirement.

## Interpretation

The dominant observed bottleneck is upstream candidate quality. Nearly four
out of five OpenAlex rows were directly irrelevant, and five of eight cases
did not contain a human-covering set. Buying the three missing Qwen calls,
adding more consensus passes, or lowering the frozen thresholds could not fix
that missing candidate evidence.

The role-slot judge was not error-free: it produced role false positives and
false negatives, and candidate admission had seven false positives. Those are
real secondary failure surfaces. They do not outweigh the more basic fact that
the frozen retrieval pool itself made the coverage gate mathematically
unreachable under human labels.

Because the reviewer did not open external sources, this measures only the
supplied title-and-abstract text. One reviewer provides no inter-rater
agreement, and the 40-minute duration does not establish expert review cost.

## Decision

Role-slot consensus v6 remains failed and sealed. Y01-Y08 stay consumed,
Z01-Z08 stay unopened, and every experimental adapter remains disconnected
from `pipeline_worker.py` and the production report path.

A successor should treat candidate retrieval and semantic role judgment as
separate hypotheses. The next pre-registered development method may use Y only
as disclosed failure-analysis evidence, but must face a newly frozen unseen
cohort before any production claim. It should not spend on more consensus
passes until the candidate pool can meet a human-coverability gate.

See the
[diagnostic pre-registration](prereg-2026-09-01-openalex-role-slot-v6-failure-diagnostic.md),
[blank-packet implementation result](results-2026-09-01-openalex-role-slot-v6-failure-diagnostic-implementation.md),
and
[original bounded live result](results-2026-09-01-openalex-role-slot-consensus-v6-development-live.md).
