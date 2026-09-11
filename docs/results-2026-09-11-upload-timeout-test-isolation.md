# Upload timeout test phase isolation

Date: 2026-09-11
Base: `fc92960872eaf4efe5e238b80ed521a4a3245c7d` (market audit PR #134).
Status: offline_test_repair / production_behavior_unchanged

PR #134 passed all eight checks. Its main run
[34563198209](https://github.com/shuxiachai/academic-commercialization-agent/actions/runs/34563198209)
then failed only Windows/Python 3.11: the existing upload deadline test expected
the subsequent authentication-boundary probe to return 401, but received 408.
This is retained as a failed observation, not hidden by retrying until green.

The test installed a 20ms timeout for its deliberately stalled request, then
reused that artificial deadline for its capacity-recovery probe. A correctly
bounded second request could time out before authentication under ordinary
scheduler delay. Adding a 50ms inter-chunk delay reproduced the failure for
both idle and total variants locally. The source itself correctly retained its
normal 30s idle / 120s total limits; it was not changed.

The repair scopes only the fault-injection settings with `monkeypatch.context()`.
The first request still must return exactly 408 with `upload_timeout`, and now
also proves its parser files are closed immediately. The second request uses
ordinary limits and still must return exactly 401, not a list of acceptable
statuses. A single parser slot is retained across both phases: leaking one
slot must cause a visible 429 instead of being hidden by the ordinary second
slot. The valid second transfer deliberately takes more than 20ms, making a
deadline-scope regression reproducible rather than dependent on runner speed.

Two defects were separately re-injected after fixing: leaking the short
deadline and suppressing the actual parser-slot decrement. They fail at the
HTTP seam as 408-versus-401 and 429-versus-401. Both files were SHA-256 restored
before complete regression. No assertion was weakened, no skip or warning
ignore was added, and no production timeout, authentication rule, provider
call or paid admission was changed. Final local/CI/deployment facts are recorded
on the follow-up release PR, not inferred from the successful PR #134 jobs.
