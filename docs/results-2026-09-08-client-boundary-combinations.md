# Fractional scores, paid identity and stale progress reads

Date: 2026-09-08. Base: `207670addc16b59c65026f1ddcabed3d172b02a0`.
This corrects a display regression and synthetic client-boundary failures.
It is not a new paid experiment or a general security/accuracy certification.

## Evidence before changing code

The unchanged baseline passed 2,499 tests and 1,191 subtests. A bounded,
read-only inventory of existing timestamped and benchmark outputs found 109
readable score files, 64 with at least one fractional dimension: TRL 45, MRL
30, patent 33, market 51 and evidence 34. These counts overlap. They identify
stored reports affected by the display rule, not 64 observed online incidents.

The preceding maintenance mistakenly required dimension integers. Actual
normalization exports fractions (including 8.5 and 3.5), so an integer-only
positive test missed legitimate values hidden as dashes. Zero also passed the
old display range despite the dimension contract starting at one.

Fake-fetch replays reproduced corrupt stored BYOK objects, arrays and strings
omitting the credential fields while retaining an access-code header. With a
valid operator code this can change the payer; without authorization the server
still rejects it. A delayed identity-A PDF reply also attached to identity B's
next request after same-page logout. Three failed polls after a running response
produced no connection-loss notification. These failures were synthesized, not
claims about observed production charges or an authorization bypass.

## Contracts now enforced

- Dimension values are finite numbers in **1..dimension maximum**, including
  fractions; the overall score remains 0..100. Invalid dimensions have visible
  local explanations and dashes without hiding valid neighbours. No formula,
  weight, confidence floor, saved score or frozen calibration changes.
- Only an absent BYOK storage entry means no BYOK. Invalid JSON, JSON null,
  wrong shapes, unknown providers and missing/non-string/blank keys block run,
  resume and PDF requests before fetch. Boot asks for an explicit credential
  choice even when an access code remains. Setters reject malformed credentials
  without clearing the existing payer; explicit code login can clear BYOK.
  This is local shape validation, not verification that a supplier accepts a key.
- Logout waits for outstanding run/resume/PDF acknowledgements. Aborting fetch
  would not cancel a paid provider request and dropping a response could lose
  its only run capability. Once settled, logout clears attachment, topic and
  decision context before reload or same-page gate entry. Gate submission cannot
  switch identity while a code check is pending or after its gate has finished.
- The progress GET has a 15-second deadline through body consumption. A failed
  read shows an independent connection warning and stops elapsed extrapolation;
  it does not change the worker state or create a failed run. A successful poll
  clears the warning and re-anchors time. No initial observation is distinct
  from a stale prior observation; 404 stops polling with a distinct message.
  Existing cursor and read-backoff rules remain. No paid POST gets this timeout.

## Verification and limits

Final local Windows / Python 3.12.9 verification: **2,619 passed + 1,196
subtests**, fresh coverage **88.89%**. Latest Ruff, the narrow CONTRIBUTING
Pylint command and both Chromium journeys passed. This adds 120 tests; document
link subtests are separate. Committed-tree CI supplies platform-specific counts.

The regression suite exercises stored files through HTTP into the actual score
renderer, all three paid client entrypoints with absent/valid/corrupt credentials,
the API/browser provider allowlist seam, delayed acknowledgements across identity
changes, stalled headers/body reads, first-read failure, recovery, 404 and stop.
Real Chromium additionally sees the gate rejection, all three pending-operation
logout guards, A-to-B attachment isolation and a visible stale/healthy transition.
Its 12 POSTs are intercepted fixtures: none reaches the static-only server or a
provider. The independent read-only browser journey remains zero-mutation.

Seven original/related defects are reinjected individually: integer-only scores,
corrupt BYOK fallback, pending-payer clearing, old attachment retention, silent
poll failures, a warning that never clears, and loss of the bounded read deadline.
Each test must fail at the relevant assertion and every source hash is restored.
The final local and CI runs determine committed-tree counts; the unchanged
coverage floor remains 85%, and no warning filter or skip is loosened.

These controls belong to one document/tab. They do not revoke capability links,
purge inaccessible storage, coordinate other tabs, guarantee server/provider
idempotency, or stop work when a tab closes. A paid acknowledgement that never
settles keeps logout guarded; closing the tab risks losing that acknowledgement
and is not cancellation. Browser timer throttling can delay the read deadline.
Other GETs and arbitrary hostile/corrupt payloads are not comprehensively bounded.
Production Tool Calling remains zero-call shadow mode; no new source/model calls,
reserved cohort access, Railway restart or paid canary occurred in this audit.
