# Held-out TRL calibration v1: 21/30 in range, with scores compressed toward 7

Date: 2026-10-18 (Australia/Sydney). Batch `heldout-trl-v1-c`, `qwen3.7-plus`,
code `2a4f2f7`. Protocol: [pre-registration](prereg-2026-10-18-heldout-trl-v1.md),
[runner erratum](errata-2026-10-18-heldout-trl-v1-harness.md) and
[model amendment](protocol-2026-10-18-heldout-trl-v1-amendment-qwen37.md).

**Disposition: supported at the registered threshold, with a registered
directional bias toward under-scoring.** 21 of 30 runs fell inside their
expected range, which is the "supported" threshold (≥ 21) and inside the
registered expectation of 19–24. The secondary measures qualify that reading
substantially: no run scored above 7.

## Primary measure

| ID | Topic | Expected | TRL (3 reps) | In range |
|---|---|---|---|---|
| H01 | small modular reactors for grid electricity | 7–9 | 7, 7, 7 | 3/3 (on floor) |
| H02 | fusion power | 3–5 | 6, 6, 6 | 0/3 (above) |
| H03 | implantable brain-computer interfaces for paralysis | 5–7 | 7, 7, 7 | 3/3 |
| H04 | psilocybin therapy for treatment-resistant depression | 7–8 | 7, 7, 7 | 3/3 (on floor) |
| H05 | direct air capture of carbon dioxide | 6–8 | 7, 7, 7 | 3/3 |
| H06 | 漂浮式海上风电 | 8–9 | 7, 7, 7 | 0/3 (below) |
| H07 | 人工光合作用制备太阳能燃料 | 3–5 | 4, 4, 4 | 3/3 |
| H08 | precision fermentation for dairy proteins | 7–9 | 7, 7, 7 | 3/3 (on floor) |
| H09 | DNA data storage | 4–6 | 6, 6, 6 | 3/3 |
| H10 | drone delivery of medical supplies | 8–9 | 6, 7, 7 | 0/3 (below) |

**21 / 30 in range.** All 30 runs completed and none counted as a failure.

## Secondary measures (registered as descriptive)

1. **Topics in range in all three repetitions: 7 of 10.** The tuned baseline also had 7 of 10.
2. **Direction of misses.** Six misses fall below the floor (H06, H10) and three above the ceiling (H02): two thirds on one side, so by the registered rule this is a **directional bias toward under-scoring**. The mean distance outside the range is 1.11 levels. Nine of the 21 in-range runs sit exactly on their floor (H01, H04, H08, all at 7). That repeats the floor-sitting pattern [diagnosed before](prereg-2026-08-14-trl-scope-rule.md).
3. **Score compression.** Only three values occur: 4 (3 runs), 6 (7) and 7 (20). **No run scored 8 or 9.** That includes two technologies proven at scale in commercial operation: Zipline has made more than 2 million deliveries since 2016, and Hywind Scotland has run commercially since 2017. At the other end, fusion power, with no net-electricity device, scored 6. Nine of ten topics gave identical scores across their three repetitions.
4. **Input shapes (n = 9, descriptive only).** English topics: 18/21 in range. The short input `fusion power` was 0/3. The Chinese inputs were 3/6: H07 3/3, H06 0/3. Both misses outside English topics follow the compression pattern, so this does not isolate a language or length effect.
5. **Existing proxies.**
   - Completion: 30/30. Weighted-formula correctness: 30/30. Uncited numeric lines: 4 across 30 reports.
   - Report structure: `benchmark_check.py` reports 24/30. All six "incomplete" reports are the Chinese ones, and a manual check found all eight sections present under localized headings. The checker matches English headings only, so this is a **checker limitation, not missing structure**.
6. **Source mix under #204.** Of 204 academic sources, 8 were graded as preprints and 9 as repository deposits (17, about 8%).
7. **Cost.** Recorded Crew-node cost was USD 2.86 for 2,406,649 tokens, using the amendment's upper-bound price basis (0.85 / 3.40 USD per million tokens), so it overstates actual billing. Helper calls are not counted.

## Exploratory comparison (not registered)

A constant scorer that always answers 7 would land in range on H01, H03, H04,
H05 and H08: **15 / 30**. The system's six additional hits all come from
low-maturity topics: H07 correctly at 4 and H09 at 6. It discriminates
immaturity in part. It does not reach the upper levels on this cohort, and it
over-scored the one topic expected at 3–5 that it missed (H02).

## Reading

- The registered primary result supports held-out calibration at
  `qwen3.7-plus`. It does **not** support reading TRL as fine-grained. On these
  topics, scores cluster at 6–7, and mature technologies are scored below
  their external anchors.
- This is consistent with, but not proof of, the rubric's commercial-signal
  table being applied conservatively. Diagnosing the cause needs a separate
  protocol. Changing the rubric and re-scoring these consumed topics would not
  be validation.
- The ranges were anchored by an AI assistant with web search and reviewed by
  the maintainer. They are not expert ground truth.

## Execution record

- **Batch `heldout-trl-v1`** (`qwen3.5-plus`): stopped on a runner defect before any agent ran. See the [erratum](errata-2026-10-18-heldout-trl-v1-harness.md).
- **Batch `heldout-trl-v1-b`** (`qwen3.5-plus`): closed after a false-positive monitor stop and a provider `Arrearage` account error. Its five successes were not inspected and are not used here. See the [amendment](protocol-2026-10-18-heldout-trl-v1-amendment-qwen37.md).
- **Batch `heldout-trl-v1-c`**: preflight passed. At the maintainer's request it was paused after 14 runs, at a unit boundary between runs, with no unit lost. It resumed under the unchanged identity: 14 reused, 16 new, 0 failed. No stop rule triggered.
- **One interim outcome was seen** before completion. Verifying the pause boundary displayed one log line with H04 rep 2's TRL (7, in range). Nothing was changed in response.
- The production deployment was switched to `qwen3.7-plus` by the maintainer during this work, so the measured configuration matches production.

## What this cannot establish

- Source truth, claim support or user value.
- Behaviour on other models or on future web evidence. Retrieval was live on 2026-10-18.
- A general accuracy rate, given ten topics and AI-anchored ranges.

These topics are now consumed for held-out purposes.
