# Human-review attestation and provenance correction

**Recorded:** 2026-08-22, after the 81 labels and rationales were completed.

The project owner states that every label and rationale in `labels.csv` was
checked by a human. AI-authorship language in the source packet's reviewer
declaration was accidentally pasted and is superseded by this correction. The
inaccurate declaration is not included in this public result directory; the
completed labels themselves were copied without modification.

This archive therefore describes the result as a **single completed human label
set**. It does not claim an independent expert panel, inter-rater agreement, or
external validation of every patent statement.

## Artifact integrity

The manifest preserves a SHA-256 hash for every reviewed case card. The test
suite verifies those hashes against the current frozen fixtures, then recomputes
`summary.json` from the exact label and case-ID set. This avoids treating CRLF
versus LF newline normalization as a substantive artifact change.

## Interpretation limits

- The labels judge topical relevance from the frozen audit evidence. They do
  not establish patent validity, ownership, enforceability, or freedom to
  operate.
- The accepted-source sample measures precision-like relevance rates, not
  retrieval recall.
- One completed human label set cannot measure reviewer agreement or systematic
  reviewer bias.
- No production filtering rule was selected or changed from this result.
