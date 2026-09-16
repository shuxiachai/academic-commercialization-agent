# CQ catalog-native synthetic Qwen result

Observed: 2026-09-16. Protocol: [pre-registered CQ contract](prereg-2026-09-16-report-evidence-catalog-qwen-canary.md).

## Outcome and scope

**Both frozen synthetic cases passed their mechanical gates in one batch:
four sequential requests, no retries, no unknown usage and no later batch.**
CQ01 performed an actual sixth-source read and returned a strict final answer
citing its issued receipt in the same conversation. CQ02 actually read its
missing-text source, then abstained without an evidence ID. This is the first
successful native read-to-final observation for this separate catalog path,
not a reinterpretation of FQ, SQ, JQ or sealed retrieval failures.

The fixtures deliberately name easy target subjects and place them sixth among
six invented entries. Two cases are not selection accuracy, independent semantic
validation, realistic retrieval quality, user value or production readiness.
Production remains zero-call shadow; there is no follow-up API/browser route.

## Identity and authority

- Starting main: `3bd02fc5badbc25ccf873a49ce8c04b53c681d6c`.
- Protocol/fixture first commit: `93c02e8efc109b100aea987d83ce44f51a04f689`.
- Pre-live usage clarification: `3b48843`, appended before any CQ request.
- Exact executed implementation: `264135740adca474837066eb8be2f56d98fe7725`.
- Fixture SHA-256: `f0426492e137c33214fc6db7063b89f790f4d19ee416b07eeebff0014313b60c`.
- Configuration SHA-256: `c03576deb854ebed820212942e738b2bc20405bb9b73dfe6eb917f437b9dfcac`.
- Default identity-only mode verified 19 fixed paths, committed/disk bytes and
  installed dependency versions, without reading a key or creating output.
  Runtime Python was 3.12.9; versions do not attest installed package bytes.

The user's standing equivalent low-cost synthetic approval was narrowed to
four requests and USD 0.10, with first failure stopping later cases. Separate
experiment/identity/authorization records were published before dispatch.
The adapter manifest still says offline contract/no live authorization; it was
not silently rewritten into a grant. A CLI acknowledgement is not independent
consent verification. Old batch allowances were not reused.

Only the dedicated DashScope credential entered the invocation process, through
the existing dedicated assignment when needed. No durable environment or .env
change, other-provider key fallback, raw key output or real user text occurred.
The invocation reported its process credential restored. The model and
destination stayed exact `qwen3.5-plus` and the frozen official Beijing endpoint;
a matching response model string is not backend version attestation.

## Request-level observations

| Request | Case and stage | Input tokens | Output tokens | Estimated USD |
|---|---|---:|---:|---:|
| 1 | CQ01, visible-ID native read | 900 | 53 | 0.000698020 |
| 2 | CQ01, paired read result then final JSON | 1013 | 104 | 0.000938209 |
| 3 | CQ02, visible-ID native read | 880 | 53 | 0.000686560 |
| 4 | CQ02, paired missing_text then final JSON | 631 | 45 | 0.000516363 |
| Total | One batch, four requests | 3424 | 255 | 0.002839152 |

Reported total usage is 3679 tokens. All four replies were observed, accepted,
model-matched and usage-complete. Budget consumption was USD 0.044597248 because
the conservative reservation remains charged for each request; the smaller
usage estimate is not an invoice or spend refund. Exactly four requests used
the full call allowance; budget consumption stayed below USD 0.10. No fifth
request was made.

Initial requests exposed only the six visible read IDs with auto. Each final
request preserved its native assistant call and paired local tool result, used
none, omitted tools and requested JSON Object. CQ01 delivered the complete A6
saved text and its real receipt. CQ02 delivered M6 missing_text and had no
successful-read receipt. Final results remained `semantic_support=not_assessed`
and `answer_verification=not_verified`; strict JSON is not semantic proof.

