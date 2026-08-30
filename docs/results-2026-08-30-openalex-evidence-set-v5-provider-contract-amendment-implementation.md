# Result: evidence-set v5 DeepSeek V4 provider-contract amendment

Date: 2026-08-30

## Outcome

The post-stop provider amendment is implemented and passes its zero-network
qualification. It authorizes no paid rerun and keeps the v5 runner disconnected
from production, reports, planner triggers and OpenAlex.

The historical `deepseek-chat` execution remains sealed as
`partial / not_evaluated`. This implementation does not edit those artifacts,
infer the missing returned-model string, reconstruct unpersisted usage, or
convert an unknown cost to zero.

## Implemented contract

- the adapter requests exactly `deepseek-v4-flash`;
- every body explicitly sends `thinking={"type":"disabled"}` to preserve the
  original non-thinking method;
- exact returned-model equality remains mandatory, including rejection of a
  dated suffix;
- no redirect, retry, repair, fallback or semantic-output persistence is added;
- a parseable failed response may expose only its safe returned-model identity
  and validated usage observation to the runner;
- failed-call usage reaches both the write-once call journal and aggregate
  `execution.json` totals;
- a potentially spending request without inspectable usage keeps the complete
  execution cost `uninspectable`; and
- the conservative local V4 Flash price row uses the official peak rates with
  its own 2026-08-30 basis date, without restamping older price rows. The
  experimental adapter ignores the general-purpose environment price override
  so an unrecorded deployment variable cannot change the frozen budget.

Manifest and execution artifacts use schema version 2 so a future consumer can
distinguish the amended accounting contract from the historical version-1
stop artifact.

## Tests and defect reinjection

The adapter/runner subset passed:

```text
16 passed in 2.33s
```

The combined adapter, runner and shared-accounting subset passed:

```text
46 passed, 8 subtests passed in 2.09s
```

The complete zero-network suite passed:

```text
1751 passed, 639 subtests passed in 32.98s
```

Two seam defects were then re-injected independently. After removing the
`thinking.disabled` field, the outbound transport-seam test failed with a
`KeyError: 'thinking'`, proving that the new test observes the actual serialized
request rather than only the request model. The same patch was reversed and
the correct implementation restored. Re-enabling the general environment price
override inside the frozen adapter made the same seam test observe
`env LLM_PRICE_PER_MTOK` instead of the built-in peak basis and fail. That
patch was also reversed. These failures prove both controls are asserted at
the serialized/provider-accounting boundary rather than as unused fields.

The real default dry-run subsequently verified 8/8 W cases, 64/64 candidate
identities, 16 unique prompt identities, the four opaque source-artifact hashes
and all six behavior-bearing dependency hashes. It explicitly reported zero
network calls, zero model calls, no private-label parsing and no production
connection.

## Frozen implementation identities

| Dependency | SHA-256 |
|---|---|
| `deepseek_evidence_judge.py` | `fa912d12a74c273857b363979e841298a9ca94e8599cc7dd31b4b33a47cecc8f` |
| `token_usage.py` | `b2a8cb6df7e6b40efc0b354965c83a205b18297002010299c9aedd0bc56a1e13` |

The runner records its own observed hash in each manifest rather than embedding
a recursive expected digest. The future authorization must name the merged Git
revision that contains this implementation.

## Next gate

No further provider request occurred during this repair. A later W01-W08
development execution requires fresh explicit authorization with a merged
revision, model-call ceiling and soft stop. Completing that execution would
still establish only development qualification; it would not validate v5 or
connect Tool Calling to production.
