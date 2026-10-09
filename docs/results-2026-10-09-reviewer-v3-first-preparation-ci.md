# Reviewer v3: first remote preparation CI failed

The first remote preparation observation tested commit
`0805cf21c572cd616fca8eb4c47f89582642387e` in
[draft PR 194](https://github.com/shuxiachai/academic-commercialization-agent/pull/194).
The preparation remains outside main. No actual Reviewer model request followed.

## Separate ordinary and preparation results

All eight checks in the [ordinary workflow](https://github.com/shuxiachai/academic-commercialization-agent/actions/runs/37916935808)
passed. Each Python matrix cell reported 7,707 tests and 1,676 subtests passed,
with one existing baseline-report check skipped. That check needs complete local
benchmark reports, which are not published to hosted CI; it ran in the local
suite, which passed 7,708 tests and 1,706 subtests with no skips. Canonical
Ubuntu/Python 3.12 coverage was 90.70%, above the unchanged 85% floor.
No new skip or warning ignore was added.

The separate [preparation workflow](https://github.com/shuxiachai/academic-commercialization-agent/actions/runs/37916936024)
failed overall:

| Actual runtime | Assertions | Cumulative read-range refusals | Wrapper status | Outcome |
| --- | --- | --- | --- | --- |
| Windows / CPython 3.11.9 | 529 passed | 0 | 0 | Passed |
| Windows / CPython 3.12.10 | 529 passed | 0 | 0 | Passed |
| Ubuntu / CPython 3.11.17 | 529 passed | 4 | 1 | Failed; actual exit 87 |
| Ubuntu / CPython 3.12.3 | 529 passed | 4 | 1 | Failed; actual exit 87 |

Every cell retained the 278 inherited, 35 common-contract and 216 new-v3 test
census. The assertion totals do not override isolation refusals or actual exit.
This first run and its two failed cells remain failed; no retry reclassifies them.

## One fresh local prefix observation

An independently reviewed, single-use local baseline used Ubuntu 24.04's bare
CPython 3.12.3 with the original Guard and three fixed stages. It loaded no SDK
and did not enter pytest or an experiment runner. Its sysconfig source was
32,768 bytes with SHA-256
`e21755a918f488db1bd21d23120ee36ad09382c553b79735a121ee1fbdbcc08d`.

Cold `sysconfig` import produced four retained refusals: two during interpreter
path resolution through the authentic `_safe_realpath`, and two while probing
`Modules/Setup` and `Modules/Setup.local`. The subsequent `get_config_vars()` and
`get_paths()` stages added none. All three stages returned, observed sysconfig
code matched the bound source, and the observer reported no fault or saturation.
The process returned one with disposition `refusals_observed`; this is diagnostic
evidence, not preparation acceptance. Raw observations remain private.

The bare local interpreter is different from the CI virtual environments, and
the CI sysconfig bytes and individual event paths were not captured. Matching
four refusals does not establish a one-to-one mapping to either remote cell,
or to the older Windows four-refusal failure. Those historical results and
closed diagnostic cases remain unchanged.

Any successor must address both the early path-resolution probes and the later
build markers without widening the Guard or moving the rejected operations
before it. A new reviewed source identity and fresh observations are required;
this failed workflow grants no native execution, private-data publication,
main merge or production authority.
