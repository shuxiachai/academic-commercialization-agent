# Erratum — academic title gate v1: maintainer check delegated; deployed with two declared changes

**Protocol:** [prereg-2026-10-20-academic-title-gate-v1.md](prereg-2026-10-20-academic-title-gate-v1.md)
(unchanged). **Result:** [results-2026-10-20-academic-title-gate-v1.md](results-2026-10-20-academic-title-gate-v1.md)
(unchanged; supported on the frozen AI labels).

## The maintainer check was not done as registered

The protocol had the maintainer label 21 test rows blind and gated
production on the comparison recomputed with those labels.

On 2026-10-20 the maintainer declined to label. They judged that human
review is not currently more accurate than the AI labels and asked the
assistant to judge. The assistant reviewed the 21 rows with its reasons,
and the maintainer adopted every recommendation.

So the "maintainer labels" are the AI labels: agreement is 21/21 by
construction, and no independent human check exists. The recomputed
comparison equals the primary one, which is supported. The production
decision rests on the AI's reading of a few borderline rows:

| Judgment adopted | Rows | If reversed |
|---|---|---|
| General UAV surveys are not about drone delivery of medical supplies | test-0295, -0298, -0301 | **partial**: precision +2.8, recall −2.4 |
| A carbon capture and storage overview is not direct air capture | test-0262 | supported (+4.5, −0.8) |
| Fermentation for plant-based alternatives is not precision fermentation | test-0390 | supported (+4.5, −0.8) |
| Drones in public health is about medical delivery | test-0299 | supported |
| Low-energy nuclear reaction research is fringe fusion research | test-0343 | supported; reversing it favours R5 |

The UAV-survey judgment is the one that matters. If those three surveys
count as relevant, the comparison falls short of the precision threshold by
0.2 points. It passes again if the low-energy nuclear reaction paper is
also judged off-topic: +3.7 and −1.6.

## Production differs from the registered rule in two declared ways

The academic lanes now gate with `source_pipeline._academic_title_matches`,
a port of `r5_one_matcher`. This covers arXiv, Semantic Scholar, PubMed,
OpenAlex and the Crossref web fallback. Patents keep
`_title_matches_topic`.

`tests/test_academic_title_gate.py` replays all 494 recorded decisions
against the frozen rule.

1. **Anchor guard** (`_academic_anchor_topic`). The user's words anchor the
   gate only when the input has at most six content words and the plan
   keeps at least half of them.
   - **Why:** production receives requests as well as topics. "We are
     building an LLM for scriptwriting; assess its value" came from a
     production run. The plan keeps one of its six words, and under R5 it
     would have rejected every relevant title.
   - **Effect on the replay:** all 43 replayed plans keep at least half,
     so no replayed decision changes.
   - **Untested:** a request-like input now gates on the planned phrase
     with R5's matcher. R5 took that path only for the four Chinese
     inputs; the old gate is not used.
2. **Plural stemmer.** The registered stemmer cut "-es" after any letter,
   so "drones" became "dron" and "interfaces" became "interfac". Now "-es"
   is cut only after s, x, z, ch or sh, and "-ies" becomes "-y".
   - **Effect on development decisions:** none.
   - **Effect on test decisions:** five change, all to accepted. Four are
     relevant titles; one is a general UAV survey.
   - **Test split with this stemmer:** precision 88.5% and recall 81.3%,
     against 88.9% and 78.0% for frozen R5.
   - **Evidence:** this is the exploratory finding from the results note,
     with no validation on fresh data. A test pins the departure to
     exactly these five decisions.

## What to watch

- **Shortage risk.** R5 accepts slightly fewer titles than the old gate:
  104 against 106 on development, 108 against 115 on test. A topic close to
  the academic minimum may now fall back to web search more often, or
  fail the academic shortage check.
- **No TRL effect yet.** None is shown. The protocol's small live check
  (at most eight runs) is the next measurement and needs its own
  registration and the maintainer's go-ahead.
