# Catalog-native Qwen transport: offline boundary evidence

Date: 2026-09-16. The [protocol](prereg-2026-09-16-report-evidence-catalog-qwen-transport.md)
was committed as `169ee186b7351cbe428e42e0c50a79cf11eb5d24` before implementation.
This is intercepted HTTP evidence, not a new paid model batch. No real provider
key was read, no benchmark source left the machine, and production remains off.

## Why a separate adapter

The previous catalog exposes up to 32 source IDs, whereas the frozen hit-based
adapter admits five. Neither changing that old validator nor silently keeping
five entries would preserve the catalog contract and the old experiment identity.
The new module has its own ledger/configuration identity, accepts an explicit
trusted snapshot, and leaves all older core/policy/transport/runner files intact.

The adapter binds the exact ordered catalog and a single conversation. Initial
nonempty catalogs advertise only `read_source`; the next request is final-only,
with `none`, omitted tools and JSON Object. Empty catalogs finalize without a
read. The core still owns actual read execution, issued receipts and strict
final validation. Matching history/schema does not authenticate arbitrary Python
callers or establish semantic support.

The full canonical HTTP envelope has the same 12288-byte limit as before.
Reservation identity must match dispatched bytes, including the final output
mode. Existing pinned HTTP restrictions and conservative accounting primitives
remain; their limits are not a live allowance for this new identity. Ledger
acceptance, core answer acceptance and provider/model quality are separate facts.

## Free capacity measurement, before and after adaptation

The same 30 local snapshots contain 632 rows. They retain the earlier mixed
live/fixture and original-CSV identity limitations. Every probe uses the fixed
capacity question and first visible source, offset zero, length 1500, followed
by a scripted abstention. Positional selection is not a relevance judgment.

| Observation | Constructed envelope before implementation | Actual intercepted adapter |
|---|---:|---:|
| Snapshots reaching two callbacks | 30/30 | 30/30 |
| Initial body byte range | 4957--5873 | 4957--5873 |
| Final-only body byte range | 6026--7919 | 6026--7919 |
| Bodies over 12288 bytes | 0 | 0 |
| Provider requests | 0 | 0 |
| Intercepted HTTP requests | Not executed | 60 |
| Actual request/journal hashes agree | Not executed | 60/60 |

The actual adapter probe returned 30 scripted abstentions, with no transport
stop or wrapper refusal. Mock usage values were invented to test accounting;
they are neither provider-reported consumption nor billable cost. These figures
measure one local capacity path, not arbitrary input coverage, selection quality
or native model compatibility. Partial catalogs and oversized final histories
remain possible on different inputs and must disclose/refuse them explicitly.

## Secret-screening dependency found during review

Independent read-only AI protocol review identified a frozen helper limitation:
it recursively decodes whole JSON strings, but ordinary prose containing retained
JSON escape tokens is not itself a JSON document. A parent-executed synthetic
check with a fake key and a mixed-text escaped echo confirmed both literal and
legacy-helper detection returned false. No real credential or live request was
involved, and this is not evidence of a historical secret leak.

Deferring rejection to the core's final parser would be too late: the adapter
may already have persisted the projected assistant message. The new module
therefore screens recoverable JSON escapes in prose before journal persistence,
without repairing final answers or editing the frozen helper. Inspection is
bounded; exhausted inspection is a refusal, not a clean result. It does not
claim detection of every arbitrary encoding or exfiltration channel.

## Review after the first green controls

The implementation's first focused run passed 100 controls in 2.41 seconds;
the expanded focused set passed 136 in 2.62 seconds, with latest Ruff 0.16.7.
The latter includes the former and is not an additional denominator. No failed
focused attempt, skipped control or warning-rule relaxation preceded those runs.

Independent read-only AI implementation review nevertheless found a P2 history
consistency gap. Source/snapshot identity and field-type checks alone allowed
changed tool-result text with an original receipt; a scripted final response
could echo the changed text while the core still recognized the original ID.
A false `missing_text` status on a saved nonempty window was another variant.
This was a concrete serialization gap within the registered contract, not a
request for general semantic validation or proof of Python caller identity.
The preceding 136 green controls and 60-request capacity probe did not cover it.

Eleven new negative controls failed against the old comparator while eight
positive controls passed (2.06 seconds). The fix compares the whole canonical
result with a deterministic window derived from the bound snapshot and original
read arguments. It includes absence precedence, code-point offsets, text,
hashes and receipt identity, without executing a second read or delivering a
second receipt. The expanded 155-control set then passed in 3.00 seconds.

The parent independently re-injected five defects: a five-ID ceiling, omitted
final JSON mode, changed bytes after reservation, disabled mixed-escape scanning,
and bypassed saved-window comparison. Each injection produced the expected red
test (one each for the first four, two for the last). The last pair observes the
unwanted second HTTP request, not just an internal status. Every restoration
matched the original source SHA-256, and all 155 controls passed in 3.14 seconds.
These are deliberate offline fault injections, not live provider failures.

After the repair, the parent repeated the actual intercepted capacity probe:
30 snapshots, 60 requests, identical byte ranges, 60/60 request hashes matching,
30 scripted abstentions and no failures. It replaces, rather than adds to, the
same-snapshot capacity denominator above. The combined new/old catalog and
transport regression passed 509 controls in 6.92 seconds. Mock usage remains
synthetic; neither probe contacted a provider.

## Final local verification

The clean starting version `886bfd8d141992638053703676d8d424b0d267c7`
passed 3943 tests and 1360 subtests in 142.67 seconds before edits. The final
full zero-provider suite passed **4098 tests and 1370 subtests in 156.82 seconds**.
The 155 new controls and 509-test combined run are subsets, not additional tests.
Latest Ruff 0.16.7, the project's narrow Pylint command and the offline lock
check passed. No skips, warning ignores or weakened assertions were added.

All 94 protected source/configuration/protocol/snapshot/old-artifact hashes
remained unchanged. Independent read-only AI re-review closed the saved-window
finding and reported no further actionable finding in the inspected new module,
tests and guides; it did not run another test suite or act as a human evaluator.
Neither clean static review nor these offline controls establish model quality.

## Remaining boundary

This phase adds no live runner, fresh paid fixture, provider authorization,
production entry point or browser control. The new class is network-capable,
but its offline manifest is not a network sandbox or permission to dispatch.
The public demo still uses only a scripted callback, not this provider adapter.

Catalog forwarding means entry into that callback. An adapter preflight failure
may still prevent all HTTP dispatch. Observing an HTTP response is yet another
fact, not evidence the model processed the excerpt successfully. Do not flatten
those facts into a single successful-delivery claim.

Native read followed by valid final JSON in one successful live conversation
remains unobserved. Register a fresh synthetic batch and hash-bound runner before
testing it under applicable bounded user authority. JQ/SQ/FQ remain closed and
cannot be stitched into a pass. General entailment, user benefit and production
payer/ownership controls are still separate gates.
