# Source-locator observer snapshot (v1)

These three files are byte-for-byte copies (LF line endings) of the files
the 2026-09-19 public source-search comparison used as its observer:

| File | SHA-256 (LF) |
|---|---|
| `tests/js/source_browser_contract.mjs` | `54cbb9a989ce6681ee0fca092441371c44617abdc76a8837d04d92647b928dca` |
| `web/static/js/result.js` | `575b6ba17de6660575369f08d271889e788570059d1823cdfe28f13f773b4650` |
| `web/static/js/i18n.js` | `1010e034767fee6829bcad0bd709cbe7784e7c024db62108e64c482790de958d` |

`report_evidence_source_locator_comparison.py` reads them from here, and
these are the hashes in its `ASSETS` and in
`tests/fixtures/report_evidence_source_locator_comparison.json`. The same
paths under the repository root are the live product files and may change.

Do not edit these copies. They exist so the comparison stays reproducible
without freezing the product UI; see
[the erratum](../../docs/errata-2026-10-22-source-locator-observer-snapshot.md).
