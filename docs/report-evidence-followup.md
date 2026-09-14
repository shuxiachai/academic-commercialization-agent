# Report evidence follow-up

## Scope

This is a production-disconnected, read-only conversation prototype. It is not
the supplementary Evidence-gap Planner, does not reopen v8, and cannot add
sources to a report. Its task is helping a reader locate saved evidence, not
deciding whether an investment or scientific claim is correct.

The ordinary alternative remains browsing the same source cards and summaries.
Reader benefit relative to that alternative has not been measured. This phase
tests the tool conversation protocol, not model quality or product adoption.

## Offline demonstration

```bash
uv run python report_evidence_followup_demo.py
```

The demo supplies synthetic sources and a scripted transport. It exercises the
real local lookup/read functions and tool-call/result pairing, but makes **zero
provider requests**. It does not read `.env`, accept credentials, read a saved
run directory or fetch a URL. It must not be presented as a live Qwen demo.

## Trusted snapshot boundary

The caller supplies one source collection and a report reference; the module
projects them into a detached immutable snapshot. Duplicate source identifiers,
wrong domain prefixes and malformed relevant fields are rejected rather than
silently overwritten. Modifying the original collection later cannot change
the conversational evidence.

This in-memory boundary does not implement web authentication or authorize the
caller. A future route must authenticate and select the source collection
before constructing a snapshot. Model arguments must never supply a run ID,
file path, URL, credential or alternative provider. Hashes bind content to this
supplied snapshot; they do not prove authenticity, ownership or source truth.

## Available tools

| Tool | Reads | Limits and explicit absence |
|---|---|---|
| `lookup_sources` | Literal matches in this snapshot's saved titles/summaries | Query 1–256 characters, at most five hits; total matches and truncation remain visible. No matches is not evidence that the literature lacks an answer. |
| `read_source` | One source's saved summary, by its local source ID | Strict integer character window, at most 1,500 characters; unknown IDs and unavailable text issue no evidence. A non-empty truncated window may be delivered successfully, but remains explicitly incomplete. |

Window offsets use Python/Unicode code points and half-open `[start, end)`
intervals, not UTF-8 byte offsets or JavaScript UTF-16 indices. A complete window
means all **saved** text was returned; the saved text may itself be a truncated
abstract, search snippet or material with unspecified origin. Nothing here
retrieves or verifies publisher full text.

`window_truncated` means that some saved text lies outside the returned window,
not that the requested length was clipped at the end. A partial non-empty
window can issue an evidence ID and support `answered_with_evidence` as a
delivery state; it does not establish completeness or semantic support.

Tool descriptions and the initial instruction treat returned source text as
untrusted data. Enforcement comes from the fixed dispatcher, strict arguments,
snapshot binding and budgets, not a promise that prompting defeats injection.

## Conversation and evidence delivery

The transport must be explicitly injected. The core has no implicit network
fallback. It exchanges assistant `tool_calls` and tool-result messages with
the exact original `tool_call_id`, following the documented
[Qwen-compatible Function Calling message shape](https://help.aliyun.com/en/model-studio/qwen-function-calling).
The scripted demo remains offline; native model observations belong to the
separate bounded canary below, not to that demonstration.

At most two tool requests and three transport turns are allowed, with at most
one tool request per turn. Bad tool names and arguments consume tool budget;
ambiguous/duplicate IDs fail the protocol. There is no automatic retry, repair,
search fallback or autonomous switch to another report. The injected
transport must separately enforce network timeout, credentials and cost; an
in-process injected callback cannot be safely preempted by this library.

Successful reads issue code-owned evidence IDs bound to the snapshot, source,
field, exact interval and excerpt hash. The model can select only IDs actually
issued in this conversation. The application assembles their source metadata
and text; it does not accept model-invented quotes or provenance. Lookup hits
alone do not authorize an evidence citation.

The final answer distinguishes evidence-backed *delivery* from an answer without
delivered evidence, deliberate abstention and execution failure. In all cases,
`semantic_support` remains `not_assessed`: exact excerpt attribution is not
proof that the prose is entailed by the excerpt. No-tool responses do not count
as successful tool use or completed evidence checking.

## Bounded Qwen compatibility work

The [Qwen canary protocol](prereg-2026-09-14-report-evidence-followup-qwen.md)
defines two synthetic controls and one shared allowance: six sequential requests,
USD 0.10 soft stop, exact `qwen3.5-plus`, no retry or supplemental search.
It uses only the dedicated DashScope key and the official Beijing destination,
independently of the ordinary pipeline's selected provider. Global credentials,
model configuration and `.env` are not rewritten.

The separate adapter and experiment ledger enforce transport limits and record
request intent before dispatch. Missing usage or an uncertain attempt stops the
batch instead of being estimated as zero. Reported tokens and conservative cost
estimates are separate from the provider invoice. An occupied output cannot be
reused. This local, single-owner experiment ledger is not the application's
shared paid-admission service or a customer receipt system.

No real saved report is read by the canary. Its fixture identities, source and
dependency hashes must match a committed version before network execution.
The core's delivered evidence means handed to the transport callback; the
network ledger separately records dispatch/response observations. Neither
establishes that the model understood the excerpt.

## What is intentionally not connected

- No FastAPI route, browser button, production worker hook or scoring change.
- No production follow-up admission or customer receipt. Local canary accounting
  must not be presented as protection for a public paid endpoint.
- No external retrieval, new source registration, cross-run memory or report
  mutation. The existing v1–v8 source locks and evaluation decisions remain intact.
- No claim of full-text verification, hallucination elimination, independent
  accuracy, user time savings or production-ready Tool Calling.

## Next gates

The [phase-one protocol](prereg-2026-09-14-report-evidence-followup-phase1.md)
defines offline acceptance and the non-model comparison. The bounded canary
has separate frozen inputs, authorization and failure criteria. A production
release additionally needs ownership, shared paid
admission, accounting, request receipts, safe diagnostics and user-visible
failure states. The experimental library being importable is not that release.
