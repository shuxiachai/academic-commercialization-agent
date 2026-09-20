# RQ: native selection through isolated receipts and browser recovery

Registered on 2026-09-20, before native observation, from
`d27130aa813af01c6c20427a3b13654ca21f2db1`.
New protocol identity: `saved_source_receipt_qwen_canary_v1`.
This is a two-case synthetic development integration check, not a general
production adapter, unseen evaluation or permission to transmit private reports.
Closed SLQ/SLCQ and earlier answer/relation batches remain closed.

## Fixed data and pre-freeze reference

Use only [this new fixture](../tests/fixtures/saved_source_receipt_qwen_canary.json),
SHA-256 `b82f67446853685195d03b8e6e9f0a99c5aa11705f10752420ca558907f06216`.
Its six sources are explicitly fictional, with synthetic provenance and no real
paper URLs, DOI records, reviewer files or user questions.

| Case | Metadata location task | Frozen outcome |
|---|---|---|
| RQ01 | Impact-event timestamp recording, rather than energy absorption | A12; excerpt; one completed local read |
| RQ02 | Methane sensor calibration, with no fitting title in the catalog | explicit decline; no source or local read |

Provider refusal is not RQ02's explicit-decline reference. The stored text stays
local; provider input contains only the unchanged locator instructions/schema,
current question and visible ID/title catalog. Labels, summaries, browser receipt
keys, access codes and original report metadata must not enter that body.

A fresh label-blinded LLM context independently selected A12 and DECLINE using
only those questions and titles. It saw no draft labels, stored text, workspace
or external sources. Its role was configured as Astra/high; effective backend
metadata was unavailable. This is fallible title-location reference review, not
human gold, source truth, semantic support or demonstrated user benefit.

UTF-8 provenance (no trailing newline; visible input uses compact JSON):
- Visible input: `358b12a32a3857e3cf766bd7cdc0d25c0d206ed4439d9c5ae573fda1dc851acf`.
- Full supplied prompt: `b5be8bf3ed285e1c23f44340f3ede030395ca005989c1331168d6a3c72b57fef`.
- Returned review: `7ca2e62c5c02a96931a99cd1e788fb72671b45ba50f318df84777998709f8ec5`.

Before edits, the whole offline suite passed 6499 tests and 1578 subtests.
A read-only measurement of 30 current local registries found maximum full native
request size 5013 bytes for a fixed measurement question, with zero above 12288.
This is neither original benchmark identity nor a model observation. The new
RQ01/RQ02 callbacks measure 1738/1665 bytes, full native bodies 1861/1788 bytes.

## Narrow operational authority

The owner accepted restricted Qwen integration and a small synthetic trial,
under standing low-cost permission without repeated confirmations. This new
batch narrows that authority to:

- exact `qwen3.5-plus`, pinned DashScope Beijing compatible endpoint;
- at most two sequential native requests, one per ordered case;
- USD 0.05 aggregate soft stop; accept possible small excess from one in-flight
  request, never use that allowance to start another request;
- no retries, redirects, repair, fallback, search, resume, model replacement,
  private inputs, production activation or manual Railway restart.

This is not reuse of an old consumed batch. Before native use the parent must
bind the exact committed code/fixture, complete independent review and wait for
all CI checks on that tree. The CLI acknowledgement records the operator action;
it does not independently prove user consent, review or CI.

