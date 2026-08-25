# Preregistration: Phase 3 evidence-gap human value review

**Registered:** 2026-08-25, before any candidate received a human label

**Network and provider budget:** zero requests; zero incremental cost

**Production status:** disconnected before, during, and after this review

## Frozen question

The completed live-provider pilot established that one bounded Tavily request
per frozen evidence gap can return candidates that survive the existing URL,
domain, SSRF, deduplication, and source-registration boundary. It did not
establish whether those accepted candidates were substantively relevant or
added evidence that the frozen source collection lacked.

This review asks two exploratory questions without making another provider or
LLM request:

1. What fraction of the 25 accepted candidates fail to answer their declared
   evidence gap?
2. In how many of the five cases does at least one candidate provide relevant,
   materially new evidence?

The review does not test planner trigger precision because all five tool intents
were injected fixtures. It therefore cannot authorize a production connection
even if both value thresholds pass.

## Measurement before implementation

The source directory is
`outputs/evidence-gap-phase3-live-20260825-adde83d/`. It contains five cases,
five accepted candidates per case, and 25 blank human-review rows. The original
directory is write-once evidence and must not be edited. Its frozen file hashes
are:

| File | SHA-256 |
|---|---|
| `manifest.json` | `8989acda104e55066b91f42c7f3f78ec33141f440a9f91c6e2b322e315f6c84b` |
| `execution.json` | `2625c20b40d216fb067cbda307880342843ec22d38b76c1ea39e6762ce77b133` |
| `candidates.csv` | `0ba0c36518deff990dd36bf3c9a212aa1e61860c54bd0dd4ad273f5f50b762a5` |
| `review.csv` | `3eaee269f838c4d5b36a4dc16d1c797a713c9c95f2635c572686e8312020d52d` |

The review tool must copy candidate identities into a separate packet and keep
the source hashes in that packet's manifest. It must never write into the
source directory.

## Frozen cases and relevance target

Relevance is judged against the declared gap, not loose keyword overlap with
the broad topic.

| Case | Declared gap | Direct relevance requires |
|---|---|---|
| L01 | academic retrieval failed | Academic performance evidence about engineered cutinases for enzymatic PET textile recycling, rather than generic plastic degradation |
| L02 | patent retrieval failed | Patent claims materially concerning closed-pore hard-carbon anodes for sodium-ion batteries, rather than generic cathodes, electrolytes, or sodium batteries |
| L03 | market retrieval failed | Commercial deployment, adoption, customers, competitors, or market evidence specific to solid-state transformers in medium-voltage data-centre use, rather than a broad transformer forecast |
| L04 | regulatory authority missing | Device-specific FDA clearance or directly applicable regulatory evidence for AI-enabled retinal screening, rather than generic AI-medical-device policy |
| L05 | clinical registry missing | A registered clinical study of a personalised neoantigen mRNA vaccine in pancreatic cancer, rather than another vaccine modality, cancer, or generic registry record |

## Frozen labels

Every accepted candidate receives all three fields. Empty rows are
`incomplete`, never a negative or a pass.

### `relevant`

- `YES`: the opened source directly answers the case's declared gap.
- `NO`: it is generic, adjacent, or mismatched and does not answer that gap.
- `UNVERIFIABLE`: the reviewer attempted the source but could not inspect
  enough content to judge. The reviewer must not guess from the title alone.

### `novel`

- `YES`: a relevant source contributes a material fact, artifact, claim,
  deployment signal, regulatory decision, or trial record absent from the
  frozen pre-run source collection.
- `NO`: a relevant source only duplicates or repackages evidence already in
  that collection.
- `N/A`: required when `relevant=NO`.
- `UNVERIFIABLE`: required when `relevant=UNVERIFIABLE`.

The only valid pairs are therefore `YES/YES`, `YES/NO`, `NO/N/A`, and
`UNVERIFIABLE/UNVERIFIABLE`.

### `review_note`

Every completed row requires a concise source-grounded explanation. It should
name the fact that fills the gap or the specific mismatch. A bare restatement
such as "relevant" or "not relevant" is insufficient.

## Reviewer declaration

The packet uses one reviewer for this exploratory result. A future independent
second review may measure agreement, but it is not silently added to this
protocol after seeing the first result.

The reviewer must declare:

- a name or pseudonym;
- whether every URL was personally attempted;
- generative-AI use as `NONE`, `LANGUAGE_ONLY`, `SOME_SUBSTANTIVE`, or
  `MOST_OR_ALL`;
- elapsed minutes, completion date, optional expertise, and limitations.

`NONE` and `LANGUAGE_ONLY` are eligible for the human-value result.
`SOME_SUBSTANTIVE` or `MOST_OR_ALL` is retained but reported as
`excluded_substantive_ai`; its labels must not become a human-value headline.
Failure to attempt every URL is `not_inspectable`, not a clean review.

## Packet and validation contract

The zero-network tool must:

1. refuse to overwrite an existing packet or result;
2. verify the four source artifacts and preserve their hashes;
3. join all 25 blank review rows to accepted `candidates.csv` rows;
4. freeze case ID, accepted source ID, title, URL, and a canonical identity
   hash for every row;
5. generate reviewer instructions, a label form, a declaration form, and a
   machine-readable packet manifest;
6. accept reordered rows but reject missing, extra, duplicate, or identity-
   changed rows;
7. distinguish wholly blank rows from partially completed rows;
8. reject invalid label pairs and empty rationales;
9. verify the original source artifacts again during summarization; and
10. write an immutable summary that always keeps
    `production_connection_authorized=false`.

An unavailable source or ineligible declaration must remain distinguishable
from a completed negative judgment.

## Frozen calculations

Headline metrics are calculated only when all 25 rows are inspectable and the
reviewer declaration is eligible.

- `wrong_source_count` is the number of rows with `relevant=NO`.
- `wrong_source_rate = wrong_source_count / 25`.
- A case has novel relevant evidence when at least one of its five rows is
  `relevant=YES` and `novel=YES`.
- `novel_relevant_case_count` is the number of such cases.

The exploratory value thresholds inherited unchanged from the live-pilot
protocol are:

- wrong-source rate no greater than 5%; with 25 rows, at most one wrong source;
  and
- novel relevant evidence in at least 3 of 5 cases.

The result is `pass` only when both conditions hold. It is `fail` when a fully
inspectable, eligible review misses either condition. It is `incomplete`,
`not_inspectable`, or `excluded_substantive_ai` when those states apply; none
of them may be rendered as `pass`.

## Defect-injection requirements

Before merging, tests must be shown to fail when at least these defects are
temporarily restored:

1. an identity-changing label row is accepted; and
2. an `UNVERIFIABLE` row is allowed to produce a headline pass.

Tests also cover missing, extra, and duplicate rows; partial labels; invalid
label pairs; source-artifact drift; both threshold boundaries; declaration
eligibility; output immutability; and the final summary seam.

## Decision after review

If either exploratory threshold fails, the tool adapter remains disconnected
and the failure is analyzed by source domain without relabeling this packet.

If both thresholds pass, production still remains disconnected. A separately
frozen planner study containing positive and negative trigger cases must still
establish at least 90% trigger precision, no more than two actual outbound
requests per run, complete incremental accounting, and zero disabled-path
regression before any feature-flagged production canary is considered.

## Explicit non-claims

This review cannot establish autonomous tool choice, planner recall, report
improvement, source-truth accuracy beyond the inspected rows, production
reliability, latency SLO, adoption, ROI, or permission to merge supplementary
sources into `validated_sources.json`.
