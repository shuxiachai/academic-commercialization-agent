# Result — agent-topology ablation on current main with qwen3.8-flash

Protocol: [prereg-2026-10-23-agent-topology-ablation-qwen.md](prereg-2026-10-23-agent-topology-ablation-qwen.md),
a repeat of the [August study](prereg-2026-08-21-agent-topology-ablation.md)
with the same frozen evidence, arms, outcomes, predictions and decision rules.

**Summary.** On today's code with `qwen3.8-flash`, the four-node arm's cost
advantage over six nodes replicated and grew. Paired medians: 60.05% fewer
tokens, 54.41% lower cost and 48.67% less time; P3 is supported.

The four-node arm's quality advantage over the monolith did not replicate. The
monolith had the fewest citation-contract findings (41, against 169 for four
nodes and 118 for six). It matched the four-node arm on the numeric screen and
on first-attempt validation, at 44% of the four-node median cost. P4 is
falsified, and P1 is falsified again.

The six-node arm completed 23 of 30 runs. Its reviewer failed its own output
contract on the first attempt in 27 of 30 runs, and on both attempts in 7.

Model, provider, prompts and the outcome screens all changed since August, so
none of these differences is attributed to topology alone. Two of the screens
also drifted in ways that bear on P2 and P4; the
[measurement caveats](#measurement-caveats-found-after-the-results) quantify
both.

## Execution

**Pilot.** Fixture case 03 ran once through all three arms as experiment
`outputs/ablation/20261023T110900Z-737ef33c`:
- 3/3 completed;
- 132,437 tokens;
- $0.022059 recorded.

No stop rule fired:
- every arm used the frozen fixture (digest `8643e7369b337b9b`);
- every final report persisted;
- every agent was a priced `qwen3.8-flash`, so the complete-cost flag was true;
- grounding checked 3, 3 and 2 lines, recorded as `fail` rather than as a
  vacuous pass;
- fixture digest, model usage and guardrail attempts were recorded in every
  cell.

**Full study.** Experiment ID: `outputs/ablation/20261023T111632Z-737ef33c`.
- **Code.** All 90 cells ran at commit `737ef33`. That is `faccb61` plus the
  registered kickoff fix, and its tree is identical to that of `db8f3bb`, the
  merge commit that put it on `main`.
- **Time.** From 2026-10-23 11:16:32Z to 14:37:13Z: 3.345 wall-clock hours,
  with no interruption or resume.
- **Integrity.** These checks passed:
  - all 90 cells used fixture evidence;
  - all ten digests equal the registered ones;
  - one commit and one experiment ID throughout;
  - every one of the 330 agent-usage records is a priced `qwen3.8-flash`, and
    cost is complete in every cell;
  - each arm held each Latin-square position exactly ten times;
  - every successful cell persisted its final report.

**Spend.** Persisted spend was $0.640163 in recorded list-price USD:
- $0.077351 for the monolith;
- $0.178429 for the four-node arm;
- $0.384383 for the full arm.

With the pilot, that is $0.662222, under the approved $2.00 soft ceiling. The
full study used 3,731,815 tokens (2,992,015 prompt, 739,800 completion) in 355
requests.

The recorded figure is the built-in upper-bound price and does not reflect
Model Studio's free quota. At the Beijing list price (¥0.8/¥2.7 per Mtok), with
the first million tokens free, the actual charge would be about ¥3.4. That is
an estimate; the provider bill is authoritative.

**Failures.** Seven full-arm cells failed, all at the reviewer guardrail after
its single retry:
- five because a correction's `reason` exceeded the 300-character schema bound;
- two because a `find` target occurred two or three times in the draft.

They are retained as outcomes and were not rerun.

## Common outcomes

As in August:
- **Finding-free** means the offline report-contract screen returned no
  finding. It is not expert-verified correctness.
- **Grounding** counts are the numeric screen only.
- **Denominators** include successful cells only, so the full arm has 23
  reports.

| Arm | Completed | Finding-free | Contract findings | Grounding checked lines / unsupported lines / not-checked runs | Median tokens | Median cost | Median elapsed |
|---|---:|---:|---:|---:|---:|---:|---:|
| Monolith | 30/30 | 10/30 | 41 | 28 / 22 / 15 | 13,321.5 | $0.002553 | 64.788 s |
| Specialists + writer | 30/30 | 0/30 | 169 | 41 / 23 / 16 | 32,472 | $0.005868 | 93.383 s |
| Full | 23/30 | 0/23 | 118 | 23 / 13 / 14 | 83,929 | $0.013457 | 197.798 s |

**What the findings are.** Almost all are the non-blocking citation-policy
heuristic, that is, uncited substantive or numeric claims: 39, 166 and 115.
The rest are:
- 3 and 2 patent-framing findings in the four- and six-node arms;
- three unsupported use-case claims, two from the monolith and one from six
  nodes, all on case 03: fleet, truck or bus applications that the cited
  summaries do not mention.

Successful reports had no missing headings, unknown source IDs or missing
evidence domains, and every one cited all three domains.

**Paired comparisons.**
- Four nodes against the monolith, contract findings: four nodes had fewer in 1
  block, the monolith in 27, with 2 ties.
- The same pair, unsupported numeric lines: four nodes had fewer in 5 blocks,
  the monolith in 4, with 21 ties.

**Latency.** Tails were tighter than in August. P95/max elapsed time:

| Arm | P95 | Max |
|---|---:|---:|
| Monolith | 91.031 s | 101.486 s |
| Four nodes | 119.027 s | 119.902 s |
| Successful full runs | 258.130 s | 279.573 s |

**Report size.** Median words were 2,629, 2,730 and 2,935. Median unique
citations were 20.5, 20 and 19.

## Registered predictions

- **P1 falsified.** No arm's report guardrail failed a first attempt: zero for
  the monolith, zero for four nodes, and all 30 paired blocks tied. The
  four-node writer therefore did not have fewer first-attempt failures. In
  August, P1 was also falsified, at five failures against one.
- **P2 supported, within the screen's scope and with a qualification.**
  - Successful full reports had 13 unsupported checked numeric lines, against
    23 for four nodes. On the 23 blocks where both reports exist, the counts
    are 13 against 18.
  - Full was better in 5 pairs, worse in 2, and tied in 16.
  - The registered screen counts figures in unrecognised notation as
    unsupported; see the caveats. Under production's rule the counts are 3
    against 5, so the direction holds. Very few lines are checkable at all.
- **P3 supported.**
  - Comparing arm medians, four nodes used 61.31% fewer tokens and cost 56.40%
    less than six.
  - Paired median reductions were 60.05% for tokens (IQR 57.89%–62.18%),
    54.41% for cost (52.36%–59.33%) and 48.67% for elapsed time
    (41.12%–58.04%). All are well above the 20% threshold.
- **P4 falsified.**
  - The monolith was cheapest: four nodes cost 2.30 times its median.
  - It lost no common quality or reliability outcome to the four-node arm:
    - completion tied at 30/30;
    - first-attempt validation tied at zero;
    - it had far fewer contract findings (41 against 169; better in 27 of 30
      pairs);
    - on the numeric screen it was level (22 against 23 unsupported lines;
      4 against 5 better blocks).
  - Excluding the decision-contract lines discussed below does not reverse
    this: 39 against 75 uncited findings.

## Decision and falsification rules

- **Any increase in high-confidence unsupported numeric claims.** The four-node
  arm had one more unsupported line than the monolith on the registered screen
  (23 against 22). Under production's rule it had 5 against 2. By the
  registered rule that is a regression for four nodes against the monolith,
  although the counts are too small to carry weight on their own.
- **Four nodes improving first-attempt validation or grounding over the
  monolith.** They did not. Domain decomposition is **not supported** in this
  study.
- **The monolith matching both staged arms on all common outcomes while using
  at least 20% fewer tokens or dollars.**
  - Against four nodes, the monolith matched or beat it on every common
    outcome.
  - Against six nodes it completed more runs (30 against 23), had fewer
    contract findings (better in 21 of 23 pairs), and tied first attempts.
  - On the registered numeric screen, however, six nodes had fewer unsupported
    lines: 13 in 23 reports against 22 in 30, and better in 7 of 23 pairs,
    worse in 2.
  - So on registered numbers the condition is not fully met, and the claim
    that specialist decomposition is necessary is **not formally falsified**.
    Under production's unknown-unit rule the monolith matches (2 against 3
    unsupported lines). The verdict on this rule therefore rests on a screen
    whose drift is documented below.
