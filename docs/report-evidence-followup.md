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

The transport must be explicitly injected. No concrete network adapter is
included. It exchanges assistant `tool_calls` and tool-result messages with
the exact original `tool_call_id`, following the documented
[Qwen-compatible Function Calling message shape](https://help.aliyun.com/en/model-studio/qwen-function-calling).
This does not establish that the exact production model accepts the prototype.

At most two tool requests and three transport turns are allowed, with at most
one tool request per turn. Bad tool names and arguments consume tool budget;
ambiguous/duplicate IDs fail the protocol. There is no automatic retry, repair,
search fallback or autonomous switch to another report. A trusted future
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

## What is intentionally not connected

- No FastAPI route, browser button, production worker hook or scoring change.
- No paid follow-up admission, persistent receipt, live usage ledger or model
  request; these must be designed before exposing a paid endpoint.
- No external retrieval, new source registration, cross-run memory or report
  mutation. The existing v1–v8 source locks and evaluation decisions remain intact.
- No claim of full-text verification, hallucination elimination, independent
  accuracy, user time savings or production-ready Tool Calling.

## Next gates

The [phase-one protocol](prereg-2026-09-14-report-evidence-followup-phase1.md)
defines offline acceptance and the non-model comparison. The next live step
requires a frozen exact model, input set, request/cost ceilings and separate
authorization. A production release additionally needs ownership, shared paid
admission, accounting, request receipts, safe diagnostics and user-visible
failure states. The experimental library being importable is not that release.
