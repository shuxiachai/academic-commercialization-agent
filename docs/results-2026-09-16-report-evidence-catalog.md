# Bounded metadata catalog: offline discovery, not live closure

Date: 2026-09-16. The [protocol](prereg-2026-09-16-report-evidence-catalog.md)
was committed as `30228b925f4ce390ae438fddaa105c3c8f667970` before implementation.
This phase makes zero model/search requests and reads no provider credentials.
The earlier JQ failure is unchanged; production follow-up remains disconnected.

## Decision and scope

The actual JQ01 long query did not appear contiguously in its saved title or
summary. Replaying that predicate returned false in both fields, while the
summary remained present. This is consumed diagnostic evidence, not a fresh
case pass. Silently changing literal matching to a word-bag search would add an
unmeasured ranking/selection policy. We instead expose a small metadata catalog
and let a scripted selector exercise the existing direct-read seam.

The new wrapper composes the frozen core, not the old guarded-policy note that
the catalog has no IDs. The frozen count-only overview remains as it was; the
new supplementary user-data catalog explicitly contains IDs. The code-owned
instruction labels titles untrusted and metadata-only. It cannot issue evidence.
Only one visible-ID read is allowed, then final-only, below the old two-tool/
three-turn ceiling. This is a combined catalog/action-policy candidate, not an
isolated causal comparison of catalog wording.

The catalog has at most 32 entries, 256 Unicode code points per title and 6,144
canonical ASCII JSON bytes including its envelope. It retains a deterministic
snapshot prefix, not relevance ranking. Returned/omitted counts, title clipping
and complete/partial coverage are explicit. Actual callback arguments have a
separate 12 KiB limit; this does not establish any future HTTP body size.

## Local capacity observation

Thirty existing local source snapshots contain 632 source rows, 19--24 per
snapshot, with all stored summaries nonempty. Total title lengths are
1,253--1,974 characters per snapshot; the longest title is 245 characters.
The source-count distribution is 19:9, 20:3, 21:6, 22:3, 23:7 and 24:2.
These local files include the previously disclosed live/fixture identity limits;
they do not revalidate the original calibration CSV or source relevance.

The actual candidate projected all 30 snapshots and forwarded 30 scripted
initial callbacks with a fixed capacity-only question:

| Observation | Result | Limit |
|---|---:|---|
| Complete catalogs | 30/30 | Metadata capacity, not evidence support |
| Returned source rows | 632 | Repeated snapshots are not independent papers |
| Omitted rows / clipped titles | 0 / 0 | Other inputs can be partial |
| Canonical catalog bytes | 2,555--3,428 | Entire catalog envelope |
| Canonical initial callback bytes | 4,834--5,750 | Fixed question; no successful-read history |
| Pre-dispatch failures | 0 | Only this capacity probe |
| Provider requests | 0 | Scripted abstention, no paid validation |

This probe retained summary fields in the local snapshot but did not put them
in the initial callback. It did not send real reports outside the machine,
choose a relevant source or calculate model accuracy.

Two measurement-harness pitfalls were kept separate from application failures.
An initial PowerShell array `.count` collided with a row field; explicit property
aggregation corrected the denominator. A later native-pipe Unicode decode failed
strict snapshot validation. The original UTF-8 summaries contained zero unpaired
surrogates; ASCII-escaped JSON in the local pipe removed the transport ambiguity
without changing source bytes or weakening validators. Only the successful
replay contributes to the table above.

## Verification boundary

The unmodified baseline passed **3843 tests and 1350 subtests in 135.25 seconds**.
The 93 new focused controls exercise the real core/callback/read seams, including
identical-title separation, visible-ID admission, missing text, receipt reuse,
strict final envelopes, Unicode boundaries and pre/post-forward failure states.
The scripted demo runs in a child process with provider imports, network
operations, credential reads and external JSON/environment/report inputs denied;
it does not merely print an offline label and assume that label proves isolation.

