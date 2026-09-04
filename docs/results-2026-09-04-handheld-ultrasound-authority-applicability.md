# Handheld-ultrasound authority applicability

- **Date:** 2026-09-04
- **Status:** implemented and zero-network validated
- **Production search/tool effect:** none executed by this study

## Origin

The separately authorized RTI02 runtime canary completed successfully, but its
report audit classified this topic as outside the clinical-authority scope:

> AI-assisted handheld ultrasound for heart-failure screening in rural clinics
> commercialization

The resulting authority-coverage state was `not_applicable`, even though the
report treated the product as a diagnostic medical device and discussed
FDA-cleared competitors. This was a deterministic applicability error, separate
from RTI02's runtime-integrity question and from source truth.

The corpus census and acceptance criteria below were completed before editing
the detector in this working branch. Because the plan and implementation enter
Git history together, this document is not an independently timestamped
pre-registration or a held-out evaluation.

## Before-change measurement

The existing detector was replayed over 110 preserved completed reports:

- 30 reports under `outputs/benchmark/`;
- 79 timestamped production or development outputs; and
- the separately named RTI02 output.

Those reports represented 73 unique normalized topics. Before the change the
weight-profile counts were:

| Profile | Reports |
|---|---:|
| material_science | 54 |
| biomedical | 31 |
| industrial | 14 |
| software_ai | 7 |
| clean_tech | 4 |

Twenty-two reports required at least one clinical-authority category. RTI02 was
the only preserved report containing either `handheld ultrasound` or
`ultrasound`.

Broader candidate markers were rejected before implementation:

- `clinical` occurred in seven reports across five unique topics and would
  newly require authority evidence for six reports;
- `screening` occurred in three reports across three unique topics and would
  newly require authority evidence for one report; and
- bare `ultrasound` is not product-specific: it also describes industrial
  inspection, cleaning, extraction, and processing.

Those phrases therefore had a higher false-positive surface than the exact
product phrase observed in RTI02.

## Narrow rule

The exact phrase `handheld ultrasound` now:

1. selects the biomedical scoring/search profile;
2. requires official regulator evidence; and
3. does **not** invent a universal clinical-trial-registry requirement.

This mirrors the earlier precision-first handling of `blood pressure monitor`.
It does not change the scoring formula, the evidence-confidence floor, or any
blocking guardrail. Evidence-gap Tool Calling remains in zero-call shadow mode;
the change only makes a missing regulator category visible to that existing
gate.

## Acceptance criteria and result

The change had to satisfy all of these conditions:

| Criterion | Result |
|---|---|
| RTI02 becomes biomedical | pass |
| RTI02 requires regulator evidence only | pass |
| RTI02 missing-regulator state reaches the shadow gate as `eligible` | pass |
| Shadow execution remains zero calls | pass |
| All 30 frozen benchmark reports remain unchanged | pass |
| Every other preserved report remains unchanged | pass |
| Generic industrial ultrasound remains nonclinical | pass |

After the change the profile counts are 54 material-science, 32 biomedical, 13
industrial, seven software/AI, and four clean-tech reports. Twenty-three reports
require at least one authority category. Exactly one of 110 reports changed:

`industrial + no requirements -> biomedical + regulatory`

The negative control, `ultrasound-assisted heavy metal recovery for industrial
wastewater`, remains `industrial` with no clinical-authority requirement.

The focused source-pipeline and evidence-gap suite passed 82 tests plus 40
subtests.

The first full-suite run also exposed 11 failures in the v6 failure-diagnostic
test module. Its synthetic fixture generated a mock run from current code and
already rebound that run's source-file hashes and execution observations, but
still compared its manifest against the real historical v6 implementation
identity. Changing any shared dependency therefore broke an otherwise unrelated
synthetic review test. The fixture now binds the exact implementation map
persisted by its synthetic manifest, while a separate assertion keeps the real
v6 constants unchanged. The focused diagnostic module passes 15/15. Removing
only the fixture binding reproduces the original
`v6 implementation identity drifted` rejection. This is test-fixture
decoupling; the historical production-disconnected experiment identity was not
rewritten or accepted under a second hash.

## Defect re-injection

Two separate defects were re-injected after the passing test:

1. Removing the biomedical product marker made all three profile/query,
   authority-coverage, and shadow-boundary tests fail. The topic reverted to
   `industrial` and authority coverage reverted to `not_applicable`.
2. Restoring the biomedical marker but removing only the regulator marker also
   made all three tests fail. The profile remained `biomedical`, while the
   serialized shadow gate changed from `eligible` to `no_gap`.

This second failure matters because it proves the tests cover the delivery
seam, not merely an internal classification field.

Final local verification passed 2,071 zero-network tests plus 678 subtests,
latest Ruff, and the CI-matching narrow Pylint gate. No provider, search, or
model request was made.

## Limits

This is a correction for one observed product phrase, not a general medical
device classifier. The 110-report replay is an in-sample safety census, not an
independent precision or recall estimate. It does not establish regulator
source quality, report correctness, Tool Calling value, or production search
success. New product classes should be measured against preserved topics before
adding another marker; broad words such as `clinical`, `screening`, or
`ultrasound` must not be promoted from this result.

The originating runtime observation remains documented in
[the RTI02 result](results-2026-09-04-runtime-terminal-integrity-post-browser-seam-paid-canary.md).
