# Patent applicants check

Result: [parser check](../../docs/results-2026-10-22-patent-applicants-check.md).

`check.py` parses each cached Google Patents page with
`src/academic_agent/patent_applicants.py`, reading only its first 256 KB as
production does. It compares the original assignees and inventors it reads
with the page's own `DC.contributor` tags. The page cache is the one
`evals/patent_family_v1/families.py` fills. No request is made.