The first focused attempt reported **92 passed and two setup/cleanup errors in
2.76 seconds**. Pytest's automatically escaped parameter name embedded 4,096
emoji into `PYTEST_CURRENT_TEST`, exceeding Windows' 32,767-character environment
value limit. A minimal environment-variable reproduction confirmed the cause.
Only short display IDs were added; all original input values and assertions
remain. The corrected `uv run pytest` passed **93 tests in 2.57 seconds**. No
skip, warning suppression, character-limit relaxation or shortened input was used.

Three separate source mutations each made a real seam assertion fail:

| Re-injected defect | Observed failing control | Exact source restoration |
|---|---|---|
| Omit catalog from actual outgoing messages | Callback-based source selection cannot complete (1.71 s) | SHA-256 matched |
| Bypass visible-ID admission | Registered but omitted A33 reaches forbidden core dispatch (1.70 s) | SHA-256 matched |
| Record forwarding before the 12 KiB check | Unsent read incorrectly appears delivered (1.77 s) | SHA-256 matched |

The restored focused suite passed **93 tests in 2.47 seconds**. Eighty-nine
protected source/test/protocol/configuration, local snapshot and earlier batch
artifact files retained their hashes. This is a scope-specific integrity check,
not a new accuracy assessment. Latest Ruff 0.16.7, narrow Pylint and the offline
lock check passed; the scoring formula and existing warning/CI rules are unchanged.

The first full candidate suite passed **3936 tests / 1360 subtests in 130.77
seconds**. Independent read-only AI review nevertheless found a test-isolation
gap: the child guard listed only connect/getaddrinfo/sendto and therefore missed
`socket.gethostbyname`. That green run is retained as pre-repair evidence, not
proof that every network path was blocked. The review is not human evaluation
or proof of semantic correctness.

The shared child guard now denies every `socket.*` audit event except the
necessary constructor event `socket.__new__`. Seven added self-checks use the
same guard bytes as the real demo: numeric-only gethostbyname/getaddrinfo,
simulated connect/sendto/bind/future events and actual unconnected construction.
Numeric probes do not require external DNS even if the guard regresses. This
is a Python-level guard, not an OS sandbox or subprocess egress guarantee.
The first all-event guard was an unexecuted draft; no initialization failure is
invented to justify the earlier three-event list.

Re-injecting that three-event list made the actual numeric gethostbyname control
fail in **1.74 seconds**. Exact test-file SHA-256 restoration then returned all
**100 focused tests to green in 2.90 seconds**. The method/core files did not
change for this repair. The previous 93/3936 results are not silently replaced
or added to the final denominator.

Final local regression passed **3943 tests / 1360 subtests in 167.03 seconds**;
latest Ruff, narrow Pylint and the offline lock check passed again. The 100 new
focused controls are part of that total, not additive. Independent read-only AI
re-review closed the P2 and found no remaining actionable issue in the scoped
implementation; it did not execute these tests or establish model accuracy.

The actual no-argument demo printed `scripted_offline`, one real local read,
two callbacks and one served receipt, while retaining `semantic_support` as
`not_assessed` and answer verification as `not_verified`. The selector takes
the first row deliberately; identical titles remain ambiguous. These observed
scripted facts cannot be described as a successful native Qwen conversation.

## Remaining gates

This is a callback-only library and no-argument scripted demo. It has no native
Qwen adapter, new paid runner, API route, browser button or production hook.
The old stage/final-JSON adapter admits at most five hit IDs, not this catalog's
32-entry enum. Reusing its old identity or shrinking the catalog silently would
misstate the experiment. A separate full-wire adaptation is the next technical
gate, followed by a fresh bounded protocol before any live validation.

Correct metadata delivery is not correct model selection. Similar titles,
omitted sources, partial windows and questions requiring multiple records remain
limits. A catalog source ID never counts as a served citation, and a real read
still does not establish semantic entailment. Native read plus final JSON in one
successful live conversation remains unobserved. Do not combine the historical
SQ read with the separate JQ JSON result, reopen a failed batch, or enable the
production Evidence-gap Planner on the strength of this offline work.
