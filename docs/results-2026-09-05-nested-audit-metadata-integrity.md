# Nested audit metadata integrity — 2026-09-05

## Scope and observation

This is a zero-provider read-path repair based on `27082a7`, not a new paid
canary or evidence of an ongoing Railway incident. The pre-change full suite
passed with **2096 tests and 1102 subtests**.

Before editing, a read-only census found 109 direct historical run directories:
67 readable status files and 42 absent ones. The 30 benchmark directories have
no status files. The new projection was then replayed over those 67 records:
55 non-null fields in the selected contract, **zero rejected fields and zero
changed records**. Most newer checks are absent from this historical sample;
this is compatibility evidence, not comprehensive coverage or an outage rate.

## Reproduced failures and repair

The previous root-file repair did not validate nested summaries. A scalar
`failed_domains` could raise before either HTTP response; scalar audit objects
could fail response-model validation. Dictionary-shaped faults could reach
JavaScript, where a string `unavailable_domains` broke `.join()` before the
report loaded. An empty consistency object instead became a false clean row.

`api/audit_projection.py` validates the display-facing parts of nine fields:
consistency, reviewer quality, quantitative grounding, report audit, authority
coverage, component coverage, source counts, failed domains and evidence-trail
completeness. It checks literal states, required decision-making counters and
list element types without coercing strings or booleans into measurements.
Legacy count-only summaries remain accepted; recorded failure/unavailability
need not pretend to contain successful-screen counters.

The read projection replaces only a malformed field and carries code-owned
names in `audit_metadata_unreadable` through **both status and progress**.
The browser displays that row as unreadable, not passed or historically absent.
Separate valid findings remain visible, including a known failed domain when
source counts in the same row are damaged. A committed terminal, usage facts,
the report and healthy history neighbors remain available. No original status
bytes, detailed audit artifacts, reports or terminal records are rewritten.

## Verification

- 42 malformed-field HTTP cases, nine valid/absent compatibility cases and
  four JavaScript tests were added. Both response models, report access and
  unchanged on-disk bytes are asserted; the existing key-set contract also
  guards against adding a field to only one endpoint.
- The Chromium loopback journey now includes a fourth run with six damaged
  audit summaries beside a valid completed terminal, report and reviewer
  result. All six affected rows must explain the read fault while the report
  remains visible. Browser/network guards observed zero provider requests,
  zero mutation attempts and zero unexpected console/page errors.
- Re-injecting the original raw passthrough made all **42 fault cases fail**.
  Separately removing the progress field made real Chromium fail because
  unreadable consistency was mislabelled as an English-language exclusion.
  Both defects were restored and the browser passed again.
- Final local verification: **2151 tests and 1118 subtests passed**, latest
  Ruff and the project's narrow Pylint passed. Documentation link checks can
  change subtest counts independently of runtime coverage. No assertion was
  weakened and no skip was added. CI is verified separately on the pushed SHA.

## Boundaries retained

This is not a universal schema validator. Unconsumed nested fields, detailed
audit-tab JSON, decision applicability, usage/recovery payload shapes and
auxiliary readers need their own concrete failure reproduction before changes.
It does not establish citation entailment, full source coverage, model quality,
recovery success, distributed ownership or a production SLO. Missing and null
remain historical absence; present invalid selected summaries are explicit
read faults. The API diagnostic is a derived view, not a worker audit result.

Scoring, Guardrail policy, frozen experiments and dependency versions are
unchanged. Production Tool Calling remains zero-call shadow mode; v8's failed
unseen result remains binding. A merge and production deployment need their
separate authorization; no paid rerun is needed to test this read boundary.
