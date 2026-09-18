# Read-first saved-evidence candidate: offline engineering

Date: 2026-09-18. Preparation was committed at
`910e3d0fbafe83f4b0d1a56ed6b3a4fb999dfb3e` before implementation.
[Protocol and frozen references](prereg-2026-09-18-read-first-followup.md).

## Implemented boundary, not production capability

The new native adapter requires a named `read_source` call for the sole
visible source and advertises exactly offset 0 / length 1500. An early final,
wrong source, malformed/partial call or refusal cannot enter the actual reader
or purchase a second request. No source uses final-only JSON. Missing saved
text and whitespace remain distinct from usable text that cannot settle a claim.

The frozen RP callback still advertises auto; a separately recorded native
transformation makes the forced choice. Callback entry, local read, reservation,
observed response and semantic support are not interchangeable. This is
controlled execution, not autonomous tool selection or source discovery.
The scope is zero/one saved source of at most 1500 Unicode code points;
larger inputs are out of scope, never silently reduced or called unavailable.

The original relation policy, parser, reader, HTTP primitive and accounting
limits are reused without changing their frozen files. The two new modules own
only native admission/audits and the fixed RF executor. Default module CLI
checks committed identity without loading dotenv, reading credentials, creating
the batch directory or sending HTTP. Future native use is one fresh fixed-output
batch, at most six requests / USD 0.10, with first-failure stopping. Independent
review and exact-commit CI remain gates, not facts supplied by a CLI flag.

## Evidence and faults caught

The clean pre-integration suite passed 5531 tests / 1504 subtests in 337.81s.
The PR153/showcase integration passed 5531 / 1510 in 323.62s. Its eight CI
checks passed before merge `915381725f01e1c3b42b25f24cbcbf8956831564`;
the merged tree matched the tested tree. That archival merge did not enable
Tool Calling.

The first candidate passed 86 focused tests and a complete local suite
(5617 tests / 1512 subtests, 332.86s), latest Ruff and narrow Pylint. A separate
read-only reviewer nevertheless found two gaps: availability summarized inner
delivery without identifying a later RP budget refusal, and an error-path
identity test could pass without observing its post-call check. A passing suite
was not evidence that those boundaries were protected.

The repaired summary separates actual read executions, inner delivery,
policy-callback delivery and native intent/response. Reservation is explicitly
not provider evidence receipt. The identity regression checks the exact order,
third check and retained usage on a rejected response. A new subprocess control
checks default CLI isolation; its Git/version boundary is still a fixture,
not an attestation of the real executing commit.

After repair, 90 focused tests passed in 12.16s, with focused latest Ruff and
narrow Pylint. These tests run the real wrapper, reader and adapter through
intercepted HTTP with fake credentials, not a model or live transport.

Author-executed deliberate mutations supplied otherwise valid downstream
responses and then restored exact source bytes:

| Removed boundary | Observed negative control |
|---|---|
| Named wire choice restored to auto | 6 failures, 1 retained positive control |
| First complete-read admission removed | 11 failures, 1 retained positive control |
| Complete tool-result comparison removed | 2 failures; a separate dispatch-first assertion observed 2 HTTP entries instead of 1 |
| Inner receipts misreported as RP delivery | 1 failure at the policy-expansion budget seam |
| Reservation misreported as received response | 1 failure in a failed-case summary |
| Post-identity check limited to successful calls | 1 failure: 2 checks instead of 3 after a rejected model reply |

The parent independently checked the repaired transport and runner hashes:
`c656ccdd3bfbbc360c3266a73b7b2c388ebf2de9cb255bafc73b2473c60ea54f` and
`0284cf1350ffca554afce5489bef525a693b46999c445d4722919a9b202727f9`.
These hashes describe this repair observation, not an alternative live grant.

An initial focused attempt had 60 temporary-directory setup errors before any
test body; a fresh writable workspace temp root resolved it. One UP031 lint
finding was fixed without relaxing rules. A preparation documentation test also
caught the missing archive link; adding it restored the unchanged assertion.
No warning filter, skip, acceptance threshold or old label was loosened.

## Limits and remaining gates

Final repaired-tree full regression, separate targeted re-review and exact-head
CI are required before dispatch; their outcomes travel with the implementation
commit/PR. The local counts above are different observations, not additive
coverage or a speed benchmark. Static review is not an independent test rerun.

RF references are context-limited, label-blinded LLM judgments of three
dependent fictional controls, not human gold or unseen accuracy. No RF native
response, real-report judgment or production admission is established by this
offline record. Closed RPQ/PCQ/CLQ outputs remain unchanged. No old batch,
private report, production endpoint, scoring formula or access boundary is
reopened.

## Final pre-native validation

The repaired full local suite passed 5621 tests and 1517 subtests in 443.95s.
Repository-wide latest Ruff and prescribed narrow Pylint passed. A separate
targeted read-only re-review closed both P2 findings without executing tests.
The real committed default CLI then verified commit `41d67f5` and the frozen
fixture without creating a batch directory; this is separate from its mocked
Git/version subprocess regression. All eight exact-head checks passed in
[CI35314037507](https://github.com/shuxiachai/academic-commercialization-agent/actions/runs/35314037507)
before the subsequently [failed native batch](results-2026-09-18-read-first-qwen-canary.md).
No green engineering check was promoted to a passing semantic observation.
