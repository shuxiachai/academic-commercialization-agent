# Reviewer v3: complete preparation matrix, separate ordinary failure

At commit `180fc64ed62d29c3bcaffe00f6f2b59d87869ead`, the
[second preparation workflow](https://github.com/shuxiachai/academic-commercialization-agent/actions/runs/37926892457)
passed all four cells. This new result does not relabel the
[first failed preparation run](results-2026-10-09-reviewer-v3-first-preparation-ci.md).

| Actual runtime | Assertions | Retained refusals | Pytest / wrapper status |
| --- | --- | --- | --- |
| Windows / CPython 3.11.9 | 529 passed | 0 | 0 / 0 |
| Windows / CPython 3.12.10 | 529 passed | 0 | 0 / 0 |
| Ubuntu / CPython 3.11.17 | 529 passed | 0 | 0 / 0 |
| Ubuntu / CPython 3.12.3 | 529 passed | 0 | 0 / 0 |

Every cell retained the 278 inherited, 35 common-contract and 216 new-v3 checks.
All four jobs completed successfully, with invoker SHA-256
`ad138af039b3b333942b48f7f030efd8fb368f747a55457bd521ede9bed6a26f`
and manifest SHA-256
`9c87ac569a4d0a57dd8b1bb4e7ca1fad2b8b8cd9f334ab77218ddddf0fb8ec01`.

The Linux receipts observed actual loader-code validation, one optional
resolution decline, completed import, restored function/environment/finder
bindings and no profile fault. Python 3.11.17 used the 30,315-byte upstream
candidate with SHA-256
`c16887bf792dc21f27fe5d2ca4ee271f131b7f6a88593def43be52cfbc846759`;
Python 3.12.3 used the 32,768-byte Ubuntu source with SHA-256
`e21755a918f488db1bd21d23120ee36ad09382c553b79735a121ee1fbdbcc08d`.
This observes the new profile in those CI virtual environments. It does not
reconstruct the individual denied paths from the first failed run.

## Ordinary regression remains a separate gate

The same commit's [ordinary workflow](https://github.com/shuxiachai/academic-commercialization-agent/actions/runs/37926892454)
failed in Ubuntu/Python 3.11 with seven failures in two synthetic diagnostic
test files. Those fixtures supplied Windows-specific diagnostic configuration
and intercepted the existing runtime dependencies, but omitted the newly added
Linux-profile import. In an ordinary Linux pytest process, the real helper
correctly rejected the already imported sysconfig module before the fixtures'
intended prepare/observer boundary. The seven failures remain recorded.

The follow-up correction is confined to the fixtures' exact dependency-import
interceptors and verifies entry/exit ordering. It retains their original
prepare, refusal, observer and stop assertions. It does not make a warm Linux
import acceptable, alter the real helper or Guard, or replay the three closed
local controls. The reinjection regression checks the actual boundary events
without depending on whether its host pytest process has cached sysconfig.

The current commit's ordinary and preparation checks must both pass; see
[Draft PR 194](https://github.com/shuxiachai/academic-commercialization-agent/pull/194)
for its current head and checks. A green preparation matrix alone does not
authorize the native Reviewer experiment, establish semantic gain, or permit
a main merge or production use.
