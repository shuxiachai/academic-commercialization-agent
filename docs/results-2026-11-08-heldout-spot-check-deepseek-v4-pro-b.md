# Result — held-out spot check on deepseek-v4-pro, part B

Run **2026-11-08** under the part B protocol
([prereg](prereg-2026-11-08-heldout-spot-check-deepseek-v4-pro-b.md)),
registered after part A's result and before any of these five runs. The other
half of the v2 cohort, one live run each, `main` at `9bd948c`,
`deepseek-v4-pro` through the `qwen` transport. Batch
`heldout-spot-2026-11-08-deepseek-v4-pro-b`; raw outputs private. Nothing
re-scored.

## Headline

- **Completion 5/5.**
- **TRL in range 3/5.** Two below floor: V08 量子密钥分发网络 at 6.7 against
  7–9, V10 vertical farming at 7.0 against 8–9. None above ceiling.
- **444,932 crew tokens**, 81,911–94,319 a run, mean 88,986. Serial wall
  time 38.1 minutes.
- **The decision rule stated in advance fires.** Two of the ten runs across
  both parts landed outside their range in the same direction, so this
  result does **not** recommend `deepseek-v4-pro` for the next thirty-run
  batch. The rule was written to be this blunt; what the two misses look like
  is below, for whoever writes that batch's protocol.

## Per unit, part B

| Case | Topic | Expected | TRL | Score | Sources A/P/M | Tokens | Time | Retries |
|---|---|---|---|---|---|---|---|---|
| V02 | continuous glucose monitoring for diabetes | 8–9 | 9.0 | 74.0 | 8/8/8 | 84,754 | 388 s | planner timeout before send, retried |
| V04 | pig kidney xenotransplantation | 5–7 | 7.0 | 60.6 | 8/2/6 | 81,911 | 438 s | writer guardrail once (cited unknown source `P4`), second attempt passed |
| V05 | battery-electric aircraft for regional passenger flights | 5–6 | 5.0 | 51.1 | 5/8/8 | 91,166 | 478 s | reviewer guardrail once (a correction's find text matched twice), second attempt passed |
| V08 | 量子密钥分发网络 (Chinese) | 7–9 | **6.7** | 63.1 | 8/8/8 | 94,319 | 473 s | planner timeout before send, retried |
| V10 | vertical farming for fresh produce | 8–9 | **7.0** | 67.1 | 6/7/8 | 92,782 | 446 s | writer guardrail once (cited unknown source `M9`), second attempt passed |

The runner counted 2 rate-limit hits per run again (10 in the batch). The
uncited-claim screen reported 0 in all five reports; every report passed the
section check.

## The ten runs together

| Case | Topic | Expected | TRL | Verdict | Tokens |
|---|---|---|---|---|---|
| V01 | robotic-assisted surgery | 8–9 | 8.0 | in range | 80,812 |
| V02 | continuous glucose monitoring for diabetes | 8–9 | 9.0 | in range | 84,754 |
| V03 | enhanced geothermal systems for electricity generation | 7–8 | 7.3 | in range | 77,022 |
| V04 | pig kidney xenotransplantation | 5–7 | 7.0 | in range (ceiling) | 81,911 |
| V05 | battery-electric aircraft for regional passenger flights | 5–6 | 5.0 | in range (floor) | 91,166 |
| V06 | space-based solar power | 3–5 | 5.0 | in range (ceiling) | 82,166 |
| V07 | hyperloop | 4–6 | 5.0 | in range | 87,980 |
| V08 | 量子密钥分发网络 | 7–9 | 6.7 | **below floor** | 94,319 |
| V09 | 特高压直流输电 | 8–9 | 9.0 | in range | 95,060 |
| V10 | vertical farming for fresh produce | 8–9 | 7.0 | **below floor** | 92,782 |

- **In range 8/10**, both misses below floor, none above ceiling. Three of
  the eight sit on a boundary (two ceilings, one floor).
- **Tokens**: 867,972 over ten runs, mean 86,797, range 77,022–95,060;
  v2's mean on `qwen3.8-max` was 91,745. The two Chinese topics are the two
  most expensive runs.
- **Retries, by node**: writer 3 (V09 malformed citation block; V04 and V10
  an unknown source id), scorer 1 (V07, a source from the wrong domain),
  reviewer 1 (V05, a correction target that matched twice), planner timeouts
  before send 3 (V01, V02, V08), one connection timeout mid-run (V07). All
  absorbed by the existing retries; nothing reached a report. Completion
  10/10, so the rule's first clause (a failure on the model's output) did
  not fire; the second did.
- **Grounding screen**: checked 0 claims in five of ten runs and 1–3 in the
  other five, nothing ungrounded, 1–7 market claims unverifiable per run.
  Said again as the silence it is.

## The two misses, read after the fact

Neither reading changes the verdict; both are for the next protocol.

- **V10 vertical farming** missed below floor under v2 as well (the planner
  drifted; see the v2 result). Here the plan held and the run delivered 6
  academic, 7 patent and 8 market sources; the scorer still put it at 7 with
  a scale-and-economics rationale, the mechanism the 2026-10-18 diagnosis
  named. Two models, two retrieval states, same direction: the topic's range
  or the rubric's handling of deployed-but-uneconomic technologies is the
  thing to examine, not this model alone.
- **V08 量子密钥分发网络** scored 6.7 against a floor of 7, with full
  evidence (8/8/8). The rationale weighs metropolitan networks in operation
  against a field-level reading. A Chinese topic with a Chinese anchor and
  an English rubric; a second run would say whether 6.7 is a position or a
  coin at the edge.

## What this does and does not say

- Ten held-out topics, one run each, all complete on current `main` with a
  model the code had never run; 8/10 inside ranges frozen three weeks
  earlier, both misses low. No calibration claim: the v2 measure needed
  thirty runs and its own thresholds.
- By the rule written before the batch, `deepseek-v4-pro` is not
  recommended for the next thirty-run batch on this evidence. The rule does
  not say the model is worse than `qwen3.8-max`; v2 scored 25/30 with three
  below-floor misses, two of them on topics this batch did not miss. It says
  the question deserves a protocol of its own, and the maintainer's unused
  free quota on several other models makes a same-topics, several-models
  comparison the obvious shape for it.
- Nothing about production, nothing attributed: model, evidence of the day
  and the anonymous OpenAlex pool differ from v2 together.
- Free quota used by both parts: 867,972 of 1,000,000 tokens on this model.
