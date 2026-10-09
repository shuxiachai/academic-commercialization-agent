# Reviewer v3: bounded Linux import controls

The [first preparation CI](results-2026-10-09-reviewer-v3-first-preparation-ci.md)
remains failed. One later independently reviewed local control set tested a
new normal-test capability profile under the unchanged Guard, with no model,
credential, production or old-batch execution.

The helper's SHA-256 was
`1d64587acc03b17c5248e06567fe01d8d9638dab42bc3656d18c1242841e77ed`;
the invoker was 130,907 bytes, below its unchanged 131,072-byte limit, with SHA-256
`ad138af039b3b333942b48f7f030efd8fb368f747a55457bd521ede9bed6a26f`.
The bound manifest was
`9c87ac569a4d0a57dd8b1bb4e7ca1fad2b8b8cd9f334ab77218ddddf0fb8ec01`.

## Observed controls

Three fresh bare Ubuntu 24.04 / CPython 3.12.3 processes executed sequentially,
once each. They used the genuine local sysconfig source, 32,768 bytes with SHA-256
`e21755a918f488db1bd21d23120ee36ad09382c553b79735a121ee1fbdbcc08d`.

| Configuration | Retained Guard refusals | Actual child exit | Observation |
| --- | --- | --- | --- |
| Capability plus owned project directory | 0 | 0 | Import, config variables and paths returned; both build-marker probes used owned storage |
| Capability removed | 2 | 1 | Interpreter ancestor and entry probes were refused in genuine `_safe_realpath` |
| Owned override removed | 2 | 1 | `Setup` and `Setup.local` probes were refused in genuine `is_python_build` |

All three preserved runtime executable/prefix identity and restored temporary
function, environment and finder bindings. Real loader code matched the bound
source. The refusal observer reported no fault; output capture completed with
empty stderr, and recorded statuses matched actual process return codes. The
negative controls' nonzero exits are expected failure-detection evidence, not
passing preparation runs. All three control slots are now closed.

The independent static review found no remaining blocking issue before dispatch.
Seventeen synthetic unit tests and full-repository Ruff/narrow Pylint passed.
The updated ordinary suite passed 7,725 tests and 1,709 subtests on Windows
CPython 3.12.9 in 560.69 seconds, with zero failures, errors or skips. It used
a fresh owned configuration and temporary directory; all default tests and
warning rules remained enabled.
The two fixed preparation files still contain the original 529 checks; no
assertion, warning policy, skip, Guard read root or production code was changed.

## Limits and remaining acceptance

These local controls establish the two targeted import dependencies and their
negative detection. They do not identify the remote CI event paths, validate a
CI virtual environment, establish host-realpath equivalence, or prove general
in-process isolation. Approved upstream source candidates are not observations
of installed CI files; unknown source bytes remain rejected.

The launcher used 45-second child/external deadlines and a 60-second outer
deadline. Capture length checks were post-capture, not streaming memory bounds;
an outer timeout would have remained incomplete with physical exit unproven.
No timeout occurred. Raw observations and review records remain private.

New ordinary and four-cell preparation CI must pass at the eventual committed
identity. These controls grant no native Reviewer result, new spending/data
transfer allowance, main merge or production activation.
