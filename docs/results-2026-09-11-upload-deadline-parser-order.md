# Order deadline injection after actual multipart file creation

Date: 2026-09-11
Base: `6d127eb5a41e43db73d66edbb0fb49dff419ee6f` (PR #136).
Status: offline_test_repair / production_behavior_unchanged.

PR #136 and its main CI both passed all eight jobs. A subsequent local merged-tree
run nevertheless returned **one failed, 3044 passed, 1253 subtests**: the idle
upload test reached `assert ingress` with no created parser files. The green CI
does not erase that contrary observation. No paid provider request was involved.

The [previous repair](results-2026-09-11-upload-timeout-test-isolation.md) scoped
the artificial deadline away from the second authentication/capacity probe. It
did not guarantee that the first request opened a file before the injected 20ms
deadline. A 50ms delay before its first body chunk reproduced the empty-file
assertion for both idle and total variants. Production correctly rejected an
unfinished upload; the test was asserting cleanup before setup had happened.

The test now keeps that 50ms delay as a regression control and orders fault
activation after the real multipart parser opens a tracked file:

- A module-local clock proxy advances beyond the unchanged total deadline only
  after file creation. Total expiry must reject before another wait call.
- A module-local receive-wait proxy records the actual production timeout
  argument. The first read has a generous test watchdog; only the post-open
  idle wait gets a short real `asyncio.wait_for` timeout. Cancellation of the
  stalled body is explicitly observed.
- All module-local proxies end before the normal slow upload. No global event
  loop clock or asyncio function is replaced. Exact 408/error-code, opened and
  closed files, expected wait sequence, idle cancellation and subsequent 401
  assertions remain. One parser slot still exposes leakage as 429.

Five separate defects were re-injected: premature first-read timeout, ignored
total deadline, wrong idle timeout selection, leaked parser slot, and bypassed
multipart cleanup exception type. Each failed its target, including the real
file-closed teardown for the cleanup defect. Both source/test files were restored
by SHA-256 before final validation. No skip, accepted-status alternatives,
warning ignore or production timeout/auth/admission change was introduced.

This is an HTTP/parser lifecycle and timeout-selection test, not a wall-clock
load benchmark or a live 30s/120s timeout experiment. The five-second watchdog
only bounds a broken test. Final full-suite, CI and deployment observations
belong to the follow-up release PR; the failed local observation is retained.
