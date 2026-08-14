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


---

## Result (measured 2026-08-14, both arms on the same frozen evidence)

**The hypothesis was wrong.** F2 tripped: the scope rule was not what pinned
those topics to their floors.

| | before | after |
|---|---|---|
| Runs sitting exactly on the floor | 14/30 | **14/30** |
| Pass rate vs anchored ranges | 28/30 | 27/30 |

| # | before | after | delta |
|---|---:|---:|---:|
| 01 CAR-T | 8.00 | 9.00 | **+1.00** |
| 02 | 6.00 | 6.00 | 0 |
| 03 | 5.00 | 5.00 | 0 |
| 04 | 6.00 | 6.00 | 0 |
| 05 | 7.33 | 7.33 | 0 |
| 06 | 7.00 | 7.00 | 0 |
| 07 | 6.00 | 6.00 | 0 |
| 08 | 4.00 | 4.00 | 0 |
| 09 | 5.67 | 5.83 | +0.16 |
| 10 | 2.00 | 2.00 | 0 |

- **P1 FAIL** — floor-sitting unchanged at 14/30
- **P2 FAIL** — 04, 05 and 07 did not move at all
- **P3 pass** — no global inflation; 09/10 essentially flat
- **P4 pass** — 27/30, one below baseline
- **F1 clear, F4 clear, F2 TRIPPED**

## What the arms show that the numbers do not

The gate worked *mechanically*. The scorer stopped invoking the
process/product distinction and now leads with the commercial evidence:

- 04 before: "initial shipments and product launches rather than widespread
  deployment" -> after: names Oxford PV, UtmoLight and GCL's commercial
  shipments
- 07 before: discussed bioreactor volumes -> after: names the US and
  Singapore approvals and three companies selling product

And then lands on 6.0 either way, with a different justification: "the
sector is still scaling, with most companies at pilot".

So the binding constraint is downstream of the rule I changed. The
commercial-signal table directly below says "multiple companies selling
commercial products -> TRL 8-9" and "1-2 companies with commercial products
or government-approved deployments -> TRL 7-8". Topic 07 satisfies both
rows — three named companies, two national approvals — and scores 6.0.
Something else is capping it.

## Decision

Keeping the gate, with the failure recorded rather than dressed up.

For: the rule genuinely was being applied to product topics it was never
written for, the reasoning it now produces is more honest, and 01 CAR-T
moving to 9.0 matches the strongest anchor in the set (marketed FDA-approved
products since 2017).

Against: it failed both predictions it was made for, and the pass rate fell
by one run. That run is on topic 09, whose range is the one marked
UNRESOLVED — a range I have already said I do not trust, so the -1 is
measured against a yardstick I disowned.

Reverting would also be defensible. What is not defensible is keeping it
*and* describing it as the fix for floor-sitting, which is what I would have
written had these criteria not been registered first.

## Next lead

Not another guess. Read what actually caps a score once the commercial
evidence is admitted — the candidates are the anti-overestimation guardrail
(difficulty 14's mirror), and whether "reported revenue or unit sales" in
the top row of the mapping is a condition market sources can essentially
never satisfy, so the scorer never reaches 8-9 by that path at all.
