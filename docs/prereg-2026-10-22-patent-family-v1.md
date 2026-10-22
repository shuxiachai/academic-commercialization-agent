# Patent family v1: protocol

**Date:** 2026-10-22.
**Status:** registered before any test-split patent page was fetched.

## Why

Web search returns one row per patent publication. One invention can therefore
take several of a run's patent slots, when it was filed in several offices or
published as an application and then granted. In one held-out run, five of
eight slots held the same psilocybin treatment, filed in AU, EP, US, CA and WO.

The collector already has a duplicate check, but it compares whole titles.
Google Patents titles carry the publication number ("US9422922B2 - ... - Google
Patents"), so family members never match. On the development registries the
check rejected nothing.

## Change under test (frozen)

`src/academic_agent/patent_family.py`, `same_invention(title_a, url_a, title_b, url_b)`.
Two patent rows are one invention when either holds:
- **Same publication.** Both URLs give the same number without its kind code, from any host (Google Patents, Patentscope or Justia).
- **Matching titles across offices or stages.** The titles match once publication numbers and the site name are removed, and the numbers come from different offices or are an application and a grant (A vs B kind). A cut-off title ("...") of at least four words may match the start of the other.

Two same-kind publications from one office with one title, such as two
Chinese grants or two US applications, are kept apart. A row without a
publication number in its URL is never merged.

If adopted, production uses this rule in the web-search patent path in place
of the whole-title check. A candidate the rule takes for an invention already
accepted is rejected, so the next candidate can take the slot. That
integration is not part of this test, which replays saved registries.

## Ground truth

- **Lookup.** Each patent row's publication number is read from its URL. Its Google Patents page is fetched once, sequentially and paced; robots.txt allows `/patent/`.
- **What is recorded:** the page's own number, its "Also Published As" table (the DOCDB family) and its "Other versions".
- **Same family:** two rows are the same publication, or their recorded sets share a member.
- **Unknown:** a row whose page cannot be read, or whose URL gives no number.

**A DOCDB family is broader than one invention.** It groups publications that
share their priority claims, and a company can file several applications from
one provisional. In development, WO2018013161A1, WO2018013162A1 and
US20180014486A1 share a family, yet they claim a farming system, a growth tower
and a control system. Recall is therefore measured against a target that
includes some distinct inventions.

## Development (held-out v2 registries)

**Data.** 27 of the 30 runs have patents: 216 rows with 127 unique
publication numbers. 123 pages were read.
- Four 2026 Justia publications are not on Google Patents (404).
- Seven rows give no number: Patentscope internal record ids, and Justia assignee pages.

**True family duplicates:** 18 of 216 rows (8%). Another 30 rows are unknown.

| Rule | Rejected | Correct | Wrong | Recall |
|---|---:|---:|---:|---:|
| Current whole-title check | 0 | 0 | 0 | 0/18 |
| Titles only (numbers and site removed, cut-off prefix) | 14 | 11 | 3 | 11/18 |
| Frozen rule | 11 | 11 | 0 | 11/18 |

The titles-only rule's three wrong rejections come from two pairs:
- two Chinese grants titled "A centralized quantum key relay network and key distribution method", from different applicants and years (two runs);
- two US applications titled "Vertical farming systems and methods", filed in 2017 and 2021.

**Set on this split after reading its results:**
- removing numbers and the site name;
- the four-word minimum for cut-off titles;
- keeping same-kind publications from one office apart.

**Disclosure.** The problem was found by listing near-identical titles across
every saved run, test batches included. That listing showed titles only. No
test-split page was fetched and no rule was scored on a test row before this
registration.

## Test split

The patent registries of the batches `heldout-trl-v1`, `heldout-trl-v1-b`,
`heldout-trl-v1-c`, `academic-gate-live-v1` and `hyperloop-confirm-v1`: 46
registries with 345 rows. Both counts were taken from the saved registries
before any page was fetched.

## Procedure

1. Run `families.py` over the five test batches, with the development page cache, so pages shared with development are not fetched again.
2. Run `evaluate.py` on the result, once.

## Measures and bars

| Measure | Definition | Bar |
|---|---|---|
| P precision | rejections whose two rows share a family / rejections with known truth | ≥ 0.90 |
| R recall | true duplicates the rule rejects / true duplicates | ≥ 0.40 |

**Reading.**
- If both bars hold, production adopts the rule for the web-search patent path.
- If either fails, production is unchanged, and the result names the failing bar.
- If fewer than five rejections have known truth, the test is inconclusive, and production is unchanged.

No TRL or score effect is claimed either way.

## Limits

- **A DOCDB family is not one invention,** as described above.
- **Google Patents is the only source of truth.** Its family lists may be incomplete.
- **Saved registries come after selection.** In production, the slot a rejected duplicate frees goes to the next candidate, which a replay cannot show. The effect on delivered patents is not measured.
- **Repeated runs of a topic repeat the same pairs.** Both per-registry and unique-pair counts are reported.
- **Pages are read on 2026-10-22,** not on the day each run collected them.
- **The Lens.org path is not covered.** No saved run used it, and its titles carry no numbers.
