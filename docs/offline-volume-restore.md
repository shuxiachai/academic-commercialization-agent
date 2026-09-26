# Bounded synthetic offline volume rehearsal

This maintenance check copies only freshly generated pytest fixtures into a
fresh destination and observes them through current application readers. It is
not a generic backup/restore service, CLI, live-volume operation, payment recovery
procedure, or authority to reopen any paid route. No production code is changed.

## Fixture and verification boundary

`tests/test_offline_volume_restore.py` creates one small synthetic run and one
pending paper extraction under pytest's temporary root. No existing reports,
`outputs/` contents, `.env`, provider keys, benchmark cohorts or private notes
are source inputs. A reusable synthetic registry helper is imported from an
existing test without editing its bytes. The inventory has a 128-entry and
2 MiB aggregate file-byte ceiling, not a production capacity recommendation.

The fixture includes:

- Run report, saved sources, synthetic scores, mutable status, immutable terminal,
  `.owner`, `.run-spec.json`, a retrieval checkpoint and `.resume-source/` checkpoint.
- `_papers/<synthetic-id>/extraction.json` plus its owner marker; no raw PDF.
- `.paid-operation-ledger.json` and `.paid-receipts.sqlite3`, with accepted run/paper
  receipts and an unresolved resume intent.
- `.source-locator-v1/.saved-source-receipts-v1.sqlite3`,
  `.saved-source-accounting-v1.sqlite3`, `control-v1.sqlite3`, and
  `native/<synthetic-receipt-hash>/manifest.json` plus `events.jsonl`.

RunSpec, checkpoint, report, terminal, paper extraction, daily-ledger, receipt
and accounting storage writers create the data wherever practical. The control
schema is initialized by its real store; its single reservation row is explicitly
synthetic SQL so the admission entry stays blocked. The native files explicitly
say synthetic/not-run and are only byte-inventoried, never parsed as evidence of
a provider request. No transport is instantiated. Stored callback/admission
counts are scenario data, not observed executions. The accounting sidecar is
deliberately unfinished: unknown tokens/cost stay null, never an invented bill.

All fixture writes are synchronous and tracked SQLite connections must be closed
before the inventory/copy. A test-only connection subclass verifies real closure
in the connection's owner thread; it does not disable SQLite's thread checks.
Readers' asyncio executor threads drain when
`asyncio.run` returns; each lookup controller is closed with no operation threads.
Leftover SQLite WAL, SHM, rollback-journal and temporary files are rejected, not
removed to make a copy pass. Absence of those files alone is not proof that a
real deployment is quiescent.

The trusted inventory stays outside the copied tree in test memory. It records
relative paths including dotfiles/directories, entry types, file lengths and
SHA-256 hashes. Links/reparse points (including ancestor checks) are rejected
before traversal. Copying requires a nonexistent destination inside the fresh
pytest sandbox, outside the source; files are created exclusively, not merged or
overwritten. Source and destination must match the inventory before/after copying,
and after all reader observations. A failed partial copy is not auto-repaired.
This assumes controlled, quiesced fixtures, not a race-proof adversarial copier.

Fresh readers point at the restored root and quota caches are reset:

| Boundary | Actual observation |
|---|---|
| Run/artifacts/owner | `runs.get_state`, `artifact_path`, `owner_of` |
| Frozen input/outcome/checkpoint | `RunSpec.load`, `load_terminal_record`, `CheckpointStore.inspect` |
| Pending extracted paper | `papers.load_extraction`, `extraction_path_for_run` with owner check |
| Daily quota and general receipts | Raw daily-ledger reader/cache reload; `receipts.lookup` and `public_record` |
| Locator saved-text delivery | `SavedSourceController.lookup` with **no selector**, plus `SavedSourceLoader` |
| Accounting/control/native files | `AccountingStore.observe`; control readonly schema/row sanity; exact native bytes |

Legacy receipt readers can open SQLite read/write. The assertion is **no changed
bytes after observation**, not OS-enforced readonly access or absence of transient
I/O. This does not simulate process restart, HTTP/browser delivery, worker
hydration, checkpoint reuse execution, native journal semantics, or full score
validation. In particular, `inspect == reusable` is storage-identity evidence,
not permission to resume paid work.

Execution, admission, PDF extraction, native construction/calls, selector,
subprocess and network entry points are fail-fast guarded. Independent teardown
call-count assertions catch even errors swallowed by application fallbacks.
Only the Windows asyncio socketpair loopback self-pipe is exempt; ordinary
loopback requests and external networking are not. No new dependency is needed.

## Meaningful negative controls

After a correct copy passes, tests actually omit the hidden daily ledger, mix
same-size score bytes and truncate a receipt database: the original inventory
must reject all three. Terminal corruption yields an unreadable record and
unknown run outcome despite the old `done` flag; checkpoint corruption yields
`corrupt`. Missing/changed locator source data gives `expired`/`changed` delivery
without selection. Damaged accounting preserves the exact available excerpt
while exposing unavailable/unknown accounting and null cost, not zero.

The existing daily-ledger reader treats a missing file as first boot (`{}`).
This rehearsal demonstrates why an inventory is necessary; it does **not** fix
that production behavior or make a missing ledger safe.

A separate old-snapshot negative adds synthetic consumption and another intent
to the source after copying. The earlier copy remains internally intact and
readable against its own inventory, but lacks the later count/receipt. **This is
not a freshness detector.** An intact old snapshot must not be used to resume
paid admission or justify retrying an uncertain request.

## Manual actual-restore prerequisites: separate authority required

An actual restore requires a separately authorized, deployment-specific plan:

1. Stop **all** new paid routes: assessments, resume, paper extraction and locator
   selection. Locator-only rollback does not stop other volume writers.
2. Drain actual worker processes, PDF/locator threads and maintenance writers,
   including cleanup, terminal publication, receipts and accounting finalization.
   Cancelling HTTP waiters or observing zero active requests is not physical drain.
3. Establish a consistent quiesced copy of the whole volume and a trusted external
   inventory, including hidden state and the source/copy time and identity. A
   database file copied while WAL writers run is not this rehearsal's input.
4. Verify in an isolated destination with execution disabled, no provider keys,
   no background maintenance and fresh reader/cache state. Preserve the original
   source and any damaged evidence; do not overwrite an online volume or drop
   journals to permit retries. Reconcile later consumption/unknown receipts using
   separately authorized evidence before considering any subsequent deployment.

This document authorizes none of those live actions, no online overwrite, and
no payment resumption. Filesystem ACL/ownership, hard-link aliases, fsync/crash
durability of a copy, encryption, retention of backups, Railway snapshots,
distributed consistency, freshness and provider exactly-once delivery are not
established. Windows link/reparse rejection uses injected metadata for files,
directories and ancestors, requiring no link privileges and no skipped cases.
This is not a native Windows link/junction observation. The POSIX branch also
checks a real directory symlink; a Windows run does not validate that branch.

## Running and release handoff

Use a **new, nonexistent** basetemp path on every invocation (pytest may remove
an existing basetemp). For example, from the repository in PowerShell:

```powershell
$fresh = Join-Path (Get-Location).Path ('outputs/pytest-offline-volume-' + [guid]::NewGuid().ToString('N'))
uv run --offline --no-sync pytest -q tests/test_offline_volume_restore.py --basetemp $fresh
```

After the focused check, run the complete repository suite and obtain an
independent review before accepting the change, following
[the contributor checks](../CONTRIBUTING.md#checks-before-and-after-a-change).
A focused pass does not establish either release gate, a live restore or a
paid canary.
