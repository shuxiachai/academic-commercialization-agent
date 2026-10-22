# Erratum: the source-search comparison's observer becomes a snapshot

**Date:** 2026-10-22.

**Affects:**
- [public source-search comparison](prereg-2026-09-19-public-source-search-comparison.md);
- [public source-search baseline](results-2026-09-19-public-source-search-baseline.md);
- [qwen source-locator comparison](results-2026-09-19-public-source-locator-qwen-comparison.md).

## What changed and why

The 2026-09-19 comparison observed the shipped Sources renderer. Its observer
was three live files, bound by hash in
`report_evidence_source_locator_comparison.py` and in the comparison fixture:
- `web/static/js/result.js`;
- `web/static/js/i18n.js`;
- `tests/js/source_browser_contract.mjs`.

Keeping the comparison reproducible therefore froze the product's result page
and its strings. For a month every new label went into side tables, and
result-page changes were refused.

The observer is now a byte-identical copy of those three files, kept under
`evals/source_locator_observer_v1/`. The comparison module reads its assets
and runs its contract from there.
- **Unchanged:** the fixture, its pinned hash `FIXTURE_SHA256`, the asset hashes in `ASSETS`, the report it projects, and the cases.
- **Unpinned:** the live product files.

## Verification

- **Hashes:** each snapshot file's LF SHA-256 equals the hash pinned in `ASSETS` and in the fixture's `observer_assets`.
- **Baseline:** `run_fixed_comparison()` reports 6/6 observed cases and 12/12 paired observations. Its encoded result hashes to `ef2ba807…9e7d66ce`, the registered `PRIMARY_BASELINE_SHA256` of the qwen comparison.
- **Tests:** the comparison and qwen comparison suites pass. One test, which asserted that the observer receives the repository root, now expects the snapshot root.

## What this does not change

- **Results:** no result, label or registered reading of either comparison changes.
- **The qwen canary's identity list** still names the live paths, as registered. The canary runs only at its original commit, so this has no effect on what it measured.
- **Other pins:** `examples/solid-state-batteries-ev.md` and `evidence.py` stay pinned by their own experiments.
