# Patent relevance v1: development comparison, no word rule advanced

**Date:** 2026-10-22.
**Status:** development only. No rule met the bar, so no protocol was
registered and no test row was labelled or read.
**Production:** the patent title gate is unchanged. Justia listing pages are
now rejected as non-records; see the end of this note.

## Question

The patent gate accepts a web-search patent when its title shares enough
topic keywords. One small-modular-reactor run accepted five solar and wind
patents through "modular" and "electricity". The academic gate was tightened
with rule R5, which anchors acceptance on the user's own words. Would R5, or
a similar word rule, remove mostly off-topic patents?

## Method

- **Pairs.** The development split is every patent accepted in the held-out v2 registries: 134 unique pairs of topic and patent, across 10 topics.
- **Labels** (`dev_labels.json`) were made by an AI assistant before any rule was scored.
  - Inputs: the topic, the patent title, and its Google Patents abstract (the search snippet when no page was read; 125 of 134 had an abstract).
  - **On-topic:** the invention is the topic's technology, a direct variant, or a component, method or application specific to it.
  - **Off-topic:** a different technology that shares words, technology not specific to the topic (a battery cell for any "electric device"), or not a patent record.
- **Rules** (`report.py`). Every pair was accepted by the current gate, so each rule can only remove rows. The rules use the production R5 functions.
- **Bar**, set as for the two-word gate before scoring: at least 5 rows removed, with off-topic and on-topic removals at a ratio of at least 2:1.

## Result on development

Off-topic pairs: 14 of 134 (10%):
- hyperloop: 5 of 15 (high-speed steel, copper plating, a gear reducer, a wheeled railway, a vacuum heater);
- space-based solar power: 5 of 13 (two Justia listing pages, space data centers, two space weapons);
- battery-electric aircraft: 3 of 17 (a fuel-cell aircraft, two generic battery cells);
- UHVDC transmission: 1 of 13.

| Rule | Removed | Off-topic | On-topic |
|---|---:|---:|---:|
| R5 on the patent title | 31 | 11 | 20 |
| A user word in the title | 14 | 5 | 9 |
| The planned phrase in the title | 18 | 7 | 11 |
| R5 on the title or the abstract | 20 | 10 | 10 |
| The planned phrase in the title or the abstract | 11 | 5 | 6 |
| Not an assignee listing page | 2 | 2 | 0 |

No relevance rule meets the bar. The listing-page check is a record-validity
check, not a relevance rule (see below).

## Reading

**Patent titles do not use the topic's words.** The relevant patents that
these rules remove describe the technology generically:
- "Aircraft with electric propulsion means" and "Electric VTOL aircraft with swappable battery" under battery-electric aircraft;
- "Vacuum tube transportation system" (1950) and "Tube transport system for very high vehicle speeds" under hyperloop;
- "Robotic surgical devices, systems and related methods".

Adding the abstract helps the off-topic side, catching 10 of 14, but it still
removes as many relevant patents. As in the two-word gate result, word overlap
does not carry the sense distinction. "High-speed steel" and a
"high-speed vacuum tube" share the same words.

**What would.** Sorting these needs a judgment of what the invention is, for
example a model reading the abstract. The abstract is already on the Google
Patents page read for each patent's applicant, so such a check would need no
extra request. It would need its own evaluation, because it adds a model call.

**Off-topic patents are fewer than the motivating run suggested.** One in ten
accepted development patents is off-topic, and they cluster by topic: none
for six of the ten topics, and a third or more for hyperloop and space-based
solar power.

## Justia listing pages

Two "patents" were Justia pages listing an assignee's patents
(`patents.justia.com/assignee/...`), not patent records. This is a validity
error in the collector, not a relevance question. The web-search patent path
now rejects any Justia URL outside `/patent/` as "not a patent record". The
two development cases, from one run, are the only such rows in any saved
registry.

## Limits

- **AI labels**, not human gold, from abstracts rather than claims.
- **One label set**, ten topics, 134 pairs. The rate of off-topic patents is a development observation, not an estimate for production.
- **Accepted patents only.** Rejected candidates were not saved with abstracts, so recall effects are not measured.

## Files

`evals/patent_relevance_v1/`:
- `build_pairs.py`: builds the pairs from saved registries and the cached patent pages;
- `dev_labels.json`: the pairs, labels and rubric;
- `report.py`: reproduces the table.

```
python evals/patent_relevance_v1/report.py . evals/patent_relevance_v1/dev_labels.json
```
