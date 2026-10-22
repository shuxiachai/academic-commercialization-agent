# Market page dates v1: all three bars hold

**Date:** 2026-10-22.
**Status:** test split read once, under the
[protocol](prereg-2026-10-22-market-page-dates-v1.md) registered before any
test page was fetched.
**Production:** the registered reading adopts the change for market sources.
The integration is a separate change.

## Result

| Measure | Definition | Bar | Test |
|---|---|---|---|
| P1 precision | found within one day / dated | ≥ 0.80 | 75/85 = **0.88** |
| P2 contradictions | contradicted / dated | ≤ 0.05 | 2/85 = **0.024** |
| C coverage | dated / admitted by `should_date` | ≥ 0.50 | 85/109 = **0.78** |

All three bars hold.

## What was measured

**Pages.** The test split has 167 unique market URLs, from runs collected
between 2026-10-18 and 2026-10-21.
- `should_date` admits 109 of them. It excludes 56 market reports, one Wikipedia page and one home page. Both counts match the protocol.
- `probe.py` read 97 of the 109 admitted pages. The other 12 refused or failed, and none of their URLs carries a date.
- 85 pages were dated: 84 from JSON-LD and one from a `<meta>` tag. The remaining 12 readable pages state no date.

**Verification.** `verify.py` rendered all 85 dated pages in headless
Chromium. It found the extracted date, within one day, on 75 of them.

**Coverage by source type:**

| Source type | Admitted | Dated |
|---|---:|---:|
| reputable_news | 58 | 56 |
| company_disclosure | 35 | 27 |
| government | 8 | 1 |
| research_institute | 8 | 1 |

## The ten rows the search did not find

An AI assistant labelled each row from the page's full rendered text
(`test_labels.json`).

| Extracted | Page | What the page shows | Label |
|---|---|---|---|
| 2026-01-07 | energy.gov, nuclear fact sheet | byline "January 19, 2026" | contradicted |
| 2024-05-01 | landbase, carbon-capture company list | "August 18, 2026" above the title; the text describes 2026 events | contradicted |
| 2025-09-18 | cbinsights, BCI startups (two URL forms) | "SEPTEMBER 18, 2025" | same date, other form |
| 2026-04-30 | paradromics blog | "APR 30, 2026" | same date, other form |
| 2025-10-09 | sofinnova news | "9 October, 2025" | same date, other form |
| 2026-07-13 | newmarketpitch, BCI valuations | only "Updated 10 October 2026" | not printed |
| 2026-10-10 | newmarketpitch, BCI deals | only "Updated 6 October 2026" | not printed |
| 2026-04-07 | bioprocesstools | "April 2026", "Last updated: July 2026" | month only, consistent |
| 2025-06-27 | techxplore | a bot-check page; the URL carries 2025-06 | unreadable |

## Deviations from the protocol

1. **Two labels were added.** The registered rubric had three labels:
   contradicted, not printed and unreadable. Five pages fit none of them.
   - Four print the extracted date in a form the registered search misses: upper case, or "9 October, 2025". These are labelled `same_date_other_form`.
   - One prints only a month that contains the extracted date. It is labelled `month_only_consistent`.

   Neither added label counts toward P1 or P2. P1 stays the registered search
   alone. A case-insensitive search that also accepts "D Month, YYYY" would
   give P1 = 79/85 = 0.93.
2. **The labels were corrected before this write-up.** A first pass read only
   the 700-character excerpts saved in `test_verify.json`. It mislabelled four
   rows: it missed the printed dates on both cbinsights copies, the sofinnova
   page and the energy.gov byline. The committed labels come from a second pass
   over the full rendered text, aided by a list of every date-like phrase on
   each page. The correction raised the contradictions from one to two.
3. **The labeller was not blind.** `verify.py` prints its counts, so the
   labeller knew that up to four contradictions would stay within P2.
4. **Update dates were read as "not printed".** The rubric says today's date
   and other articles' dates do not count. It does not mention update dates,
   which are modification dates and which the extractor also ignores. If both
   newmarketpitch update dates were instead taken as the pages' own dates,
   P2 would be 4/85 = 0.047, still within the bar.

## Reading

**Adopted.** Under the registered reading, production reads the page date for
each accepted market source that has no date and that `should_date` admits.
No TRL or report-quality effect is claimed.

**What a date tells the reader.** All 85 dated sources would have been listed
as "n.d." before. Measured from the day each run collected its sources:
- 38 were more than a year old, and 9 more than two years old;
- 9 were at most 90 days old;
- the median age was 318 days.

**When the metadata is wrong, it is older than the page claims.** There are
three contradictions so far: indiatimes in development, and energy.gov and
landbase here. Each page prints a later date than its metadata. A source
dated this way looks older than it is, not newer. Three cases do not make a
rate.

**Coverage is mostly news.** News pages were nearly all dated (56/58).
Company pages were dated less often (27/35), and government and research
pages rarely (1/8 each).

## Limits

- **The registered limits stand.**
  - A page that prints the same wrong date cannot be caught.
  - Pages were read on 2026-10-22, not on the day each run collected them.
  - Coverage depends on which sites refuse automated requests.
- **The margin on P2 is small.** The bar allows four contradictions in 85
  dated pages, and two were found. One split of 85 pages is the whole test.
- **The labels are by an AI assistant, who was not blind**, not by a human.

## Files

`evals/market_dates_v1/`:
- `test_probe.json`: one row per test URL, with the date and method found;
- `test_verify.json`: the render check for each dated row, with an excerpt for each row not found;
- `test_labels.json`: the ten labels and the rubric as applied;
- `dev_probe.json` and `dev_verify.json`: the development split, unchanged.

To rerun the test split, from the repository root:

```
B=outputs/benchmark-runs
python evals/market_dates_v1/probe.py . $B/heldout-trl-v1,$B/heldout-trl-v1-b,$B/heldout-trl-v1-c,$B/academic-gate-live-v1,$B/hyperloop-confirm-v1 <cache> test_probe.json evals/market_dates_v1/dev_probe.json
python evals/market_dates_v1/verify.py . test_probe.json <render cache> test_verify.json
```

The rerun reads today's pages, so its counts can differ.