- **Six nodes matching four on common outcomes while costing at least 20%
  more.** The six-node arm did not match:
  - it completed fewer runs (23/30 against 30/30);
  - contract findings were mixed (9 pairs each way, 5 ties);
  - its numeric lines were slightly better;
  - its median cost was 129% higher.

  Nothing here establishes that six nodes are necessary for report generation.
- **Reviewer corrections.** The reviewer made 241 accepted corrections. That is
  activity, not evidence that six nodes are better.

## Reviewer diagnostics

**Edits.** The reviewer accepted 241 corrections, in every one of the 23
successful full runs. Median draft retention was 99.1652%, with a 97.3644%
minimum, so it edits far more than in August. No edit has been judged for
correctness.

**Guardrail.** The reviewer guardrail ran 57 times, and its first attempt
failed in 27 of 30 runs. The causes:

| Cause | First attempt | Both attempts (terminal) |
|---|---:|---:|
| A `reason` longer than the 300-character schema bound | 21 | 5 |
| More than the 20 corrections the prompt allows | 5 | 0 |
| A `find` target occurring more than once | 1 | 2 |

The reviewer prompt states the 20-correction limit and the 2,000-character
`find`/`replace` limit. It never states the 300-character `reason` bound, which
lives only in the schema (`evidence.py`). The 2026-10-01
[Reviewer v2 closeout](results-2026-10-01-reviewer-comparison-v2.md) met the
same bound. Other full-arm guardrail retries were 4 for the scorer and 1 for
the market analyst. The monolith and four-node arms needed no retry on any
task.

