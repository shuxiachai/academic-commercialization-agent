# Hyperloop confirmation: both runs complete in range after the planner fix

Date: 2026-10-21 (Australia/Sydney). Two live end-to-end runs of held-out
case V07 (`hyperloop`, expected TRL 4–6). This is a confirmation, not a
registered measurement.

- **Code:** `8d240ed`, which includes #248.
- **Model:** `LLM_PROVIDER=qwen`, `QWEN_MODEL=qwen3.8-27b`.
- **Batch:** `hyperloop-confirm-v1`.
- **Approval:** the maintainer approved one or two further runs within the
  free quota.

## Result

| Run | Status | Academic sources | Off-topic | TRL (4–6) |
|---|---|---|---|---|
| rep 1 | success | 7 | 0 | **6** ✓ |
| rep 2 | success | 7 | 0 | **5** ✓ |

- **Plan:** both runs planned "Hyperloop transportation system", with
  aliases "Vacuum tube transport" and "Low-pressure tube transit".
- **Sources:** both delivered the same seven academic sources.
  - Six are arXiv hyperloop papers already labelled relevant in title gate
    v1, among them "Hyperloop System Optimization" and "Hyperloop: A
    Cybersecurity Perspective".
  - The seventh is a PubMed paper on electrodynamic suspension coils for
    hyperloop.
- **Top-up:** the shortfall top-up was not used.

**Comparisons:**
- **Live check, before #248:** all four hyperloop runs stopped at the
  academic minimum with 1–2 sources.
- **Held-out v2 (`qwen3.8-max`, old gate):** hyperloop scored 4, 3 and 2,
  and 41% of its academic sources were off-topic.

**Cost:** 71,961 and 72,109 Crew-node tokens.

## Deviation

**Interrupted after rep 1.** During rep 1 the working tree was switched to a
dependency branch, so it no longer matched the batch identity. The batch
correctly refused to start rep 2: "Execution/fixture identity changed after
batch acceptance".

**Rep 2 resumed unchanged.** After returning to `8d240ed`, rep 2 ran under
`--resume-batch hyperloop-confirm-v1`. The identity and rep 1's artifacts
were verified, and rep 1 was reused, not rerun.

## What this cannot establish

- **Two runs on one topic.** The TRL agreement is consistent with the fix
  but does not measure calibration.
- **Hyperloop is a development topic.** It motivated the gate.
- **The labels are not human gold.** Relevance labels are from an AI
  assistant.
