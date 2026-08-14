# Pre-registration — narrowing the TRL PROCESS/TECHNOLOGY SCOPE RULE

Written **before** the change and before any run, and committed before the
baseline was measured. Registering the falsification criteria afterwards
would let any outcome be read as a success, which is the failure this file
exists to prevent.

## The finding this responds to

Against externally anchored expected ranges, **16 of 30 baseline runs land
exactly on their range's floor**, and five topics (02, 03, 04, 05, 07) score
their minimum acceptable value to the decimal. An unbiased scorer would
scatter inside the range.

## Diagnosed cause

`PROCESS/TECHNOLOGY SCOPE RULE` in `agents.yaml`, which the scorer is told to
apply **first**, before selecting a TRL signal. It instructs the scorer to
discount regulatory approvals and commercial launches as TRL evidence when
the topic names a process rather than the end product.

Read in the three floor-sitting rationales, the scorer names the commercial
milestone and then discounts it:

- 04 perovskite: cites the Oxford PV utility-scale shipment, then "initial
  shipments rather than widespread deployment" → 6.0
- 05 CRISPR: cites the FDA approval, then "broader clinical adoption ...
  still limited" → 7.0
- 07 cultivated meat: approval and retail sale are in the retrieved evidence;
  the rationale discusses bioreactor volumes instead → 6.0

Not a retrieval gap: `pilot line`, `approv`/`singapore`/`usda`/`retail` and
`phase 3` all appear in the retrieved evidence for those topics.

Provenance: added 2026-07-13 in `e179d83`, to stop an FDA approval for a
small-batch product from inflating a bioreactor **process** TRL — on the
cultivated meat topic, which is now one of the five sitting on its floor.

## The change

Gate the rule instead of deleting it. Its core claim is sound: a product
approval does not prove that an underlying *process* is mature. What is
wrong is that it is applied unconditionally, while most benchmark topics
name a product or an application rather than a process.

The rule will apply only when the topic names a process, method, or
scale-up; not when it names a product, therapy, device or application.

## Predictions (registered before running)

| # | Prediction |
|---|---|
| P1 | Runs sitting exactly on their range floor drop from 16/30 to **≤ 8/30** |
| P2 | Topics 04, 05, 07 each rise by **≥ 0.5** TRL (mean over 3 reps) |
| P3 | Topics 09 and 10 rise by **< 0.5** TRL — they are already above their ceilings |
| P4 | Pass rate against the anchored ranges stays **≥ 26/30** |

## Falsification criteria (registered before running)

| # | If this happens | Then |
|---|---|---|
| F1 | 09 or 10 rises by ≥ 0.5 | The change is a **global inflation**, not better discrimination. Revert. |
| F2 | Floor-sitting runs stay > 12/30 | The scope rule was **not the main cause**. Keep it gated anyway if harmless, and look elsewhere. |
| F3 | Any topic previously inside its anchored range moves outside it | The change **broke a case it was not meant to touch**. Revert. |
| F4 | Pass rate falls below 26/30 | Net regression. Revert. |

F1 is the one that matters. Raising every score would satisfy P1, P2 and P4
while making the system strictly worse at telling mature technologies from
hyped ones — which is the only thing this benchmark exists to measure.

## Method

Both arms run with `--fixtures`, replaying the same frozen evidence, so the
retrieval variance that made a one-shot comparison meaningless (sd 0.58,
difficulty 31) is removed and any difference is the rubric's.

    uv run python benchmark.py --fixtures --force --repeat 3 -c 3

Baseline recorded before the edit; treatment after; nothing else changed
between them.
