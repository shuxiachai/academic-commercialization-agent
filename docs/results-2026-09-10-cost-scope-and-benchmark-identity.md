# Cost scope and immutable benchmark identity

## Premise and measurement

Starting revision: `09c7280bb08e8038837ffca74c812cea97eab52e`.
This is an offline maintenance change, not authorization for a provider run,
restart, new source retrieval, or experimental Tool Calling activation.

The first baseline invocation hit Windows access denial on the existing system
pytest temporary root before fixture setup. A new workspace-local temporary
root, as documented in CONTRIBUTING, passed **2784 tests + 1223 subtests**.
No warning filters, skips or assertions were weakened.

All 30 stored benchmark meta files lack the new execution identity. A read-only
digest of every file under `outputs/benchmark/`, including relative path names,
was `4fd0a8f8248ed102e837d19b96b8f39237d0cd01d4aef8a94a3960cbfb02c47f`.
Those runs remain historical evidence; they cannot validate a new model by reuse.

Synthetic reproduction found `LLM_PRICE_PER_MTOK=nan:1` accepted a nonfinite
price and produced nonfinite cost with `cost_complete=true`. The old benchmark
success/mode predicate accepted a record despite differing model/code identities.
These are deterministic reproductions, not observed production charges or leaks.

## Changed boundaries

- Rate validation rejects negative/nonfinite values. The existing malformed
  override table fallback remains, with a value-free warning and incomplete
  price status. Arithmetic and aggregate overflow become unknown cost. An
  entirely unpriced or unobserved collection is not a zero/complete bill.
- New usage dictionaries identify `accounting_scope=crew_nodes`, exclusions and
  `end_to_end_cost_complete=false`. Actual status and terminal-backed HTTP
  responses preserve the whole dictionary; real JavaScript displays the scope,
  even beside fully priced nodes. Legacy absent scope stays not recorded.
- `benchmark.py` creates new exclusive batches outside the archive. Identity
  binds selected inputs/repetitions, raw fixture bytes, source files, Git commit,
  lock and actual installed versions, Python/platform, exact provider/model,
  endpoint hash and whitelisted runtime settings. Credentials are never dumped.
- Workers revalidate identity before paid dispatch. Reuse requires matching
  unit identity and intact source/report/score artifacts. Failed, incomplete,
  damaged or mismatched occupied units are refused instead of overwritten or
  automatically retried. `--force` means a new batch, never replacement.
- Summary exports select one batch, reject mixed/corrupt successes and retain
  identity columns. Historical summaries also export to a new directory.
  The CLI's new-spend total excludes reused old usage; the previous code's
  explanatory comment did not actually implement that exclusion.

The legacy `_already_succeeded` predicate remains only as historical mode
inspection, with its existing tests unchanged. It is no longer used by the
paid execution path. Frozen experiments, scoring formulas, labels and the
original calibration records are unchanged.

## Verification and limits

Six original defects were deliberately reintroduced one at a time: nonfinite
rate acceptance, nonfinite aggregate publication, browser scope omission,
worker identity bypass, legacy success reuse, and recounting a skipped bill.
Each caused its target behavioral assertion to fail; every mutation was restored.

Full local verification after the production changes: **2826 passed + 1230
subtests**, **89.09%** coverage across `src`, `api` and `ui` (10979 statements,
1198 missed). Two real Chromium journeys pass: read-only navigation has zero
mutations/external/provider requests; the composer intercepts 23 paid POST
fixtures and three delayed history GETs, with zero API requests reaching its
static server. The archive digest above is unchanged. Latest Ruff, narrow
Pylint and the final release CI are checked separately; test counts are not
report-accuracy or full-invoice accuracy estimates.

These changes do not establish a full auxiliary-request ledger, provider
exactly-once billing, signed/tamper-proof audit storage, or a new accuracy/cost
benchmark. Explicit exclusions do not prove that a stage ran. Live batch reuse
refers to its saved evidence, not fresh web contents. Credentials/contact values
are omitted rather than used as reusable account fingerprints. Historical
readers cannot reconstruct missing execution identities. The frozen fixture
capture command remains separate from immutable assessment batches.

Service receipt recovery, typed market comparisons, native PDF process
isolation and public-startup policy remain separate open work. Production
Tool Calling remains zero-call shadow; no consumed cohort is reopened.
