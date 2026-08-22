# Pre-registration: blinded user-utility audit of workflow topology

**Registered:** 2026-08-22, before packet implementation and before any utility labels
**Cost:** zero API calls; existing frozen topology-ablation reports only

## Question

Given the same frozen evidence and the same model family, does the production
six-stage workflow produce a report that proxy users find more useful for a
commercialization decision than the one-node monolith?

This is deliberately narrower than “does the product create business value?”
It does not compare against ordinary ChatGPT, an analyst team, or a report made
from fresh web research. A positive result is a small user-utility signal for
the workflow decomposition. It is not adoption, ROI, decision accuracy, or
proof that a technology should receive investment.

## Measurement before design

The completed 90-cell topology ablation contains 29 successful monolith/full
report pairs. All ten benchmark topics have both variants at repetition 1, with
identical frozen-evidence digests inside each topic. The deterministic selection
rule below therefore yields ten pairs without choosing on report quality.

The selected pairs are long: two reports together contain approximately
6,945–9,790 words. Asking one person to review all ten would create an
unrealistic 70,000+ word task and likely turn fatigue into the main treatment.
The packet therefore uses a balanced incomplete-block assignment for three to
five reviewers rather than pretending that ten report pairs require ten people.

## Frozen case selection

The source experiment is
`outputs/ablation/20260821T234300Z-7dd894ef`. For each of the ten benchmark
topics, select the lowest repetition number for which both `monolith` and
`full` have `status=success`, both report files exist, and their fixture digests
are equal. Ties are impossible because each topic/variant/repetition cell is
unique. Under the current artifacts this selects repetition 1 for every topic.

No report is selected or rejected because of contract status, word count,
citations, Reviewer changes, or a known benchmark outcome. The full report has
its deterministic `## Reviewer Notes` appendix removed because that heading
would reveal the treatment. The substantive report body is not shortened,
rewritten, or normalized. Length and structure are part of the user experience,
even though they may make perfect blinding impossible.

Every selected source path, fixture digest, source hash, blinded-side hash, and
A/B identity is stored in an answer key outside all reviewer packet directories.

## Reviewer count and assignment

The coordinator chooses `N` as 3, 4, or 5 before distributing any packet. The
tool creates two rounds at the same time:

- **Round 1 (primary):** all ten topics appear exactly once. Loads differ by at
  most one case: 4/3/3 for three reviewers, 3/3/2/2 for four, and 2 each for
  five.
- **Round 2 (optional replication):** all ten topics appear exactly once again,
  assigned so that no reviewer sees the same topic twice. It is reported
  separately until complete. If all reviewers finish both rounds, every topic
  has two independent judgments and total per-person load is 6–7, 5, or 4 pairs
  for three, four, or five reviewers respectively.

Round 2 may be omitted for workload reasons, but it must not be started or
stopped because Round 1 looks favourable or unfavourable. An unfinished round
is `incomplete`, not a smaller denominator. If fewer than three eligible people
participate, results are `pilot_only` and cannot support a resume claim.

A fixed seed controls case assignment and A/B identity. Each reviewer receives
only their own directory. The coordinator keeps the answer key private until
all forms being analysed are locked.

## Reviewer instructions and fields

Reviewers are asked to act from their actual or nearest professional role, not
to guess which report came from which architecture. For each pair they record:

1. initial `GO`, `NO_GO`, `DEFER`, or `UNCERTAIN` judgment from the topic alone;
2. the decision after reading A and after reading B;
3. pairwise preference for overall quality, decision usefulness, information
   gain, actionability, and citation trust;
4. recommendation-acceptance score for A and B from 1 to 5;
5. reading minutes and estimated revision minutes for A and B;
6. whether no, some, or all cited sources were opened;
7. factual-error observations as `NOT_CHECKED`, `0`, `1`, or `2_PLUS`;
8. confidence from 1 to 5 and a concise rationale.

Pairwise values are `A`, `B`, `TIE`, or `UNCERTAIN`. Citation trust may also be
`NOT_CHECKED`. Empty required fields mean *not evaluated*, never tie, zero
errors, or pass. `0` factual errors is invalid when no sources were opened; the
row must say `NOT_CHECKED` instead.

Each reviewer also declares role category, relevant experience, and generative
AI use. The requested procedure is no generative AI. Translation or clerical
assistance is retained but disclosed. A reviewer who used AI to generate a
substantive judgment is excluded from the primary human result; their responses
remain archived as a separate sensitivity record rather than silently deleted.

## Primary analysis and decision rule

Round 1 is the primary denominator: ten topic-level judgments, not the number of
people. It is evaluable only when all ten assignments are complete and at least
three eligible reviewers contributed. The six-stage workflow has a
**provisional utility signal** only if all of the following hold:

- the full report is preferred for `decision_usefulness` in at least 6/10 cases;
- the monolith is preferred for `decision_usefulness` in at most 2/10 cases;
- at least 8/10 decision-usefulness judgments are not `UNCERTAIN`;
- no reviewer is counted after declaring substantive AI-generated judgments.

Ties stay in the denominator. Information gain, actionability, overall
preference, decision changes, acceptance scores, reading time, revision time,
and factual-error observations are secondary descriptive outcomes. Factual
error rates are not calculated from rows marked `NOT_CHECKED` and are never
described as zero hallucinations.

If Round 2 is complete, the same outcomes are reported over its ten judgments
and over all twenty, with per-topic agreement. Round 2 cannot rescue a failed
Round 1 criterion; it is replication evidence, not a post-hoc denominator.

## Interpretation boundaries

Even a passing result remains a small proxy-user case study because:

- benchmark topics and expected technology ranges were previously known;
- both variants use frozen project evidence and DeepSeek, not ordinary ChatGPT;
- report length and style may reveal topology despite removal of explicit notes;
- preference is not an externally correct go/no-go decision;
- three to five reviewers cannot represent TTO officers, investors, and industry
  analysts as populations;
- proxy reviewers must be named as proxies, not upgraded to “experts”; and
- this study measures one reading task, not continued adoption or economic ROI.

The public result must state reviewer count, role mix, completed rounds,
AI-assistance disclosures, citation-check coverage, missing assignments, ties,
uncertainty, and disagreement. Stars, forks, and this packet are not user
adoption evidence.

## Implementation and defect-injection requirements

The implementation must remain zero-network and must:

- refuse fewer than 3 or more than 5 reviewer slots;
- reject missing, duplicate, failed, mismatched-digest, or drifting source cases;
- keep every answer key physically outside reviewer directories;
- produce deterministic assignments in which every topic appears once per
  round and no reviewer repeats a topic;
- hash every report at the source and reviewer packet boundaries;
- distinguish incomplete, pilot-only, AI-excluded, and evaluable states; and
- refuse to overwrite a packet or summary already on disk.

After tests pass, one assignment or blinded report hash will be deliberately
mutated. A boundary test must fail before the artifact is restored. Assertions
must cover the packet and aggregate output seams, not only helper return values.

The pre-registration has its own commit before packet code, assignments, or
human utility labels exist.
