# RP native CI follow-up: contain the environment-read guard

Date: 2026-09-17. This is a test-harness correction after the
[native adapter's local validation](results-2026-09-17-relation-policy-qwen-transport.md),
not a provider or production defect claim.

## Observed failure

Commit `bc52c52254cadd01e7a45547cf476f55b83d15ba` passed the local
5,349-test / 1,456-subtest suite. Its
[CI run 35188591079](https://github.com/shuxiachai/academic-commercialization-agent/actions/runs/35188591079)
then failed on Ubuntu Python 3.11 and 3.12 with pytest exit code 3.
Both Windows matrix jobs also failed; the inspected Windows 3.12 log has
the same reporter stack, with shell-reported exit code 1.
The test itself printed PASSED; reporting failed before fixture teardown.

The native-configuration test had installed a process-global replacement for
os.environ to catch accidental ambient key/proxy reads. Pytest's verbose
reporter then called shutil.get_terminal_size, which indexed COLUMNS while
that replacement was still active. The guard raised pytest.fail outside the
test body, producing INTERNALERROR. This is our guard-lifetime defect, not an
Actions outage or evidence that the adapter contacted a paid provider.

The Python 3.12 job ended after 4,194 passed / one existing skipped test /
1,245 subtests. These are interrupted-run counts, not a full-suite pass.
The original local observation, implementation/test hashes and five intentional
mutation results remain in their dated record; they are not rewritten as CI
success. This follow-up changes only the new test file and current documentation.
The runtime adapter and all older frozen experiments stay byte-identical.

## Correction and verification

The guard now uses a nested monkeypatch context whose lifetime encloses
construction, intercepted HTTP, transport-option checks and journal checks,
then ends before pytest reporting. There is no terminal-variable whitelist.
The existing get/index prohibitions remain; environment enumeration is also
rejected. Restoration checks exercise shutil.get_terminal_size before fixture
teardown, using invented terminal dimensions and comparing object IDs rather
than risking the contents of the real environment in an assertion failure.

Six added cases inject get/index/items reads during either the real constructor
or the intercepted HTTP handler. They require the original strict failure,
zero or one intercepted requests respectively, restoration even on exception,
and a successful terminal query afterwards. The author checked that all 209
original assertions and 38 original test functions/parameterizations remain;
37 other function bodies are unchanged.

The local verbose reproduction stopped after 85 passed, with PASSED followed by
the same reporter INTERNALERROR. An initial unrelated test setup failed on a
pre-existing temporary-directory ACL; using a fresh directory avoided it
without changing permissions, skips or warnings.

One actual mutation replaced scoped.setattr with the outer fixture's
monkeypatch.setattr. A temporary diagnostic plugin restored the environment
only after the test call ended, preventing a reporter crash from hiding the
test's own terminal-query assertion. The fixed control passed seven selected
tests with zero plugin restorations. The mutant failed all seven at the
COLUMNS read, with seven plugin restorations and pytest exit 1. Valid
downstream HTTP replies remained configured. After exact restoration, the
normal verbose suite without that plugin passed all 160 tests in 3.41s.

Restored test SHA-256:
`9d9ff1a49664523e58cb010800fca4abe40f195a1a6d55a1e77aeff51a177b02`.
The adapter remains
`9b1a79953efacc1c4d5516d98430e25be545a8be87fd8c4cc5bbb1fe26463d53`.
The six new cases are included in the focused and full-suite counts, not
additional successes to add to those denominators.

The full zero-provider suite passed 5,355 tests / 1,462 subtests in 289.12s.
Repository-wide Ruff 0.16.8 and the prescribed narrow Pylint passed.
All 134 pre-adapter frozen files and the seven closed PCQ artifacts were
rechecked unchanged after this repair. No assertion, warning policy or CI
command was relaxed.

A different requested route_reviewer / gpt-6-astra / high context found no
actionable issue in the scoped guard, normal and exceptional restoration
seams, preserved assertions or the failure/mutation disclosure. That review
was static: execution and mutation observations came from the repair expert
and parent, not an independent re-execution; backend model metadata is
unavailable. Exact-head remote outcomes are recorded on PR153 after pushing,
not inferred from these local successes.

## Limits

The same strict no-ambient-read assertion must remain active throughout adapter
construction and intercepted HTTP. Restoring the real mapping before reporting
does not permit the adapter to obtain credentials from it. No COLUMNS exception,
warning ignore, skip or production-code workaround is acceptable.

A successful repair only restores reliable test isolation. It does not validate
Qwen semantics, reopen a paid allowance, activate production Tool Calling, or
authorize merging PR153. Exact-head CI remains a separate release gate.
