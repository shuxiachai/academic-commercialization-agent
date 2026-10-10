# Reviewer reason schema probe v1

Offline preparation, not live authorization. This independent stdlib-only
runner does not import or change production schemas, CrewAI, old executors,
closed fixtures or old allowances. The default checks identity only:

```text
uv run python -m evals.reviewer_reason_schema_probe_v1.runner --packet outputs/<private-packet>.json
uv run pytest -q tests/reviewer_reason_schema_probe_checks.py
```

The explicit checks use synthetic keys and intercepted HTTPS sends. Their real
Python child processes exercise exit, deadline, forced termination and pipe
drain without network access. Tests are deliberately outside default `test_*.py`
collection. Keep the repository warning and network guards intact.

`core.py` freezes the three request bodies and strictly validates unrepaired
responses. `worker.py` claims one durable reservation before reading its one
selected literal credential and performs at most one direct HTTPS request.
`runner.py` owns the child, monotonic deadlines, bounded pipes, immutable output
and first-fault stop. The fixed native output is
`outputs/reviewer-reason-schema-probe-native-v1`; an occupied or partial output
cannot be resumed, replaced or retried by this runner.

The private packet binds one observed Beijing workspace endpoint, exact model,
absolute selected credential-file path, literal assignment variable and numeric
rates. Keep this packet, identities, grants and all observations under ignored
`outputs/`. Do not put real workspace identifiers, account screenshots, source
paths, key values or key hashes in public files. Identity-only never opens the
selected credential file, creates native output or launches a network worker.

`--live` is a separately gated future entry, requiring `--grant`,
`--expected-identity` and `--expected-commit`. These must match the final private
packet/runtime/body identity, independent approved source review and successful
CI for the committed source identity. Grant metadata is binding data, not proof
of a human instruction; the operator must first obtain a new explicit grant.
This preparation has no such grant. No live command is supplied for casual use.

Code/source identity excludes the private packet and runtime so public CI can
check the same source; the execution identity includes both. No dependency is
added: the native worker runs with `-I -S -B`, stdlib only, and a minimal parent
environment. HTTPS uses normal certificate validation and direct connection,
without inherited proxy settings, redirects, retries, streaming or fallback.

Request limit is 8 KiB; response limit is 128 KiB plus one-byte overflow probe.
Each slot's wall deadline starts before launch: `min(slot_start + 90,
batch_start + 270)`. Cleanup then allows 5 seconds for terminate/wait and
10 seconds for forced-kill/pipe-drain observation. Physical exit and pipe EOF
are separate facts. Unconfirmed drain closes the batch. These controls are not
an OS sandbox, provider-side cancellation or a hard billing ceiling. Startup
accounting includes Popen duration; a kernel-blocked process creation cannot
be interrupted by Python before it returns a process handle.

Full stdout/stderr are byte-bounded while draining. Raw child errors are never
saved. Response key echoes, including JSON-escaped layers, withhold both content
and digest; only separately parsed numeric usage may survive. Other admitted
responses retain exact bytes as base64 and SHA-256, without trim, normalization,
clipping, repair or model-generated reinterpretation.

See the [implementation preregistration](../../docs/prereg-2026-10-10-reviewer-reason-schema-implementation.md)
for controls, budget assumptions and limits. This is a schema compatibility
probe, not semantic review, adoption evidence or general decoder enforcement.
