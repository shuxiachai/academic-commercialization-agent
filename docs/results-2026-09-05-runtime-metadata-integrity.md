# Runtime metadata read integrity — 2026-09-05

## Scope and measured starting point

This is zero-provider fault containment, not a paid experiment or an observed
production outage. The starting revision was `88fdc0e32586c3c055f7e752319eb29f3e912b4f`.
Before editing, the complete local suite passed 2,073 tests and 1,095 subtests.

A read-only census covered only the 109 timestamp-named direct children of
`outputs/` and the 30 frozen `outputs/benchmark/` directories, excluding test
copies, experimental cohorts and private worktrees. It printed aggregate
counts only and changed no stored artifact:

| Cohort | Status object readable | Status absent | Status malformed | Terminal absent |
|---|---:|---:|---:|---:|
| Local history, 109 runs | 67 | 42 | 0 | 109 |
| Historical benchmark, 30 runs | 0 | 30 | 0 | 30 |

These older artifacts do not exercise the new terminal contract. Absence is
not corruption, the counts are not 139 failures, and no observed corruption
rate or production incident can be inferred. The unused legacy UI language/
profile helpers were not changed just to make a metadata cleanup look urgent.

## Reproduced failure and change

Isolated byte-level fixtures demonstrated that invalid UTF-8 and valid JSON
scalars/arrays could escape the reader as HTTP 500; `done="false"` could
become a completed run. A damaged terminal record fell back to weaker mutable
done/error/cancellation markers, despite already advertising an unreadable
terminal. History then read raw status a second time and could fail the entire
list even after the detail reader had handled the fault.

The corrected reader distinguishes `status_record_state=absent/readable/unreadable`
at the actual file read. It validates the container and outcome flags while
preserving optional legacy fields. It does not migrate files or validate every
nested historical audit schema.

- A live process still establishes `running`; a valid immutable terminal still
  establishes its outcome even if the live projection is damaged.
- With no live process and a present but unreadable terminal, the outcome is
  `unknown`, not a guessed success/failure. Legacy inference applies only when
  the terminal file is absent.
- Unverifiable outcome timing is null, rendered as a dash rather than zero.
  Readable usage snapshots are lower bounds; no readable measurement is
  unavailable. A valid terminal's null usage is authoritative and must not be
  backfilled from a stale mutable bill. No reader fabricates a snapshot time.
- Status and progress expose the same record-read state. `progress.done` is
  false for `unknown`. History reuses the safe projection for topic and duration.
- The actual browser labels damaged live metadata even beside a valid completed
  terminal. A stale `stage=Done` cannot paint an unknown outcome all green.

No raw error paths or diagnostic text were added to public responses. Ownership,
paid admission, worker writes, scoring, frozen experiments and zero-call
production Tool Calling were not changed.

## Verification and limits

Twenty-three new offline cases exercise both HTTP read endpoints and history,
including a healthy neighbour, missing historical files, invalid encoding,
invalid JSON container/outcome flags, live processes, valid/damaged terminals,
permission failure and unavailable terminal accounting. The expanded Chromium
journey uses real isolated files, FastAPI and the shipped DOM. It permits only
loopback reads and verifies no external or mutating requests.

Three deliberate defect re-injections failed at their intended seams:

1. Removing damaged-terminal precedence: three wrong lifecycle outcomes.
2. Restoring history's second raw status read: eight HTTP-500 failures.
3. Dropping the new field from progress: Chromium could not find the unreadable
   metadata warning, despite the internal value being correct.

All injections were restored. The post-code suite passed 2,096 tests and 1,098
subtests; latest Ruff, narrow Pylint and the restored Chromium journey passed.
Documentation indexing can add subtests independently of runtime coverage;
the PR's CI checks the final committed tree on both platforms.

This does not prove disk durability, automatic metadata recovery, a production
SLO or every nested audit schema's robustness. `unknown` remains retryable;
persistent storage damage needs operator inspection, not an automatic paid
rerun. Existing reports are not rewritten or deleted by these reads.
