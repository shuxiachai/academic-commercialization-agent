# Patent applicants: parser check

**Date:** 2026-10-22.
**Status:** a check of a metadata parser, run on pages already fetched for
[patent family v1](results-2026-10-22-patent-family-v1.md). This is not a
registered experiment: no threshold was set in advance, and no report-quality
effect is claimed.

## Why

Web search returns patent rows without an applicant. In 66 of the 69 saved
runs with a report, the patent list named none. Each row's publisher was the
site instead: Google (416 rows), Wipo (72) or Justia (26). The patent task
received an empty assignee list, so a report could not say who holds the
patents it cites. For a commercialization reader, that holder is the
competitor or the party to license from.

## Parser

`src/academic_agent/patent_applicants.py` reads the header block of a
patent's Google Patents page:
- **Assignees.** It takes the current assignees, or the original ones when no current assignee is listed.
- **Inventors.** It uses them only when the patent is inventor-owned, listed as "Individual".

The parser anchors on each field's label. Assignees listed in the citation and
similar-document tables are therefore never taken. Only the first 256 KB of a
page is read.

## Check

The check covers the 276 readable pages cached for patent family v1 (its
development and test registries). Each page was parsed from its first 256 KB,
as production reads it.

| Check | Result |
|---|---|
| Original assignees parsed vs the page's `DC.contributor` assignee tags | 276/276 agree |
| Inventors parsed vs the `DC.contributor` inventor tags | 276/276 agree |
| Pages that name a company or institution | 240 (87%) |
| Inventor-owned pages ("Individual") | 36 (13%) |
| Pages that name nobody | 0 |
| Current assignee differs from the original | 52 (19%) |
| Header block ends within the first 64 KB / 256 KB | 97.8% / 100% (latest at 212 KB) |

The current assignee is the one shown. It differs from the original on about
one page in five, usually after an assignment, and it is the party to approach
now.

## Limits

- **The check shows the parser reads Google's data correctly, not that the data is right.** Both compared fields come from the same page. Google notes that its assignee list may be inaccurate, and every source named this way says so.
- **Some patent rows are never looked up.** Patentscope internal record ids and Justia assignee pages carry no publication number.
- **Pages were read on 2026-10-22.**

## Files

`evals/patent_applicants_check/check.py` reruns the check on the patent family
page cache:

```
python evals/patent_applicants_check/check.py . <page cache dir>
```