A separate narrow AI inspection found CQ01 repeated the saved 24 kHz at 60%
relative humidity and both limitations: no outdoor deployment or long-term
stability study. CQ02 declined to establish annual revenue from unavailable
text. This inspection was not human review, an independent held-out evaluation
or a general entailment audit, and it did not modify mechanical gates.

## Offline checks and review before execution

Starting suite: 4098 tests / 1370 subtests, 128.87 seconds. Final implementation
suite: **4261 tests / 1376 subtests, 166.50 seconds**. The 163 new controls and
538-test direct-dependency run are overlapping subsets, not extra totals.
Current Ruff 0.16.7, narrow Pylint and offline lock checks passed.

A fixture capacity probe used the real wrapper and adapter with fake keys and
intercepted HTTP: CQ01 bodies were 3148/3926 bytes, CQ02 3059/3174 bytes, and all
four actual body hashes matched reservations. This was not provider inference.
The first probe incorrectly expected enum answered instead of the existing
answered_with_evidence; correcting the measuring script changed no product
contract. One UP031 lint issue was fixed; no assertions/skips were relaxed.

Independent read-only AI protocol review caught an accounting overclaim:
non-200 replies are rejected before their bodies are parsed. The appended
clarification preserves only actually parsed valid usage; unreadable usage stays
unknown with its reservation and stops the batch. The new HTTP500-with-usage
control proves that boundary without changing the frozen primitive.

Independent read-only AI implementation review found no remaining actionable
issue on the reviewed hashes. The parent then removed the new first-failure
stop/break: the HTTP-seam test failed with **two requests instead of one**.
After finally restoring the exact source hash, all 163 new tests passed again
in 31.49 seconds. All 98 protected historical files were unchanged. This
expected defect-injection failure is not a failed paid run.

The reviewed runner SHA-256 was
`02674d47f0f8f58e51dc0883d8398db0674454f4637a4f1c29e5677631158194`;
CLI `18591e029e988851cba0ee19f8a47cb4c2c958a0f5f8059cc7c4ff6873200706`;
tests `978ae6ba05efa558274eb6afb7a7a6225e038c50c64168ca7ff7e165751c06e5`.
Role configuration is not backend model metadata or hard sandbox proof.

After recording the live result, the complete zero-provider suite passed again:
**4261 tests / 1381 subtests, 165.38 seconds**. The additional subtests are
documentation-link checks, not new model observations. A separate read-only AI
artifact audit matched the four usage records, native read/result pairs and all
eight hashes below; its documentation review found no remaining actionable
claim issue. Operator environment restoration and test execution facts come
from parent command records, not from inference from the run artifacts.

## Local evidence hashes

Raw synthetic traces remain local; only qualified aggregates and SHA-256
identities are published. No reviewer records, private run links or credentials
are included.

| Artifact | SHA-256 |
|---|---|
| authorization.json | 3252f2d3d06fa594d05f469b7c00e5bae688dc97a8e015965ec3778096ac8ee7 |
| CQ01.json | ac16f974b93715a5435cf30bfd7cf9d50b5146b032bfd94b3e421bedea218388 |
| CQ02.json | ce1fada03f4ae8b7524f9bddc5b3e775cf6f04da1761b2ca3e812d71a2a36558 |
| events.jsonl | 5c57034785e770086776c2121c84211bc85798798176b8a239c06d8c19056dd5 |
| experiment_manifest.json | 4de19ba3a3d14edda48f16a920789f8156cf01694b21c1e0f7391168b72a4464 |
| identity.json | c28fdf0c0ecd8e302861315d2af9beefe72ba42ee9398d2dd0172727b7c5987f |
| manifest.json | b49ee9fa88449cf958190e5deb0058b53779407f6601fce7fbe7cf5549a5e46f |
| summary.json | e88261d1d169efc9680d3d1081a4d99102c5b40adf85dbed189159e37df7d1a3 |

The batch is closed. Further work should test one bounded real saved-report
task under a NEW protocol and privacy authorization, not replay CQ until it
looks stable. Production additionally needs ownership/admission, accounting,
receipts, safe diagnostics and a user-visible failure contract. No search
planner or other provider is authorized by this result.
