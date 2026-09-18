# RF native result: the read completed, but the claim relation failed

Date: 2026-09-18. Executing commit:
`41d67f5f5216d07dfd1d9b0e00c2612ea2dd080e`.
[Protocol](prereg-2026-09-18-read-first-followup.md) and
[offline engineering](results-2026-09-18-read-first-followup-implementation.md).
The exact executing commit passed all eight
[CI checks](https://github.com/shuxiachai/academic-commercialization-agent/actions/runs/35314037507)
before dispatch. This single batch is **closed and failed**. RF02/RF03 are unrun.

## Observed native path

RF01 sent a named `read_source` request, received one valid full-window call,
executed the actual local reader once and sent its complete saved synthetic
text in the second native request. That final-only request omitted tools and
used JSON Object output. Both projected native replies passed the transport
checks; the wrapper admitted the four-field assessment and its actual receipt.
This is one observed forced-read conversation, not autonomous tool selection.

The model declared `refuted` where the frozen reference was `insufficient`.
The code preserved that declaration and the batch stopped on
`expected_relation_mismatch`, without a third request. The physical-value
proposition was not a proposition that a record reported a measurement.
The answer recast it as the latter, treating an explicit absence of measurement
as refutation of the sample's physical property. Neither a valid citation nor
a successful tool read establishes that semantic step.

| Observation | Result |
|---|---|
| Attempted / selected controls | 1 / 3 |
| Native requests / actual local reads | 2 / 1 |
| Mechanical conversation passes | 1 of 1 attempted |
| Frozen-label checks / matches | 1 / 0 |
| Later controls | RF02 and RF03 unrun |
| Unknown-usage / pending requests | 0 / none |
| Fixed batch artifacts | 7, retained unchanged |
| Overall batch | failed and closed |

The parent subsequently recomputed the canonical journal body hashes and
compared the second request's complete tool payload with the frozen source
using a pure comparison helper, not another read or request. Body sizes were
4555 and 5338 bytes, below 12288. The saved executing identity still matched
all 19 bound files. These checks bind recorded intent and local execution;
there was no TLS packet capture or independent provider/backend attestation.
The availability audit explicitly keeps provider evidence receipt
`not_attested`, separately from observed response receipt.

## Separate LLM review

A different requested `route_reviewer` / `gpt-6-astra` / high context received
only the literal claim, text actually present in the final request, receipt
metadata and candidate assessment. Author reference labels, prior reviews and
the batch outcome were withheld from that first pass. No external sources or
additional project-provider requests were used.

It independently proposed `insufficient` and judged the answer `mixed`:
the quotation was supported, but the refutation depended on changing the
proposition from a physical value to recorded measurement. All three quoted
spans were checked in the supplied claim/text. Inherited project instructions
limit context isolation; effective backend metadata is unavailable. This is
fallible, label-blinded and context-limited LLM judgment, not human gold.

The raw judgment is retained separately outside the immutable batch directory.
The native summary's pending-review field is not rewritten retrospectively;
this dated observation records the later judgment. RF02/RF03 have no answers
to judge and do not enter a semantic denominator.

## Usage, stop and scope

Reported usage was 2433 input + 303 output = 2736 tokens. The frozen
conservative estimate is **USD 0.002436429**; the two retained request
reservations total **USD 0.022298624**, not an additional charge or invoice.
There is no unknown usage or in-flight continuation. Remaining six-request /
USD 0.10 ceilings do not authorize reopening the occupied output.

Only newly frozen fictional material was sent to exact configured
`qwen3.5-plus` at the pinned Beijing endpoint, non-thinking and non-streaming.
No real report, raw private reviewer material, supplementary search, retry,
repair, alternate model, recovery or production activation occurred. Closed
RPQ/PCQ/CLQ material and RF reference bytes were not altered.

The first-stage read-admission defect is addressed in this one bounded
observation. Live nonempty-evidence insufficiency is still **not established**.
Stop expanding this generative relation candidate for now: do not tune this
consumed batch or make a new paid attempt automatically. A future source
locator/quotation interface would be a separate product decision, not something
implemented or validated by this failed experiment. Production remains unchanged.
