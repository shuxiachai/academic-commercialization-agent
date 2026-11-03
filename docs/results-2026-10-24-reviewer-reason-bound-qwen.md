# Result — stating the reviewer's reason bound, six-node rerun on qwen3.8-flash

Protocol: [prereg-2026-10-24-reviewer-reason-bound-qwen.md](prereg-2026-10-24-reviewer-reason-bound-qwen.md).

**Summary.** The reviewer prompt now states the 300-character `reason` bound
its schema enforces. On the same 30 six-node blocks, same model and same
fixtures:
- First reviewer attempts that broke the bound fell from 21 to 3.
- Terminal reviewer failures fell from 7 to 2.
- Completed runs rose from 23 to 28.

All four registered predictions hold, and by the registered rule the change
is adopted. The reviewer also made fewer edits per plan: a median of 5.5
against 9, just above the RB4 floor of 5. Whether its remaining edits are
right was not judged.

## Execution

**Pilot.** Experiment `outputs/ablation/20261023T151302Z-aafb8760`: one cell on
case 03, at `aafb876`. It succeeded in 174.153 s, with 79,629 tokens and
$0.012590 recorded.

None of the five stop rules fired:
- fixture evidence with the registered digest;
- the final report persisted;
- every agent a priced `qwen3.8-flash`, so the complete-cost flag was true;
- grounding checked 2 lines rather than passing vacuously;
- every guardrail recorded.

**Rerun.** Experiment `outputs/ablation/20261023T151630Z-aafb8760`.
- **Code and time.** 30 cells at `aafb876`, from 2026-10-23 15:16:30Z to
  16:49:50Z, 1.556 hours, with no interruption.
- **Integrity.** These checks passed:
  - only the six-node arm ran;
  - every cell used fixture evidence, and all ten digests equal the
    registered ones;
  - the blocks are exactly the baseline's 30;
  - one commit and one experiment ID throughout;
  - all 180 agent-usage records are a priced `qwen3.8-flash`, and cost is
    complete in every cell;
  - every successful cell persisted its final report.
- **Spend.** $0.363228 recorded against the $1.00 ceiling. The baseline arm
  recorded $0.384383 for the same blocks. The rerun used 2,291,259 tokens
  (1,951,715 prompt, 339,544 completion) in 189 requests.

The first pilot attempt was refused by the runner's argument guard before any
request; the protocol's amendment records it. No other deviation.

## Outcomes

| | Baseline (`737ef33`) | Rerun (`aafb876`) |
|---|---:|---:|
| First reviewer attempt failed | 27 / 30 | 6 / 30 |
| — `reason` over 300 characters (primary) | 21 | **3** |
| — more than 20 corrections | 5 | 3 |
| — `find` not unique | 1 | 0 |
| Terminal reviewer failures | 7 / 30 (5 reason, 2 find) | **2 / 30** (2 reason) |
| Completed runs | 23 / 30 | 28 / 30 |
| Runs accepting a correction | 23 / 23 | 28 / 28 |
| Accepted corrections; median / max per plan | 241; 9 / 20 | 194; 5.5 / 20 |
| Accepted `reason` length, median / p90 / max | 147 / 206 / 292 | 152 / 203 / 257 |
| Draft retention, median / min | 99.1652% / 97.3644% | 99.5532% / 98.3596% |
| Median tokens / cost / elapsed | 83,929 / $0.013457 / 197.798 s | 75,174.5 / $0.011516 / 163.095 s |
| P95 / max elapsed | 258.130 / 279.573 s | 226.278 / 305.882 s |
| Other guardrail retries | scorer 4, market 1 | scorer 5 |

**Paired by block**, the same topic and repetition, before and after:

| | Failed before only | Failed after only | Both | Neither |
|---|---:|---:|---:|---:|
| First attempt failed on `reason` | 18 | 0 | 3 | 9 |
| First attempt failed, any cause | 21 | 0 | 6 | 3 |
| Terminal failure | 7 | 2 | 0 | 21 |

**The two remaining terminal failures** are in blocks that passed before:
- **04-r3:** too many corrections, then one long `reason` on the retry.
- **09-r1:** the same correction's `reason` was too long twice.

Each failed attempt now carries one long reason. Before, failed first
attempts carried one to eleven. The writer's report guardrail never needed a
retry in either experiment.

## Registered predictions

- **RB1 holds.** 3 of 30 first attempts failed on `reason`, against the
  registered maximum of 5 and a baseline of 21. No block that passed before
  began failing on it.
- **RB2 holds.** 2 of 30 runs failed terminally, against a maximum of 3 and a
  baseline of 7. Both failures are in blocks that had passed before; fewer
  terminal failures is a count, not a guarantee for any block.
- **RB3 holds.** First-attempt failures from other causes were 3, against a
  ceiling of 9 and a baseline of 6. Failures did not move to another cause.
- **RB4 holds.** All 28 successful runs accepted a correction, against a
  floor of 18. The median plan held 5.5 corrections, against a floor of 5,
  down from 9.

## Decision

The adoption rule is met: RB1 holds, and neither RB3 nor RB4 is violated. The
prompt change is adopted by merging it. Under RB2, fewer terminal failures can
be claimed for this model: 2 against 7.

## What this does and does not show

- **Shown.** On `qwen3.8-flash`, telling the reviewer the bound removes most
  breaches of it. Over-long reasons still occur in a few plans, and twice the
  single retry did not recover.
- **The drop in corrections** (median 9 to 5.5, retention up) has three
  possible causes:
  - the reviewer became more conservative;
  - the long reasons had come with long plans;
  - variance between days.

  This study cannot tell them apart. Fewer edits are not shown to be better
  or worse.
- **Model.** Production runs `qwen3.7-max-preview` and other models; the
  change is unmeasured on them.
- **Limits.**
  - One model, 30 blocks, different days. A modest effect could not be
    separated from provider variance, but this one is large: 18 blocks fixed
    against 0 newly failing on the primary outcome.
  - The report-contract and numeric screens were recorded but are not
    outcomes, because both drifted (see the topology result).
  - Clipping over-long reasons in code, and the more-than-20 and non-unique
    `find` failures, remain out of scope.

## Data and reproduction

The experiment directories are local, like the baseline's:
- `outputs/ablation/20261023T151302Z-aafb8760`, the pilot;
- `outputs/ablation/20261023T151630Z-aafb8760`, the rerun;
- `outputs/ablation/20261023T111632Z-737ef33c`, the baseline.

```bash
uv run python ablation_check.py outputs/ablation/20261023T151630Z-aafb8760
uv run python scripts/reviewer_contract_audit.py outputs/ablation/20261023T151630Z-aafb8760 \
  --baseline outputs/ablation/20261023T111632Z-737ef33c
uv run python scripts/ablation_outcomes.py outputs/ablation/20261023T151630Z-aafb8760
```

`--baseline` pairing was added to the audit script after the rerun had
started and before its results were read. It does not change any registered
threshold or outcome definition.
