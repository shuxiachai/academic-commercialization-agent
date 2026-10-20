# Held-out TRL calibration v2: 25/30 in range, and the top of the scale is reached

Date: 2026-10-19 (Australia/Sydney). Batch `heldout-trl-v2`, `qwen3.8-max`,
code `f4b6122` (retrieval changes #213 and #215; rubric and scoring formula
unchanged). Protocol: [pre-registration](prereg-2026-10-19-heldout-trl-v2.md).
The maintainer reviewed and confirmed the cohort ranges before dispatch.

**Disposition: supported.** 25 of 30 runs fell inside their expected range,
above the "supported" threshold (≥ 21). The registered expectation of 15–21
was wrong in the favourable direction.

The compression seen in v1 did not recur: 11 runs scored 8 or 9, against 0 in
v1. Low-maturity topics were not inflated; all three misses that delivered a
TRL fell below their floor. This batch cannot say which change produced the
difference, because the topics and the model also changed (see Reading).

## Primary measure

| ID | Topic | Expected | TRL (3 reps) | In range |
|---|---|---|---|---|
| V01 | robotic-assisted surgery | 8–9 | 9, 9, 9 | 3/3 |
| V02 | continuous glucose monitoring for diabetes | 8–9 | 9, failed, 9 | 2/3 |
| V03 | enhanced geothermal systems for electricity generation | 7–8 | 7, 7, failed | 2/3 (on floor) |
| V04 | pig kidney xenotransplantation | 5–7 | 6, 6, 6 | 3/3 |
| V05 | battery-electric aircraft for regional passenger flights | 5–6 | 5, 6, 6 | 3/3 |
| V06 | space-based solar power | 3–5 | 3, 3, 2 | 2/3 (below) |
| V07 | hyperloop | 4–6 | 4, 3, 2 | 1/3 (below) |
| V08 | 量子密钥分发网络 | 7–9 | 7, 7, 7 | 3/3 (on floor) |
| V09 | 特高压直流输电 | 8–9 | 9, 9, 9 | 3/3 |
| V10 | vertical farming for fresh produce | 8–9 | 8, 8, 8 | 3/3 (on floor) |

**25 / 30 in range.** 28 runs completed. Two failed and count as not in range:

- **V02 rep 2.** The reviewer's correction plan exceeded its 2,000-character field bound, and the guardrail rejected it after one retry.
- **V03 rep 3.** The model provider returned an `Arrearage` account error.

## Secondary measures

1. **Compression (registered reading).**
   - Distribution: 2 (2 runs), 3 (3), 4 (1), 5 (1), 6 (5), 7 (5), 8 (3), 9 (8).
   - **11 runs scored 8 or higher**, so the registered "compression persists" reading does not apply. Five runs scored exactly 7, against 20 in v1.
   - Every run on the four topics with a floor of 8 that completed landed in range (V01, V02, V09 at 9; V10 at 8). V10's business failures did not pull it below 8.
2. **Inflation check (F1).** **0 of 9** runs on V05–V07 exceeded their ceiling, against the flag at 4 or more. No inflation.
3. **Direction of misses.**
   - All three misses that delivered a TRL fell **below** the floor: space-based solar power at 2, and hyperloop at 3 and 2. By the registered rule, this is a directional bias toward under-scoring, now at the low end of the scale. Mean distance outside the range: 1.33.
   - 12 in-range runs sit exactly on their floor: V08 and V10 three each, V03 and V06 two each, V05 and V07 one each.
   - Topics in range in all three repetitions: 6 of 10. V02 and V03 lost a repetition to the failed runs.
4. **Retrieval level.**
   - **Anchor-entity coverage.** 8 of 10 topics had a market source naming one of their fixed anchor entities in at least two runs, against a prediction of ≥ 7. The two exceptions:
     - V06 (no Caltech or Aetherflux source);
     - V09, a Chinese input whose sources describe UHVDC generally but name none of the anchor projects.
   - **Query audit.** The topic deployment query ran in 30 of 30 runs (prediction ≥ 27). No component query supplied more than one market source (prediction met). Of 229 market sources, 160 came from the topic's own deployment and revenue queries and 12 from component queries; v1 had 0 and 166.
   - **Market-size titles:** 94 of 229 (41%), against 102 of 219 (47%) in v1, by the audit script's lower-bound pattern.
5. **Input shapes (n = 9, descriptive).** 7/9 in range. V08 and V09 (Chinese) were 3/3 each; V07 (the one-word input `hyperloop`) was 1/3.
6. **Existing proxies.** Completion 28/30. Report structure complete in 28/28 by `benchmark_check.py`, including the Chinese reports. Uncited numeric lines: 0 across 28 reports.
7. **Cost.** Recorded Crew-node cost was USD 7.17 for 2,752,364 tokens, at the upper-bound price basis (2.00 / 6.00 USD per million tokens). About 220 web searches were made, within the Tavily plan.

## Exploratory comparison (not registered)

A constant scorer:
- answering 7 would land in range on V03, V04 and V08: **9 / 30**;
- answering 9 would reach **15 / 30**.

The system's 25 comes from placing topics at both ends of the scale, which neither constant scorer can do.

## Reading

- **The registered result supports held-out calibration** at `qwen3.8-max` with the current retrieval. The specific v1 defect, no score above 7 for proven technologies, did not recur on this cohort.
- **Which change mattered is not established.** Three things differ from v1:
  - the retrieval changes;
  - the model (`qwen3.8-max` against `qwen3.7-plus`);
  - the topics. Several v2 topics are unambiguous at 9 (da Vinci, UHVDC), while v1's mature topics were less clear-cut.

  A frozen-evidence comparison would separate the model from retrieval: replay v1's saved evidence with `qwen3.8-max`. It would need its own protocol.
- **The low end now leans low.** Hyperloop and space-based solar power were scored below their anchors' floors. The ranges for these two rest on judgement about how far short-track and in-orbit component tests count, so the miss is as much a question about the anchors as about the scorer.
- **The ranges are not expert ground truth.** They were anchored by an AI assistant with web search and reviewed by the maintainer.

## Execution record

- **Preflight passed** at 15:21, and dispatch followed.
- **Monitor replaced.** The first monitor counted a unit's initial `running` record as finished. That could have stopped the batch after two real consecutive failures instead of three. At 15:23 it was replaced, without touching the benchmark process, by one that counts terminal records only. No unit was affected.
- **Arrearage stop.** At 17:27 the stop rule for provider account errors halted the batch on V03 rep 3 (`Arrearage`), after 23 finished runs.
- **Resume.** The maintainer topped up the account, and the batch resumed at 17:30 under the unchanged identity (same commit, model and settings), after a fresh preflight:
  - 21 successes were verified and reused, and 7 units never started were run;
  - the two occupied failed units were not retried. A wrapper outside the repository applied the concurrent path's existing occupied-unit rule to the serial path, as in v1's batch b; benchmark.py's bytes and the batch identity were unchanged.
- **No outcome was inspected before completion.** Monitoring reported counts, cost and searches only, and the failed runs were read through their error records.

## What this cannot establish

- Which of retrieval, model or topic choice produced the difference from v1.
- Source truth, claim support or user value.
- Behaviour on other models or later web evidence. Retrieval was live on 2026-10-19.
- A general accuracy rate, from ten topics with AI-anchored ranges.

These topics are now consumed for held-out purposes.
