# Reviewer v3: qualified Windows preparation validation

Two fresh offline default-entry runs passed on 2026-10-09. They validate the
isolated preparation machinery on the two exact Windows runtimes below, not
Reviewer model behavior or the effectiveness of either instruction arm.

| Observation | CPython 3.11.9 | CPython 3.12.9 |
| --- | --- | --- |
| Unique tests | 529 | 529 |
| Passing setup/call/teardown phases | 1,587 | 1,587 |
| Inherited / common-contract / new-v3 tests | 278 / 35 / 216 | 278 / 35 / 216 |
| Cumulative refusals | 0 | 0 |
| Actual child exit / parent exit | 0 / 0 | 0 / 0 |
| Both output streams reached EOF | Yes | Yes |
| Timeout / termination | Neither | Neither |

The tested working-tree snapshot was on `codex/prepare-reviewer-comparison-v3`,
based on commit `9acdf13d23b051435c721d3727473e5b00800e9c`. The preparation was
uncommitted; that base commit alone does not identify the tested files.
The invoker SHA-256 was
`84eb1cfc4e49e0234dd4ffd305920edbd7a49133e5ef05da4de89138e55e4321`;
the manifest SHA-256 was
`ba8c9b52cfc349ccc4308d9526d4fac5915691707ebabcc9798cd8f2f9b3c37a`.
These observations do not transfer automatically to a later source/manifest
identity. Raw receipts and diagnostic packets remain private and uncommitted.

## Preserved failures and scope

The original complete 3.11 invocation remains failed: its 529 assertions passed,
but four read-range refusals remained and the actual child exited 87. The later
H6 and first-observer-fault diagnostic failures also remain closed non-passes.
No old case was replayed or retrospectively relabelled by these two successes.
The original four events lacked path/stack witnesses; fresh controls cannot
prove the exact origin of every historical event.

The passes cover the default entry, including process exit and final receipt
acceptance. They do not imply diagnostic marker counts, a successful historical
H6 case, all-descendant termination, Linux compatibility, remote CI, or native
provider obedience. Separate targeted checks and the negative observer-integrity
control are supporting evidence, not additions to the 529-test denominator.

## Remaining delivery gates

Independent delivery review identified a Linux-specific gap: the owned distro
configuration was selected only on Windows. Linux would otherwise probe host
OS-release paths during the real dependency import. This is a static finding;
the finding preceded Linux execution. A minimal owned-profile correction and
fresh validation must preserve the guard, cold-child filtering and all fixed
assertions instead of allowing host configuration reads.

The independently reviewed correction changed only normal-profile platform
admission and physical-directory checking. Its invoker SHA-256 is
`0eb6e775cb0c2412595cf45dbb29f70caea29c94ed6e1bebecf260b5111d9075`.
All 27 targeted distro tests passed on Windows CPython 3.12.9. A separate
Ubuntu 24.04 / CPython 3.12.3 cold-import control used the same frozen script:
the owned-directory case exited zero with no refusals; removing both environment
keys exited one with exactly two cumulative read-range refusals. Both were
fresh cases, each limited to 30 seconds internally and 45 seconds externally.
The expected negative exit is sensitivity evidence, not a passing unisolated
import. This narrow dependency check does not establish the full Linux gate.

The final preparation commit still needs independent review and all eight
ordinary CI checks plus the four Reviewer preparation cells at the same SHA.
The preparation stays outside `main`; credential preflight and the actual
Reviewer experiment remain unrun. The protocol's request/cost ceilings do not
grant a new paid allowance, private-data transfer or production activation.
