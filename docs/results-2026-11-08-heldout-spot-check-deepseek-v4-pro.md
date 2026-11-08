# Result — held-out spot check on deepseek-v4-pro

Run **2026-11-08** under the protocol registered the same day
([prereg](prereg-2026-11-08-heldout-spot-check-deepseek-v4-pro.md)). Five
topics from the frozen v2 cohort, one live run each, on `main` at `14a2097`,
with `deepseek-v4-pro` through the `qwen` transport on the maintainer's free
quota. Batch `heldout-spot-2026-11-08-deepseek-v4-pro`; raw outputs are
private and stay on the maintainer's machine. Nothing was re-scored.

## Headline

- **Completion 5/5.** Every unit reached a scored report.
- **TRL in range 5/5**, against ranges frozen on 2026-10-19: V01 8.0 (8–9),
  V03 7.3 (7–8), V06 5.0 (3–5, at the ceiling), V07 5.0 (4–6), V09 9.0 (8–9).
- **423,040 crew tokens**, 77,022–95,060 a run, mean 84,608, against v2's
  mean of 91,745 on `qwen3.8-max`. Serial wall time 53.7 minutes.

Five runs, one each: this is a reading, not a calibration measure, and it
claims nothing about production (bring-your-own-key) or about any one cause.

## Per unit

| Case | Topic | Expected | TRL | Score | Sources A/P/M | Tokens | Time | Retries |
|---|---|---|---|---|---|---|---|---|
| V01 | robotic-assisted surgery | 8–9 | 8.0 | 70.3 | 8/8/7 | 80,812 | 972 s | planner timeout before send, retried |
| V03 | enhanced geothermal systems for electricity generation | 7–8 | 7.3 | 69.3 | 5/8/8 | 77,022 | 430 s | none |
| V06 | space-based solar power | 3–5 | 5.0 | 49.6 | 8/8/7 | 82,166 | 327 s | none |
| V07 | hyperloop (one word) | 4–6 | 5.0 | 47.1 | 8/5/7 | 87,980 | 369 s | one connection timeout, retried after 2.2 s; scorer guardrail once (`market_source_ids` named an academic source), second attempt passed |
| V09 | 特高压直流输电 (Chinese) | 8–9 | 9.0 | 74.9 | 8/8/8 | 95,060 | 1,061 s | writer guardrail once (malformed citation block `[P4的启发性空白]`), second attempt passed |

Each run was six crew requests, seven where a node was retried. The runner
counted 2 rate-limit hits per run (10 in the batch) and advised staying
serial, which the batch was. The uncited-claim screen reported 0 in all five
reports and every report passed the section check.

## Readings fixed in the protocol

- **Completion**: 5 of 5. No failure, so no error record to read. Two
  guardrail retries were on model-contract fields (a source-domain mix-up in
  the scorer, a citation block the writer malformed on the Chinese topic);
  both were corrected on the second attempt by the existing retry, and
  neither reached the report.
- **TRL against the frozen range**: in range 5, above ceiling 0, below floor 0.
  V06 sits exactly at its ceiling of 5; v2 had missed space-based solar power
  below floor, and the present run is in range on eight academic sources
  rather than the thin set v2 reported.
- **Tokens and time**: mean 84,608 a run (v2: 91,745), range 77,022–95,060;
  the two long runs (V01, V09) spent their time in retries and in the longer
  Chinese writer turn (9,905 completion tokens over two attempts), not in
  more requests. The recorded cost is `None`: the model is not in the price
  table, so no USD figure is claimed. The batch used 423,040 of the
  1,000,000-token free allowance.
- **Retrieval shape**: academic sources at the cap (8) in four runs and 5 in
  V03; patents 5–8; market 7–8. V07's plan kept the user's word: 12 of its
  queries contain "hyperloop" and the delivered sources mention it 166 times,
  so the v2 failure that #248 corrected did not recur.

## Other observations, not registered

- The claim-grounding screen checked 0 claims in four of the five runs and 2
  in V09, with nothing ungrounded; the market claims it saw were marked
  unverifiable (4 in V01, 1 in V07, 2 in V09). "0 unsupported of 0 checked"
  is not a pass; it is the screen saying it had nothing it could check.
- Asked its own name in the probe before the batch, the model answered
  "Claude". Nothing in the pipeline depends on a model's self-report; noted
  because a reader of the raw outputs may meet the same thing.
- The first topic's planner call timed out once before the request was sent
  and was retried after one second, the path #280 made patient; the batch did
  not need the `--stagger` the runner suggests.

## What this does and does not say

- The pipeline completes end to end from the CLI on the current `main`, with
  live retrieval, on a model it had never run, and lands every one of five
  held-out topics inside its frozen range, including the one-word and the
  Chinese inputs.
- It does not measure calibration (five runs), it does not exercise the web
  client, accounts, caps or email, and it cannot attribute anything: the
  model, the live evidence of the day and the anonymous OpenAlex pool all
  differ from v2 at once.
- A larger batch on this model, if wanted, has this as its first reading;
  the quota left after this run allows about six more.
