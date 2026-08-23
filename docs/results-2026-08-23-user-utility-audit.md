# Result: two-round blinded user-utility audit

- **Completed:** 2026-08-23
- **Pre-registration:** [user-utility audit protocol](prereg-2026-08-22-user-utility-audit.md)
- **Model cost:** zero; the audit reused frozen topology-ablation reports

## Decision

The protocol completed, but the pre-registered primary criterion **did not
pass**. The production six-stage report won decision usefulness in 6/10 primary
cases, satisfying the lower bound, but the monolith won 4/10, exceeding the
pre-registered maximum of 2/10. The optional replication round produced the
same 6/10 versus 4/10 split and also failed the criterion. Round 2 is
replication evidence; it does not rescue the failed primary result.

The supported conclusion is narrow: the six-stage report had a modest aggregate
preference and recommendation-acceptance advantage, but this small panel did
not establish that the additional workflow complexity creates a stable
decision-utility advantage.

## Sample and completion

- Five reviewers completed both rounds: 20/20 eligible assignments and no
  exclusions.
- Each of the ten topics was judged once per round by a different reviewer.
- Role mix: one target user, one technical proxy, and three other reviewers.
- Four reviewers declared no generative-AI use. One declared translation or
  clerical assistance only; no substantive AI-generated judgment was counted.
- Both report variants used the same frozen evidence and DeepSeek model family.
  This was not a comparison with ordinary ChatGPT or a human analyst.

The role mix is a material limitation. One target-user reviewer cannot
represent technology-transfer officers, investors, or industry analysts as
populations.

## Outcomes

| Outcome | Round 1: full / monolith / tie | Round 2: full / monolith / tie | Both rounds |
|---|---:|---:|---:|
| Overall preference | 6 / 4 / 0 | 6 / 4 / 0 | **12 / 8 / 0** |
| Decision usefulness | 6 / 4 / 0 | 6 / 4 / 0 | **12 / 8 / 0** |
| Information gain | 2 / 5 / 3 | 3 / 6 / 1 | **5 / 11 / 4** |
| Actionability | 4 / 5 / 1 | 4 / 4 / 2 | **8 / 9 / 3** |

Recommendation-acceptance medians replicated exactly: 3.0/5 for the full
workflow and 2.5/5 for the monolith in both rounds. Median reading time was
16.5 versus 15.5 minutes in Round 1 and 17.5 versus 15.5 in Round 2. Estimated
revision time was 27.5 versus 20 minutes in Round 1 and tied at 22.5 minutes in
Round 2.

Only four of twenty assignments opened any cited source, all by one reviewer;
none checked every citation. The first round gave the full report two
citation-trust preferences, while the replication produced two ties. Both
variants had the same factual-error categories in every checked pair. These
observations are too sparse to support a comparative accuracy or hallucination-
rate claim.

Each variant changed the topic-only decision in one case per round. The study
therefore does not show that either topology more often changes a go/no-go/
defer decision.

## Replication and disagreement

The aggregate 6:4 preference reproduced exactly, but the topic-level result did
not. Only U09 and U10 selected the same topology in both rounds; the preferred
topology reversed for the other eight topics. Per-topic agreement was therefore
**2/10 (20%)**.

| Reviewer | Full preferred | Monolith preferred |
|---|---:|---:|
| R01 | 4 | 0 |
| R02 | 1 | 3 |
| R03 | 1 | 3 |
| R04 | 4 | 0 |
| R05 | 2 | 2 |

This pattern is descriptive, not a causal reviewer-effect estimate: reviewer,
topic, and professional role are confounded in a five-person incomplete-block
design. It does show that the stable 60/40 aggregate must not be presented as
stable superiority for particular technologies.

## Post-return normalization

The raw returned CSV files were preserved locally. Several reviewers used
free-text profile labels, numeric values where pairwise enums were requested,
or NOT_CHECKED where the citation-check field required NONE. Formal copies were
normalized conservatively and each mapping was recorded beside the form.

Two primary-round reviewers required pairwise metrics to be coded from their
written rationales. One replication response contained two A/B values that
contradicted its explicit preference and rationale; those values were coded to
match the prose. A checked-citation response used a numeric trust score and was
coded as a tie because both variants had the same 2_PLUS error category and the
rationale gave no comparative trust basis.

This post-return coding weakens precision and is disclosed rather than hidden.
It does not change the primary pass/fail decision: among primary rows whose
decision-usefulness choices required no interpretation, the monolith already
had three wins, exceeding the pre-registered maximum of two.

## What this result supports

The data support these statements:

- the full workflow received 60% of overall and decision-usefulness preferences
  in each round;
- the monolith more often won information gain across both rounds;
- actionability was close to even;
- the six-stage workflow's pre-registered utility advantage was not
  demonstrated; and
- individual reviewer preference was large enough that more target-user
  replication is needed before making a product-value claim.

The result does **not** establish adoption, ROI, objectively correct investment
decisions, comparative hallucination rates, superiority to ordinary ChatGPT,
or that six agents are necessary. No production prompt, scoring formula, or
workflow topology was changed in response to this audit.

## Next hypothesis, not a shipped conclusion

Reviewer rationales suggest a post-hoc product hypothesis: the full workflow's
evidence boundaries and caution can improve overall trust, while its report
structure may dilute information density and action priority. Before changing
the production report, a separate experiment should pre-register a concise,
decision-first brief derived from the same full evidence and recruit more
actual target users. The present data are development evidence for that
hypothesis, not validation of the proposed solution.
