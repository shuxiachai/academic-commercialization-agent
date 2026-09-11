# PDF identity, signed quantities and thread-owned failure receipts

Date: 2026-09-11. Starting main: `e02677b36c07048d0e53366c6da138def88bfe90`.
Scope: offline repair and release verification; zero paid provider calls.

## Confirmed defects and adopted boundaries

1. A bibliography DOI was labelled unverified but still populated A1's DOI/URL.
   New extraction retains `candidate_doi` / `candidate_url` separately; code owns
   these fields, not model JSON. Neither candidate nor legacy locators enter
   citation identity. A1 keeps its actual uploaded summary/title and synthetic
   upload identifier, with no DOI-resolution call. This also applies to old
   extractions at conversion, not an in-place rewrite of saved reports. The
   synthetic identifier is not a registered DOI or manuscript verification.
2. Numeric extraction lost signs and lowercased milli/mega symbols together.
   ASCII +/- and Unicode minus survive comparison. mW/MW, mWh/MWh, mPa/MPa
   and mHz/MHz remain distinct. Unknown unit/compound notation on a distinctive
   figure yields explicit unverifiable rather than a pass or accusation.
   Other unsupported case spellings (mM versus mm, Mw versus MW), Greek and
   Chinese suffixes also abstain instead of becoming a unitless value.
   Ordinary count/year exclusions and precision-aware decimal rounding remain.
   This is a narrow advisory grammar, not dimensional conversion, full unit
   support, claim entailment or a blocking guardrail.
3. Only a live HTTP waiter recorded extraction failures. A disconnected waiter
   left the already-failed background thread's receipt pending. The actual PDF
   thread now records known provider/parser, quota/capacity, accounting-admission
   and publication failures, including local 5xx. The same safe detail/category
   can be observed via GET and replay; failure never means free/refunded.
   A failed receipt commit itself remains unavailable/unresolved, not fabricated
   failure. Successful metadata survives a lost commit; unresolved intent cannot
   launch another extraction. Existing queued-abandonment and raw cleanup remain.

Local recovery identity now includes the PDF and grounding implementations.
Protected score computation, frozen experiment sources and zero-call production
Tool Calling remain unchanged. Candidate fields reach both the initial HTTP
reply and receipt recovery, not only an internal model.

## Measure before and after

The unchanged starting suite passed **2884 tests + 1237 subtests**. Thirty new
offline boundary cases initially produced **26 failures and four passes**.
No real model, search or DOI request was used to reproduce them.

Read-only replay of **90 archived evidence files / 30 benchmark runs**:

| Numeric-screen outcome | Before | After |
|---|---:|---:|
| Checked findings | 50 | 32 |
| Ungrounded findings (subset of checked) | 1 | 0 |
| Unverifiable findings | 161 | 179 |

The 18 moved findings use unsupported unit notation such as eV, GJ/tCO2, dB
and cm². The removed warning moved to unverifiable, not to grounded. These
figures document reduced asserted coverage, not improved independent accuracy.
A tentative expansion making every citation count checkable created three
unsupported warnings on old reports; it was rejected. Small counts retain their
old exclusion. Archived evidence, calibration CSVs and scorecards were not changed.

## Verification and limits

Tests use real PDF extraction with an offline model substitute, HTTP delivery,
persisted metadata, A1 conversion, actual cancellation of a waiting coroutine
while its thread is held, and read-only receipt lookup after thread completion.
Positive controls retain correct sign/unit pairs and already-passing receipt
commit-loss behavior. Local source identity is tested by changing read bytes.

Eleven defect variants were deliberately injected and required the named test
assertion to fail, then restored with matching source SHA-256: candidate DOI
assignment, candidate A1 attachment, omitted HTTP fields, lost sign, collapsed
milli/mega symbols, unknown suffix as unitless, missing background failure
commit, commit uncertainty as false failure, PDF/grounding omitted from local
revision (two variants), and unsupported symbol case folding. Unit variants
were repeated after the final Unicode/SI refinement.

Release CI, mutation evidence and deployment verification are recorded on the
release PR. Real Chromium tests intercept paid POSTs or reject mutations.
No paid canary or manual Railway restart is part of this maintenance.

Final Windows/Python 3.12.9 regression: **2922 passed + 1242 subtests**,
**89.18% Python coverage** (85% floor unchanged); 38 added cases. Latest Ruff,
narrow Pylint and whitespace checks pass. Both Chromium journeys pass: 26
intercepted composer POSTs, zero provider calls, unexpected requests or page
errors; the read-only result journey also records zero mutation attempts.

Native PDF subprocess isolation, end-to-end billing, independently verified
manuscript identity and general citation correctness are not established here.
Hard process death or unavailable storage can still leave unresolved receipts;
an in-flight provider request can have spent money even when delivery fails.
