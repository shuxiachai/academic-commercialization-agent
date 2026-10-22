# Patent family v1: both bars hold

**Date:** 2026-10-22.
**Status:** test split read once, under the
[protocol](prereg-2026-10-22-patent-family-v1.md). The protocol was committed
and pushed (7f9368c, 16:04 +11:00) before any test page was fetched.
**Production:** the registered reading adopts the rule for the web-search
patent path. The integration is a separate change.

## Result

| Measure | Definition | Bar | Test |
|---|---|---|---|
| P precision | rejections whose two rows share a family / rejections with known truth | ≥ 0.90 | 27/29 = **0.93** |
| R recall | true duplicates the rule rejects / true duplicates | ≥ 0.40 | 27/33 = **0.82** |

29 rejections have known truth, more than the five a conclusive test needs.
Both bars hold.

## What was measured

**Registries.** The test split has 46 patent registries with 345 rows and 164
unique publication numbers. 163 pages were read; one returned 404, and 11 rows
give no number in their URL.

**True family duplicates:** 33 rows (10%). Another 21 rows are unknown.

**The current whole-title check rejected none.**

**The frozen rule rejected 29 rows (17 unique pairs):**
- 16 of the 46 registries lost at least one duplicate;
- the most in one registry was four of eight, in a psilocybin run (`H04`);
- all three runs of that topic lost three or four.

## The two wrong rejections

Both are one pair, in the two small-modular-reactor runs. CA2602288C and
US8177480B2 share the title "Modular system for generating electricity from
moving fluid". Each registry kept one and rejected the other.

The two have the same inventor (Edouard Petrounevitch). Both claim Canadian
application 2,504,776, with priority date 2005-04-15 and filing date
2006-03-08. Google Patents lists them in different DOCDB families, and each
names the other only under "Similar Documents".

Under the registered truth, the rejection is wrong. If the two are one
invention, as these fields suggest, precision would be 29/29.

## The six missed duplicates

Descriptive only; the rule was not changed after the test was read.
- **Different titles for one family:** a continuation retitled ("Dispersed space based laser weapon" against "Solar powered space weapon"), and one claim reworded ("including" against "comprising").
- **A translated title:** an EP publication with its German title, in two hyperloop runs.
- **A title the key does not clean:** "1. wo2015179213 - large-scale space-based solar power station", with a list number and a lower-case publication number, in two runs.

## Reading

**Adopted.** Under the registered reading, production uses `same_invention`
in the web-search patent path, in place of the whole-title check. No TRL or
score effect is claimed.

**What the duplicates cost.** On the test registries, 29 of 345 patent rows
(8%) were another publication of an invention already listed. In the worst
registry, four of eight were. A reader counting patents, or reading the
applicant list, saw one invention several times.

**What a later version could add.** Case-insensitive number removal would
catch the "wo2015179213" pair. Translated and reworded titles need the family
list itself, for example from the Google Patents page this test read. Neither
is part of this change.

## Limits

- **The registered limits stand.**
  - A DOCDB family is not one invention.
  - Google Patents is the only source of truth.
  - The effect on delivered patents is not measured: in production, the slot a rejected duplicate frees goes to the next candidate.
  - Pages were read on 2026-10-22.
  - The Lens.org path is not covered.
- **The rule was shaped on development.** Its office and kind condition came from the two wrong pairs found there. The test is the first reading of that choice.
- **Repeated runs repeat pairs.** The 29 rejections are 17 unique pairs, and the one wrong pair counts twice.

## Files

`evals/patent_family_v1/`:
- `test_families.json`: the test registries, each row's publication number, and the family recorded from its page;
- `dev_families.json`: the development split, unchanged;
- `families.py` and `evaluate.py`, as registered.

To rerun the test reading, from the repository root:

```
python evals/patent_family_v1/evaluate.py . evals/patent_family_v1/test_families.json
```
