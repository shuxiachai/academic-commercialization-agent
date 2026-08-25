# Phase 3 fixture identity — preflight erratum

**Date discovered:** 2026-08-25
**Live provider requests before discovery:** **0**
**Cost before discovery:** **USD 0.00**

## What the preflight found

After PR #38 merged, the study owner authorized the separately gated Tavily
compatibility pilot. The mandatory dry-run reproduced all five frozen
collection hashes and all five validated-plan hashes, but reported the raw
manifest SHA-256 as:

`4f216d5a7ad0f44db0b973a10087fc6075ac1a2dddddde0430faf62595ca377f`

The Phase 3 implementation result had instead recorded:

`4ee79ec8295c5e51a14fcef78180788be09aaa5102e8e0c6096e0944528339b2`

The pilot stopped at that discrepancy. No live adapter was constructed, no
output directory was reserved, and no provider request was made.

## Cause

The incorrect value came from a pre-commit working-tree draft. The raw bytes in
Git's first public blob for the manifest have the `4f216d...` SHA-256 above.
Recomputing common line-ending variants did
not reproduce `4ee79e...`: the committed LF bytes hash to `4f216d...`, while a
CRLF conversion hashes to `eb476b...`. The earlier value therefore does not
identify a reproducible repository artifact.

This is an artifact-provenance defect, not evidence that a topic, query,
collection, or validated plan changed. The ten semantic identities remained
byte-for-byte equal to their disclosed values.

## Correction

The first committed manifest blob is now the canonical Phase 3 fixture:

`4f216d5a7ad0f44db0b973a10087fc6075ac1a2dddddde0430faf62595ca377f`

The runner now freezes that value in code and validates it before JSON parsing
or case expansion. Whitespace-only edits therefore fail before adapter
construction or billing. The original implementation-result commit remains in
Git history; this erratum supplements it instead of pretending the incorrect
value was never published.

## Experiment status

At publication, the live-provider pilot remained **not run**. The earlier
authorization applied to revision `5be937e`, whose preflight exposed this
defect, and was not silently carried to a corrected revision.

After the correction merged, the study owner issued a fresh authorization for
deployed revision `adde83d`. The exact five-case run then completed five
requests and five credits at a conservative USD 0.04. See the
[live-provider result](results-2026-08-25-evidence-gap-live-provider-phase3.md).

No other acceptance threshold changes:

- at most five requests and five observed credits;
- conservative cost no greater than USD 0.04;
- complete request, usage, row, quarantine, latency, and trace accounting;
- zero policy-invalid rows entering the evidence delta; and
- human review before any wrong-source or novel-evidence claim.
