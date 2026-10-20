# Protocol amendment — held-out TRL v1: measure `qwen3.7-plus` in batch `heldout-trl-v1-c`

Registered **2026-10-18**, before batch `heldout-trl-v1-c` starts. It amends
the [held-out TRL v1 protocol](prereg-2026-10-18-heldout-trl-v1.md). The cohort, the expected
ranges, the primary measure, the thresholds, the rules and the stop rules are
**unchanged**. Only the model, its price basis and the batch change.

## Why

Batch `heldout-trl-v1-b` (at `56d3ced`, `qwen3.5-plus`) stopped under the
registered stop rule on a provider **account** error. Alibaba Cloud returned
`Arrearage` ("Access denied, please make sure your account is in good
standing") at H07 rep 1. Every Qwen model on the key was refused while the
account was in arrears. After the account was restored, the maintainer chose
to continue on **`qwen3.7-plus`**.

## What this changes in the measurement

- **The model under test is `qwen3.7-plus`, not production's
  `qwen3.5-plus`.** Results describe this system with `qwen3.7-plus`. They
  are not a measurement of the deployed configuration unless production
  switches model. That is a separate decision outside this protocol.
- The model is part of the batch identity, so batch `heldout-trl-v1-b`
  cannot be resumed under it. **All 30 runs are made in a new batch,
  `heldout-trl-v1-c`**, and no unit from batch b is combined with batch c.
- A preflight with the project's own request parameters (JSON Object
  output, `enable_thinking: false`) succeeded on `qwen3.7-plus`.

## Price basis for the USD 5 stop rule

`token_usage` has no built-in price for `qwen3.7-plus`, so the batch sets
`LLM_PRICE_PER_MTOK=0.85:3.40`, in USD per million input and output tokens,
with cached input at the input rate. That is the highest published tier found,
China long-context ¥6 / ¥24 per million tokens, converted at about ¥7.1 per
USD. Following the project's convention for soft stops, this can only
**overstate** recorded cost. Requests in this batch stay far below the
long-context tier. Third-party listings give $0.32–0.40 input and
$1.28–1.60 output, and the official pricing page could not be retrieved.
Recorded cost is therefore an upper-bound estimate, not an invoice.
Helper-call accounting does not recognise the model name and records those
calls as unknown-model rather than failing.

## Record of batch `heldout-trl-v1-b` (closed)

| Unit | Outcome |
|---|---|
| H01, H02, H03, H04, H06 rep 1 | success (5) |
| H05 rep 1 | killed mid-run by a **false-positive monitor stop** |
| H07 rep 1 | `error_crew`: provider `Arrearage` |
| remaining 23 | never started |

- **The false positive.** The external stop-rule monitor scanned the whole run log and matched "unauthorized" in a Reviewer correction reason ("constitutes an unauthorized legal opinion"). That is report text, not a provider error. The monitor now scans only failure records (`meta.json` errors and `error.log`).
- **The resume.** The batch was resumed under the unchanged identity. In serial mode, `benchmark.run_topic` raises on an occupied unit and nothing catches it, so a shim outside the repository applied the concurrent path's existing rule: the unit is recorded as failed and not retried. `benchmark.py` bytes were unchanged.
- **The stop.** The batch then ran until the account error, which is a genuine stop condition.
- **What was looked at.** Recorded Crew-node cost for batch b was USD 0.43 at the qwen3.5-plus table price. No TRL, score or report from batch b was looked at; the monitor reported only success counts. Batch b is kept as recorded and is not analysed against the thresholds.

## Held-out status

Batch b produced five TRLs that no one has looked at. No prompt, rubric,
retrieval or scoring change has been made since the protocol, so the topics
are still treated as held out for batch c. As with the earlier erratum, this
reading is stated rather than assumed.

## Registered command for batch c

```bash
LLM_PROVIDER=qwen QWEN_MODEL=qwen3.7-plus \
QWEN_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1 \
LLM_PRICE_PER_MTOK=0.85:3.40 \
uv run python benchmark.py --cohort evals/heldout_trl_v1/cohort.json \
    --repeat 3 -c 1 --experiment-id heldout-trl-v1-c
```

Preflight, monitoring and stop rules are as registered, with the monitor
scanning failure records only. Cost uses the price basis above.