The [official model page](https://www.alibabacloud.com/help/en/model-studio/qwen3-5-plus)
was checked on 2026-09-20: Beijing supports Function Calling and its published
upper-context rates remain USD 0.573 input / 3.44 output per million tokens.
Retain the unchanged transport's conservative engineering rates, 16384 input-token
reservation and 512 output-token cap: USD 0.011149312 per attempt, USD 0.022298624
for two. These are admission estimates, not invoices, exact tokenizer bounds,
cache discounts or claims about the returned backend's weight snapshot.

Live credentials come only from process `DASHSCOPE_API_KEY`, after identity and
fresh-output checks. No dotenv or other-provider fallback in the runner. The
parent may supply that single existing local value only after any separately
required local-secret permission, without printing or persisting it; no
configuration file is uploaded. An absent process credential is a blocker,
not authority to bypass a denied configuration-file read.

## Composition and isolation

Add the dedicated adapter and runner; do not rewrite the frozen locator,
`LocatorQwenTransport`, `LocatorQwenLedger`, existing receipt controller,
HTTP factory, browser scripts or public `api.main`.

Each case binds its exact report ID, detached snapshot, question and selector
identity. Its selector composes one fresh unchanged native transport/ledger.
A new aggregate BatchGate binds the case's receipt-key hash and owner before
the real browser POST is forwarded, reserves before native dispatch, and does
not admit the next case until the previous case is fully checked and drained.
The callback itself lacks receipt identity; the pre-POST observation must not
be misrepresented as a native callback's key verification.

Use the real isolated factory, controller, saved-source loader, native selector,
local read and browser. Only these two native POSTs occur; do not spend two more
calls on an earlier ASGI rehearsal. RQ01 discards the actual returned POST
acknowledgement, reloads with no automatic request, re-enters the synthetic code
and explicitly GETs the same receipt. RQ02 verifies the explicit decline and
read-only receipt replay. Neither lookup nor replay may add a selector entry,
native reservation or daily charge.

The dedicated process uses only fresh synthetic owner/run storage and a
synthetic access code. Restore scoped global settings and always drain physical
operation threads before advancing or ending. No existing user output is opened.
Browser traffic is confined to the exact loopback page/assets/API; upstream
route fetches disable redirects. A new native test guard admits only the fixed
DashScope HTTPS endpoint and necessary loopback execution, not arbitrary hosts.
Keep the old zero-provider guards unchanged. These runtime checks are not an
OS/network sandbox or proof of provider exactly-once execution.

HTTP `provider_usage` and `provider_cost` remain `not_observed`: this layer's
wire contract has no provider accounting collector. The new native side ledger
reports validated usage, reservation consumption and estimate separately;
do not overwrite those wire fields to advertise a complete end-to-end bill.

## Identity, durability and stopping

Default CLI is identity-only: no credential read, output creation or native
request. Freeze fixture bytes, complete callback/native request hashes, all
relevant local transitive source/dependency paths, protocol/tests, browser assets
and lock/installed dependency versions, retaining committed and disk hashes
under the existing explicit CRLF-to-LF rule. Record Python/Chromium identities
without claiming installed binary attestation. Recheck source/input identity
before and after each native callback, including failure paths.

The only native output is `outputs/saved_source_receipt_qwen_canary_v1`.
Reject occupied/partial/symlink/reparse output; there is no override, resume,
cleanup-and-rerun or automatically selected alternate batch directory.
Persist the new identity/authority manifest and durable intent before dispatch.
Use atomic, write-once JSON publication after complete flush/fsync/close.

The global gate consumes the sum of max(reserved, known estimate), keeps unknown
usage charged and stops after the first identity, mechanical, reference, budget,
usage or publication failure. Preserve planned unrun cases and null metrics.
Do not run RQ02 merely because RQ01 returned an HTTP response. Pending native
writes or failed receipts cannot be refunded or repaired by another selection.

Mechanical gates reconcile exact native bytes, one reservation/finish pair,
exact response model string and coherent usage; one original callback and the
expected local read; complete POST/GET receipt identities/results and actual
inert browser text; one temporary daily admission and physical exit. Reference
agreement is a later, separate gate. Overall success requires both cases,
complete durable summaries and no pending/unknown accounting.

Never publish raw provider/error bodies, refusal prose, API/access keys or
receipt capabilities. Synthetic native request journals are still distinguished
from public-safe aggregate summaries. Monotonic elapsed time includes the local
identity/browser/publication workflow; it is not provider latency or an SLO.

## Offline release gate

Use fake keys and intercepted actual native HTTP through the real application,
not a fake successful locator callback. Cover strict request/source binding,
aggregate budget/order, occupied output, before/after identity drift, unknown
usage, receipt lost-ack replay, first-failure stopping and safe diagnostics.
Reinject critical identity/admission/replay faults and require unchanged tests
to fail before restoring exact hashes.

A separate browser rehearsal uses intercepted native responses only and cannot
read a real key. Run before/after full zero-provider tests, latest Ruff, narrow
Pylint, existing browser journeys and an independent read-only review before
native execution. Any later semantic inspection is an honestly labelled fresh
LLM review, never a human prerequisite or an extra paid judging request.
A successful batch does not turn on the public website feature.