**Production differs here.** The ablation runs each crew without production's
reviewer fallback. In production, a reviewer that fails after its retry
delivers the validated Task 4 draft unchanged and still runs the scorer. The
seven terminal failures therefore measure the raw six-node topology. They are
not production delivery failures, but in production they would be paid
reviews that changed nothing.

## Measurement caveats found after the results

Both readings below were added after the results were seen, to explain them.
They are exploratory, not registered. They do not replace a registered number
or enter `article_figures.json`. `scripts/ablation_outcomes.py --exploratory`
reproduces them.

**1. Decision-output contract lines.** After August, the production writer
template gained a "Decision-output contract". The fifth section must now state:
- the assessment mode;
- one primary route;
- the decision owner, or "not established";
- cost and time, or "not established";
- the GO/NO_GO applicability.

Such a line states a mode or an absence, so there is no source to cite. The
non-blocking uncited-claim screen flags it. The four- and six-node arms reuse
the production template; the monolith keeps its frozen August prompt, which
has no such section.

A flagged line counts as a contract line here if it contains "assessment mode",
"commercialization route", "decision owner", "cost and time", "GO/NO_GO" or
"applicability". By that rule:

| | Monolith | Four nodes | Six nodes |
|---|---:|---:|---:|
| Uncited findings | 39 | 166 | 115 |
| On contract lines | 0 | 91 | 66 |
| On other lines | 39 | 75 | 49 |

None of August's flagged lines matches the rule: the contract did not exist
then. The contract-finding comparison between
the monolith and the staged arms is therefore confounded by template drift. The
monolith still has the fewest findings on other lines.

**2. Numeric-screen drift.** `ablation_check.analyse_numeric_grounding` calls
`claim_grounding._supported` directly. Since 2026-09-11 (`457984f`),
`claim_grounding` marks a figure in unrecognised numeric or unit notation with
`?unknown:`. Production's own check then treats that line as unverifiable:
"Unknown units cannot earn a pass or a false accusation." For such a figure
`_supported` returns false, so the August harness now counts it as
**unsupported**. Of the unsupported figures, these carried the marker:

| Monolith | Four nodes | Six nodes |
|---:|---:|---:|
| 25 of 30 | 21 of 27 | 14 of 18 |

August's figures never did: the marker did not exist yet.

The recount below applies production's rule to the same reports and sources.
Its implementation first reproduced the registered counts exactly for all 83
successful cells with the rule off. The registered counts are those in the
outcome table above.

| Arm | Checked lines | Unsupported lines | Not-checked runs |
|---|---:|---:|---:|
| Monolith | 8 | 2 | 23 of 30 |
| Four nodes | 23 | 5 | 18 of 30 |
| Six nodes | 13 | 3 | 15 of 23 |

Under either reading, few lines in these reports are checkable, so the numeric
screen carries little information in this study. The harness was not changed
after the results. Before it measures another experiment, it should apply the
same unknown-notation rule as production, with a test.

## Side by side with August

