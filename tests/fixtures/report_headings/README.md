# Fixtures: the Chinese report saved under English headings

From two runs on the deployment on 2026-11-18 (topic 钠离子电池用于电网储能): one
that failed after its reviewer, and the run resumed from it. Read on 2026-11-19
with the maintainer's consent (GET requests only), who also agreed to these
excerpts being kept here.

- `resumed_run_report_excerpt.md`: the resumed run's saved report, cut down.
  Kept as saved, byte for byte: the title, the applicability paragraph, all
  nine headings, the reference legend, eight lines of the report's text and
  seven of its 24 reference entries. Everything else was removed, so some
  citations point at entries that are not here, and the file is not a report
  anyone should read for its content. Like the saved file, it ends without a
  newline and has no proofreading record.
- `run_status_excerpts.json`: the fields of the two runs' status that the
  tests and `docs/results-2026-11-19-report-headings.md` rely on: the failed
  run's two `heading_translation` attempts, and the resumed run's empty
  auxiliary record and reused nodes.

Used by `tests/test_report_headings.py`.
