# Isolated Reviewer comparison v1

Three fresh fictional development cases, two complete instruction arms, six
sequential native requests at most. The unchanged draft and real EvidenceReport
serialization are paired; only the full Reviewer agent/task instructions differ.
The instruction roots are `ee0a00e` and `ff5dcee`. Full YAML blocks and Git blob
identities are frozen in `manifest.json`, along with fixture, request, source and
installed dependency identities. Source-code hashes normalize CRLF to LF; fixture,
manifest and request bytes do not. Local `-text` protects the wire snapshots.
Both arms use the real `DecisionContext().crew_inputs()` orientation guidance.
The actual imported evidence/run-spec module origins must resolve inside this
checkout; a different editable installation is refused before helper use.

The [parent protocol](../../docs/prereg-2026-09-30-reviewer-comparison.md) owns
the acceptance rule. This is direct native instruction testing followed by the
actual `_apply_reviewer_corrections` and `validate_final_report`, plus explicit
length/citation retention checks. It is **not** `make_reviewer_guardrail`, the
complete CrewAI wire, a Writer/Scorer run, or evidence of general correctness.
Missing targets are explicitly incomplete, not a partial success. No semantic
answer-string checks occur in the runner; harmless no-op plans remain valid.

## Preparation and live boundary

Run `uv run python -m evals.reviewer_comparison_v1.runner` for read-only identity.
Default import is standard-library-only. Preparation lazily loads production
schemas with dotenv loading and the shared dotenv file-read seam temporarily
disabled (including Pydantic/Chroma's dotenv_values); both are restored afterward.
The protected path reads no credentials and
performs no network request. Identity output is **not** live authorization.
Preparation checks frozen block hashes and request rendering without historical
Git objects, so shallow CI can exercise it. The live gate additionally verifies
the complete original Git blobs and exact block extraction at both roots;
missing history refuses native execution before any key read. It never fetches.

The parent must finish independent code review, commit this exact content, see
green public CI for that commit and freeze its default identity/body preview.
Only then may the parent supply `--live --expected-commit <full-sha>
--expected-identity <sha256> --reviewed-ci-commit <same-full-sha>`.
The last flag is an operator attestation, not a claim the offline runner queried
or proved CI status. Dirty tracked files, uncommitted inputs, identity drift or
an existing `outputs/reviewer_comparison_v1_native` refuse execution before any
key read. There is no endpoint, fixture, body, output-directory or model override.

After the gate and durable batch claim, only `DASHSCOPE_API_KEY` from the project
`.env` is selected; all other assignments and inherited provider configuration
are ignored, not expanded. File bytes necessarily include neighboring lines,
but no other key is interpreted, logged or persisted. Duplicate, malformed and
control-containing key assignments fail closed. Never publish raw credentials.

The fixed CN endpoint uses httpx 0.28.1, exact `qwen3.5-plus`, non-thinking JSON
Object mode, temperature zero and 1,500 output tokens. No SDK, tools, redirects,
proxy environment, retries, fallback, resume or repair. TLS verification stays on.
Whole response bodies are bounded to 128 KiB; requests to 48 KiB. Decoded payload
keys/values and nested escaped strings are checked for key echo before any raw
response/model/delivery persistence. Malformed envelopes retain only a hash,
safe category and unavailable usage, never unchecked raw bytes. Read/connect/
write timeouts and elapsed checks are bounded, not a hard cancellation deadline
inside a synchronous socket read. Byte limits do not prove token limits.

Each POST follows exclusive request persistence and an append/flush/fsync
reservation. The frozen uncached input/output rates (USD 0.573/3.44 per million)
reserve 16,384 input plus 1,500 output tokens: USD 0.014548032 per request,
USD 0.087288192 for all six, below the USD 0.10 soft budget. This is an estimate,
not tokenizer proof, a provider invoice, or a guaranteed in-flight spending cap.
No unused reservation is recycled. Unknown/malformed usage is unknown, never
zero. Overflow, response-model mismatch, transport/status/parse/application or
persistence faults stop later requests; known usage precedes content checks.
Occupied output remains consumed after failure. File fsync plus exclusive mkdir
does not promise disk-loss safety, directory durability on every filesystem,
distributed ownership, or resistance to an operator deleting the directory.

## Artifacts and judgment

The new output holds the identity/manifest, exact request and bounded response
bytes, exact model JSON text, patch application/error detail, final Markdown,
usage/reservation journal and mechanically complete blind packets. A failed
stream can leave unknown usage and no complete response; its reservation stays.
Provider errors are never printed verbatim. Do not publish raw output by default.

For semantic judging, the parent must rename/shuffle blind packets and remove
ordinal/filename associations before handing off their **contents only** to a
fresh context. Packets contain sources, original draft, actual final and frozen
rubric; no arm, instruction, intermediate finding, correction reason or label.
All first judgments and backend-metadata uncertainty must be retained. Semantic
misses do not trigger model retries. All three candidate deliveries must be
mechanically complete and supported; gain additionally requires at least one
baseline mixed/unsupported to supported pair and no regression. An uncertain
baseline is not a gain. Both arms passing all cases means gain unobserved.

## Offline validation

`uv run pytest -q tests/test_reviewer_comparison_eval.py` runs twelve grouped
tests (including parametrized controls) with intercepted HTTP and socket denial.
No live invocation belongs in tests. Parent owns full-suite/CI and independent
review. Mocks validate the harness and boundaries, not native model quality.

## Archive and maintenance scope

Keep this runner, fixture, manifest and its 64 test controls at the immutable,
reviewed preparation CI commit and retained branch; do not merge the preparation
PR into main. Main receives only qualified method/result documentation linking
that commit. These controls are preparation evidence, not additions to main's
ongoing default maintenance test count. Close the single batch after any outcome;
do not refresh its frozen identities or reopen its output for later maintenance.