| | August, DeepSeek, `7dd894ef`: mono / four / full | October, qwen3.8-flash, `737ef33`: mono / four / full |
|---|---|---|
| Completed | 30 / 30 / 29 | 30 / 30 / 23 |
| Finding-free | 9 / 19 / 11 | 10 / 0 / 0 |
| Contract findings | 119 / 24 / 39 | 41 / 169 / 118 |
| Uncited findings | 115 / 24 / 38 | 39 / 166 / 115 |
| Grounding checked / unsupported / not-checked | 134/29/2 · 89/5/8 · 67/2/10 | 28/22/15 · 41/23/16 · 23/13/14 |
| Median tokens | 14,364 / 35,884.5 / 79,559 | 13,321.5 / 32,472 / 83,929 |
| Median elapsed | 45.264 / 62.279 / 94.153 s | 64.788 / 93.383 / 197.798 s |
| P95 / max elapsed (s) | 70.5/84.7 · 156.4/350.4 · 145.3/473.3 | 91.0/101.5 · 119.0/119.9 · 258.1/279.6 |
| First-attempt report-guardrail failures | 1 / 5 / 2 | 0 / 0 / 0 |
| Four vs six, paired median reduction | tokens 57.16%, cost 47.01%, time 37.71% | tokens 60.05%, cost 54.41%, time 48.67% |
| Reviewer: corrections (runs) · retention median / min | 34 (9 of 29) · 99.9983% / 99.3310% | 241 (23 of 23) · 99.1652% / 97.3644% |
| Reviewer first-attempt failures · terminal | 8 (invalid JSON) · 1 | 27 (mostly `reason` > 300) · 7 |
| P1 / P2 / P3 / P4 | falsified / supported / supported / supported | falsified / supported (qualified) / supported / falsified |

Spend is not compared:
- the price bases differ;
- August's DeepSeek rows were charged for cache hits;
- the free quota is not reflected in October's recorded cost.

Median spend per run fell, but so did the model's list price.

## Limits

- **Attribution.** Model, provider, 669 commits of code, the writer template
  and both outcome screens changed between the two studies. No difference
  from August is attributed to topology alone.
- **Model.** `qwen3.8-flash` is a small model, chosen for its free quota. It is
  not the production model: production reported `qwen3.7-max-preview` on
  2026-10-23. These results do not describe production's model on any date.
- **Arm asymmetry.** The staged arms run today's production prompts; the
  monolith runs its frozen August prompt. The decision-output contract exists
  only on the staged side.
- **Runs.** All runs are orientation runs, with no decision context, as in
  August.
- **Reviewer fallback.** The six-node arm has no production fallback, so its
  completion rate is the raw topology's.
- **Sample size.** Ten topics and three repetitions: effect sizes, not
  significance tests.
- **Scope.** Neither screen measures qualitative correctness. No reviewer edit
  was judged, and nothing here measures user value.

## Deviations from the protocol

- **Command form.** The registered commands were run through a wrapper. It
  loads the main checkout's `.env` without overriding set variables and
  prints no key. For the full study it also asks Windows not to idle-sleep
  until the process exits. The arguments were the registered ones,
  `--full --execute --confirm-full-study --stop-after-usd 2.00`.
- **Commit identity.** The study ran at the protocol's commit `737ef33`, not at
  main's merge commit `db8f3bb`; the two have the same tree.
- **Timing.** The pilot started before PR #293 finished CI. The protocol was
  already on the remote, as the protocol requires.
- **Added analyses.** The two exploratory readings above, labelled as such.

## Data and reproduction

The experiment directories are local, like August's, and are not committed:
- `outputs/ablation/20261023T110900Z-737ef33c`, the pilot;
- `outputs/ablation/20261023T111632Z-737ef33c`, the full study;
- `outputs/ablation/20261023T111632Z-737ef33c/article_figures.json`, the
  pre-registered article figures, from successful cells only.

```bash
uv run python ablation_check.py outputs/ablation/20261023T111632Z-737ef33c
uv run python scripts/ablation_outcomes.py outputs/ablation/20261023T111632Z-737ef33c --exploratory
```

`scripts/ablation_outcomes.py` reproduces every figure of August's "Stage 2
full-study outcome" section from August's directory, which is how its
definitions were checked before any October result was computed. After the
results, three things were added to the script:
- the paired comparisons between the monolith and six nodes;
- P2's common-block totals;
- the two exploratory readings.

Its registered computations are unchanged, and it still reproduces August's
figures.
