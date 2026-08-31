# Result: evidence-set v5 Qwen provider-contract implementation

Date: 2026-08-31

## Outcome

The pre-registered Qwen3.5 Plus provider profile is implemented and passes its
zero-network qualification. It authorizes no paid request and keeps the v5
judge disconnected from production reports, planner triggers, OpenAlex and the
six-stage workflow.

The existing DeepSeek schema-2 profile remains available as the historical
default. Qwen uses a separate schema-3 manifest and implementation lock rather
than rewriting the provider identity of earlier artifacts.

## Implemented contract

The new strict adapter:

- sends one raw HTTP request to the frozen DashScope Chat Completions endpoint;
- requests exactly `qwen3.5-plus` and rejects aliases, suffixes and endpoint
  overrides;
- places `enable_thinking=false` at the top level of the direct JSON body;
- requires JSON Object mode, temperature 0, non-streaming output and the
  existing per-pass output ceiling;
- performs no redirect, retry, repair, fallback or model substitution;
- reads cached input only from
  `usage.prompt_tokens_details.cached_tokens`;
- validates prompt, completion and total-token arithmetic before admitting
  semantic content;
- uses the committed conservative Qwen peak-tier price basis with environment
  overrides disabled; and
- persists no credential or rejected semantic response.

A parseable model-identity failure may retain only its safe returned model and
validated usage. A potentially spending call without inspectable accounting
keeps the whole execution cost `uninspectable`, never zero.

The runner now selects its provider explicitly. Live CLI execution refuses to
start without `--judge-provider deepseek|qwen`; historical dry-run behavior
still defaults to DeepSeek. Qwen provider, model, API base, exact request
endpoint and request schema reach the pre-call manifest, every call journal
and schema-3 execution artifact. The execution model rejects a schema/provider
mismatch. `pipeline_worker.py` imports neither provider judge nor this runner.

## Zero-network evidence

The real Qwen dry-run verified:

- 8/8 W development cases;
- 64/64 candidate identities;
- 16 bounded prompt identities;
- every source and provider-specific implementation hash;
- `real_network_calls_performed=false`; and
- `real_model_calls_performed=false`.

The adapter and runner subset passed:

```text
21 passed in 2.08s
```

The complete zero-network suite passed:

```text
1782 passed, 657 subtests passed in 32.86s
```

Latest Ruff and the CI exception-order/unreachable-code Pylint gate also
passed.

## Defect reinjection

Two seam defects were re-injected independently and then reverted.

Removing top-level `enable_thinking=false` made the raw outbound-body test
fail with `KeyError: 'enable_thinking'`. This proves the test observes the
serialized direct-HTTP request rather than an unused configuration field.

Removing the call-journal provider consistency check made the cross-provider
test fail with `Failed: DID NOT RAISE ValueError`. This proves a DeepSeek
response cannot be stored under a Qwen request merely because both values were
individually valid.

Both correct implementations were restored, and the focused tests passed
again.

## Frozen Qwen implementation identities

| Dependency | SHA-256 |
|---|---|
| `qwen_evidence_judge.py` | `6b43ba97049bc51410e9871280b4b67093a09f64290baec360b87abb70a7953e` |
| `evidence_search.py` | `2721debe3bb193b8971f8a89db0f4c91342944cb232f1829c02dd8d3780422d0` |
| `openalex_evidence_set.py` | `413bf6cea1c555c75bd80aaadae720cbf00886974acfdd443643f6a2f75e992c` |
| `openalex_scope_link.py` | `abfb9a6b6af1691411f4ad3689b0f5052c42dfeddfdc30cb2e9e21c7d0ff2667` |
| `openalex_scope_link_unseen.py` | `1e3c0b15c9608cf83b414ee52ac2da7540728149970fa45ab9e6306773ef4749` |
| `token_usage.py` | `884a314cb6dfa9393afb74e71cdf54e77c22404f647772e88d3845ec89a0acac` |

The runner records its own observed hash in each manifest instead of embedding
a recursive digest.

## Next gate

No Qwen v5 provider request occurred during this implementation. A later
W01-W08 development execution requires fresh authorization naming the merged
revision, exact provider/model, maximum 16 sequential calls and a soft USD
stop. W01-W08 remain consumed development evidence; even a pass would authorize
only the separately frozen X01-X08 unseen study.

This work therefore completes the Qwen judge contract, not Tool Calling as a
production feature. The production workflow remains phase-1 zero-call shadow
mode until the experimental source-value and unseen gates justify a separately
reviewed connection.
