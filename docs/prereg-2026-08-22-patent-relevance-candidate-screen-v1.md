# Pre-registration: patent topic-slot review screen v1

**Frozen:** 2026-08-22, before implementing or calculating candidate outputs.

## Status and purpose

This is a **post-hoc development experiment**, not a held-out validation. The
81 human labels and their aggregate failure patterns were already visible when
this rule was designed. The experiment asks a narrower engineering question:
can one fixed, zero-network and topic-generic screen turn the known failure
patterns into a reproducible `KEEP / REVIEW / DROP` decision without silently
discarding a human-labelled relevant patent?

Passing this experiment does not authorize a production filter. It only
qualifies the frozen candidate for a later, genuinely unseen challenge set.

## Frozen evidence and baseline

- Cases: the exact 81 case IDs and case-card hashes in
  `evals/patent_relevance/human-review-2026-08-22/manifest.json`.
- Labels: the exact complete label set in the same directory.
- Benchmark core: 75 cases; sodium-ion diagnostic challenge: 6 cases.
- Existing baseline accepts all 81 cases. Combined direct relevance is 69/81
  (85.2%); benchmark-core direct relevance is 64/75 (85.3%).
- The sodium-ion challenge remains post-hoc and must be reported separately.

The evaluator must refuse missing, extra, duplicated, partial, or hash-drifted
cases. Silence is not a pass: incomplete inputs produce no headline metrics.

## Candidate v1: two topic slots

The candidate receives only the research topic, patent title, and frozen
evidence summary. It must not read the human label or rationale when producing
the decision.

1. Split a topic at the first literal ` for `.
2. The phrase before the split is the **technology slot**. For a topic without
   ` for `, the complete topic is the technology slot.
3. The final meaningful token in the technology slot is the technology anchor.
4. The phrase after ` for ` is the **application slot**. Every meaningful token
   in that phrase is required within one bounded support window. Topics without
   an application slot skip this test.
5. Matching is case-insensitive, hyphen-insensitive, singular/plural tolerant,
   and permits a common six-character prefix for longer morphological variants.
6. Meaningless routing words are limited to a frozen stop-word set in code;
   the rule contains no topic-name, patent-ID, assignee, URL, or human-label
   exception.

The actions are frozen as follows:

- `DROP`: the technology anchor has no support anywhere in title plus summary.
- `REVIEW`: the technology anchor is supported, but the complete application
  slot has no bounded support; or application support is absent from the title
  and at least one supporting evidence window contains a frozen broad-list or
  background marker.
- `KEEP`: neither condition above applies.

The frozen weak-context markers are:

- `variety of applications`
- `applications such as`
- `applications include`
- `applied to a variety`
- `merely by way of example`
- `including but not limited`
- `any other complex`
- `description of related techniques`
- `background`
- `has included`
- `other sources`

The support window is 180 characters on each side of an anchor occurrence.
Application support requires all application-slot tokens in the same window.
These constants may not be changed after candidate metrics are calculated.

## Metrics

The committed result must include, overall and by corpus:

- action counts;
- human-label counts within each action;
- direct and usable precision among `KEEP` cases;
- human `RELEVANT` counts sent to `REVIEW` and `DROP`;
- `WEAK` and `IRRELEVANT` capture into `REVIEW` or `DROP`;
- manual-review load (`REVIEW / all cases`);
- every decision, reason, anchor, and evidence feature by case ID.

The six-case sodium-ion challenge is diagnostic and cannot be merged into a
claim about benchmark generalization.

## Pre-registered gates

The candidate qualifies only for a new held-out challenge if **all** gates pass:

1. `RELEVANT` sent to `DROP` equals zero.
2. Both `IRRELEVANT` cases leave `KEEP`.
3. At least 6/10 `WEAK` cases leave `KEEP`.
4. Combined `KEEP` direct precision improves over 85.2% by at least 2 percentage
   points.
5. Manual-review load is at most 25% (20/81 cases).
6. All 81 case IDs and content hashes match the frozen manifest.

Failure is a result. No gate may be relaxed, no case-specific exception may be
added, and no production behavior may change to make the candidate pass.

## Defect reinjection and verification

Tests must prove the evaluator catches a decision or summary that fails to
reach the committed result boundary. After the implementation passes, one
committed decision or aggregate count will be deliberately mutated; the new
seam test must fail before the artifact is restored.

The implementation and final result will be added below only after this frozen
document has its own Git commit.
## Result — added after the frozen run

The pre-registration was committed as `b011f86`; the label-blind candidate and
its synthetic contracts were then committed as `aeb3d18`. Only after both
commits existed was the complete 81-case evaluation run.

The candidate failed two gates:

- `KEEP` direct precision increased from 85.2% to 35/37 (94.6%), a 9.4-point
  improvement, but six human-labelled relevant patents were sent to `DROP`;
- 36/81 cases (44.4%) were sent to `REVIEW`, above the 20/81 ceiling.

It passed the remaining gates: both irrelevant cases and 8/10 weak cases left
`KEEP`, and all 81 case hashes matched. The benchmark core and sodium challenge
remain separate in `result.json`; the diagnostic challenge itself had one
relevant and one weak patent sent to `DROP`.

The six relevant auto-drops demonstrate that a final technology token is not a
safe ontology: valid cases used treatment/manufacturing instead of therapy,
sequestration instead of storage, altering expression instead of editing, a
specific flexible solar-cell form instead of electronics, and energy-storage
material instead of battery. The review rule also routed 28 relevant patents to
manual work. Two weak quantum patents still remained in `KEEP`, showing that a
search snippet can phrase an illustrative application as if it were focused
support.

No threshold or marker was changed after measurement. The candidate is rejected
for held-out qualification and production use. Full artifacts are in
[`evals/patent_relevance/candidate-screen-v1-2026-08-22/`](../evals/patent_relevance/candidate-screen-v1-2026-08-22/).
