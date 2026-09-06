# Run mutation intent: stale clicks must not change the operation

Date: 2026-09-06. Base: public main
`f0e6882d54fde1ca4d20cb09343fb0c70f351f05`.
This is zero-provider maintenance verification, not a paid experiment,
observed production data-loss incident or deployment authorization.

## Evidence before the change

The starting full suite passed 2,228 tests and 1,126 subtests. A read-only
census of the existing 109 direct run directories found 67 readable status
records and 42 absent records; the 30 benchmark runs do not have status files.
Among the 67 readable records, 51 had `done=true` without an error and 16
had `done=true` with an error. These are historical status flags, not a
replacement for immutable terminal truth. No retained click/request audit
establishes how often a stale mutation occurred.

Two new HTTP regressions failed against the old implementation:

- A completed fixture received a Cancel-intent request and returned
  `200 / action=deleted`, erasing its report directory.
- A live fixture received a Delete-intent request and returned
  `200 / action=cancelled`, terminating its mocked process.

Both client actions used an unqualified DELETE. The handler tried cancellation
first, then permanent removal when cancellation found no active process.
Consequently a worker finishing between a displayed Running state and a Cancel
click could turn cancellation into deletion. A separate BYOK history catch
invented `failed` after a failed GET and exposed Delete even if the worker
was live. The run view also invented Running before its first progress read,
and treated every non-running state as eligible for deletion.

## Bounded fix

The same route now accepts an optional closed `intent=cancel|delete` enum:

| Request | Contract |
|---|---|
| `DELETE /api/runs/{id}?intent=cancel` | Cancel an active run; a retained but inactive run returns 409 and never falls through to deletion. A missing run remains 404. |
| `DELETE /api/runs/{id}?intent=delete` | Attempt removal directly; the existing locked live-process check returns 409 rather than cancelling it. |
| Invalid explicit intent | 422, not fallback to legacy dispatch. |
| Omitted intent | Legacy cancel-or-delete behaviour remains for existing API clients. |

The shipped browser sends explicit intent for both actions. A preflight GET
was rejected as the solution: a worker can finish after that read too. Intent
must constrain server dispatch, not merely the label on a button.

Initial and unreadable states have no mutation buttons. BYOK history retains
an unavailable entry as Unknown with a bilingual explanation, not Failed.
A later successful read restores the real terminal state and Delete control.
Code-owner/admin authorization and ownerless BYOK capability semantics are
unchanged; intent is an operation constraint, not a new identity.

## Verification at the seams

The implementation passed the full 2,240-test zero-provider suite, latest
Ruff, narrow Pylint and the real Chromium journey. Test totals are a revision
snapshot, not a measurement of production reliability or model accuracy.

- Ten new HTTP/OpenAPI tests cover both conflicts, a worker finishing after
  a successful poll, repeated Cancel, successful explicit operations, invalid
  enum values, missing IDs and owner/admin/ownerless authorization controls.
  They inspect report availability and process termination as well as status.
- Two Node tests import the actual browser request module and capture exact
  URL, method and owner header. Their fetch stub makes no HTTP request.
- Real loopback Chromium holds the first progress response, checks unreadable
  terminal controls, injects one exact-route BYOK history 503, and verifies
  successful reload restores the completed row. Existing rendering, access,
  recovery-affordance and artifact checks remain in the journey.
- Browser audit: zero paid-provider requests, external requests, mutation
  attempts, page errors or unexpected console errors. The two deliberate
  access-check 401s and one history 503 are matched by route and exact count;
  arbitrary errors are not ignored.

Defect re-injection was performed and restored before final verification:

| Reintroduced defect | Test evidence |
|---|---|
| Ignore explicit intent at server dispatch | All four targeted regressions failed. The two primary fixtures again returned the opposite operation; one mocked completion-race fixture instead hit Windows' open-log deletion error, not a clean deletion. |
| Remove both client intent parameters | Both Node request-contract tests failed. |
| Invent Running before the first read | Chromium expected Unknown but read Running. |
| Permit actions for non-terminal unknown state | Chromium expected zero buttons but found Delete. |
| Convert BYOK GET failure to Failed | Chromium could not find the required Unknown history row. |

## Limits and next step

The change does not establish a production incident count, distributed mutation
serialization, all possible cancellation races, provider exactly-once billing
or improved model quality. Legacy unqualified callers retain the original
dual-purpose semantics and must adopt explicit intent to gain this protection.
The browser smoke does not issue mutations; HTTP mutation tests use isolated
fixtures and mocked workers.

No source artifacts, scoring formula, recovery algorithm, paid admission or
Tool Calling experiment was changed. Supplementary retrieval remains zero-call
shadow mode. After CI and separate merge authorization, verify the deployed
OpenAPI enum and shipped client parameters with read-only requests; a paid
canary is unnecessary for this request-contract fix.
