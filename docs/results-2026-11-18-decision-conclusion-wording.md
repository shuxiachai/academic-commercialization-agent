# The conclusion a decision-support report states: what the saved reports show

**Date:** 2026-11-18 (UTC).
**Status:** offline measurement on saved reports, plus the one production
report that prompted it, read back from the deployment with the maintainer's
consent (two GET requests; its text is kept out of the repository and no test
quotes it). No search or model request was made.
**Production:** the card, the comparison rows and the PDF card are in the
change that carries this file. No prompt, score or applicability rule changed.

## Why

A production run of 2026-11-18 on perovskite-silicon tandem solar cells was
given all four core fields of the decision context: a technology transfer
office deciding whether to license the technology. Its scope line said the
context "allows a GO / NO-GO for this decision-maker". The report did
conclude, in the last paragraph of its executive summary: "the actor-specific
conclusion is DEFER because module-scale validation, reliability evidence, and
patent/legal clarity remain insufficient…". The decision brief showed a band
and a score, the comparison showed neither the question nor the answer, and
the PDF had no summary at all. The reader who asked the question had to find
the answer in a report of about 38,000 characters.

The writer's contract (`config/tasks.yaml`) already tells it to "conclude with
exactly one of GO, NO_GO, or DEFER for the supplied decision and state the
evidence conditions behind it". It does not say where, or in what form.

## What was measured

`scripts/audits/decision_conclusion_audit.py` reads every
`commercialization_report.md` under `outputs/` and each run's `status.json`.

```
uv run python -m scripts.audits.decision_conclusion_audit outputs --lines
```

`outputs/` is private and not in the repository, so the command reproduces
these figures only on the maintainer's machine.

**Reports and modes.** 1,797 saved reports. **None is in decision-support
mode.** Three record `orientation` (two in the run's status, one more in its
delivered applicability paragraph); 1,794 record no mode, because they predate
the gate (2026-08-26) or were made from the command line, which sets none. The
run above exists only on the deployment. The three decision-context canaries
of 2026-08-26 no longer exist there: each answered 404 on 2026-11-18.

So the saved reports can say what a conclusion is **not**, and nothing about
how decision-support reports word one. For that there is one report, below.

**Lines that use the words.** 400 lines use `GO`, `NO_GO`/`NO-GO` or `DEFER`
in capitals:

| Use | Lines |
|---|---|
| Say that no GO/NO_GO is assessed, in English or Chinese ("Actor-specific GO/NO_GO is not assessed", "不评估 GO/NO_GO") | 374 by pattern, 2 more read by hand |
| A heading over such a statement ("**GO/NO_GO Statement:**", "### GO/NO_GO评估说明") | 5 |
| "GO" as a name: graphene oxide ("GO's 35.53% forecast CAGR", "GO-Ag films"), a product ("Carbyon GO") | 18 by pattern, 1 more read by hand |
| **A conclusion** | **0** |

In lower case the same words are ordinary English and appear as such: "clear
go/no-go criteria at 18-month intervals", "defer to".

**The rule on these reports.** `decision_verdict.find_verdict`, the function
the page and the PDF call, finds a conclusion in **0 of 1,797**. Every one of
those would have been wrong.

## The rule

A conclusion is taken only from a sentence that ties a verdict word to the
conclusion itself:

- a label: "**Decision:** DEFER", "GO/NO_GO Status: NO_GO", "结论：DEFER";
- a statement: "the actor-specific conclusion is DEFER because…", "we
  recommend a NO_GO", "the recommendation is a conditional GO",
  "决策结论为暂缓许可";
- `DEFER` or `NO_GO` alone at the head of a paragraph, list item or
  sub-heading: "**DEFER.** Module-scale validation is not yet…".

and never from: the vocabulary named as a vocabulary ("GO, NO_GO, or DEFER");
a negation ("is not GO", "not assessed"); a conditional or a criterion
("NO_GO if…", "would be GO if…", "whether to DEFER"); a table row; the words in lower case
in prose; a bare `GO` followed by what it names ("GO inks"); the code-owned
applicability paragraph; the reference list, the proofreading notes, a fenced
block. `GO` alone at the head of a line is not taken either: "GO: graphene
oxide" heads a glossary line.

Four conclusions are named: GO, conditional GO ("conditional GO", "GO, subject
to…"), DEFER, NO_GO. Statements that name different ones are reported as
disagreeing, each quoted, none chosen. No statement is reported as "the report
states no clear conclusion".

**Misjudgements found while writing it.** The first draft was run against 37
hand-written sentences (19 that state a conclusion in forms the contract
allows, 18 that must not be read as one, most of them lines from the saved
reports). It was wrong twice, both false positives:

| Sentence | Read as | Cause | Now |
|---|---|---|---|
| "The conclusion is that GO-based inks are closer to market than CVD films." | GO | "conclusion is" followed by `GO` within reach | `GO` must end its clause; "is that…" opens a clause, not a verdict |
| "No conclusion is DEFER-able here." | DEFER | the word as part of another | a verdict word is not followed by a hyphen, an apostrophe or a letter |

Three more of the same kind were then written from the saved reports' own
vocabulary, and the rule tightened until it refused them: "We recommend GO
inks for printed sensors", "The recommendation is GO films over CVD graphene",
"**GO**: graphene oxide".

Putting each guard's defect back, one at a time, then showed five guards
that no test sentence reached: removing them changed no result. A sentence
was written for each: "The decision is GO, NO_GO, or DEFER for the committee
to make" (the vocabulary as a list after a tie); "**Conclusion:** a DEFER is
not given for an unspecified actor" (a negation after a labelled word); the
"DEFER-able" sentence above, which had been fixed and then left out of the
tests; "The conclusion is that a NO_GO would be premature at this stage" (a
clause after "is that"); and "**Recommendation:** defer to the registry
record for legal status" (a labelled word that goes on as prose).

The last of these also showed a **miss**: a labelled word in lower or title
case was taken only when punctuation followed it, so "**Decision:** Defer
until module-scale data are available" stated nothing. A labelled word may
now be followed by its reason or its condition ("until", "because",
"pending", "unless"…), not by "to".

**A gate is not a conclusion.** Reading the finished rule against the
writer's contract found one more false positive that no saved report could
show, because none has a conclusion to disagree with. The contract asks every
report for "a gated action plan that names the evidence needed and its
decision criteria", with pass thresholds and stop criteria. A gate written
as "**Gate 2 decision:** NO_GO if outdoor loss exceeds 3% a year" was read as
a NO_GO, and beside the summary's DEFER the card would have said the report
states conclusions that disagree. A verdict word followed by its trigger
("if", "when", "should", "in case", "otherwise", "若", "如果") is now a
criterion. "Until", "unless" and "because" are not triggers: "DEFER until
module data exist" and "NO_GO unless freedom to operate is confirmed"
conclude now. A table's rows are not read as sentences at all.

## The one production report

The run that prompted this (38,089 bytes, decision-support, completed) was
read once the rule was written, so it tested the rule rather than shaped it.

| | |
|---|---|
| The rule's reading | **stated, DEFER** |
| Places it is said | 2, both DEFER: at the end of a long summary sentence about the preferred route, and as a labelled line ("Conclusion: DEFER.") opening the last paragraph of the recommendations |
| What follows the labelled line | one sentence of reasons, one naming what would reopen the decision ("If the owner-confirmed gates above are met…") |
| Its gated plan | six gates as list items ("Gate N — name: obtain…") and a stop-criteria paragraph; none uses a verdict word, none was read |
| Other lines with a verdict word | the code-owned applicability paragraph only |

Two things changed because of it:

- **Which statement is quoted.** The card showed the first place the
  conclusion is said, which here is the summary's sentence about the route.
  The labelled line carries what the reader is after, the reasons and the
  condition, and the contract puts the conclusion in that section. Where a
  report has a line of its own for the conclusion (a label, or the word alone
  at the head of a paragraph), that line is now the one quoted; otherwise the
  first place. Every place is still listed.
- **A miss it nearly had.** Writing that report's shape in other words for a
  test ("In decision-support mode the preferred route is…; however, the
  conclusion is DEFER…") stated nothing: the rule tried only the first
  noun-and-"is" in a sentence, and "decision" in "decision-support" came
  first. The report itself writes "decision_support", one word, and so was
  read. Every tie in a sentence is now tried.

`tests/test_decision_verdict.py` now holds 27 sentences that state a
conclusion and 37 that do not, and all 64 are read as intended, with whole
reports for a gated plan beside its conclusion and for a conclusion said
twice. The rule still finds a conclusion in 0 of the 1,797 saved reports.

## What this does not show

- **Recall is one for one, which is not a measurement.** A single
  decision-support report exists to read, from one model, and the rule takes
  its conclusion. How other models and other reports word theirs is unknown.
  A report that argues its way to waiting without one of the words ("the
  office should wait for module data") is shown as stating no conclusion.
  That is the intended side to err on, and the card says so rather than
  staying empty.
- **Languages.** English and Chinese forms only. A report in another language
  that translates the verdict word is shown as stating none.
- **The conclusion is not checked.** The card quotes what the report says. It
  does not test whether DEFER follows from the evidence, and the report's
  consistency check does not either.
- **The conditions are the sentences beside the statement**, up to two, as
  written. The gated action plan elsewhere in the report is not parsed.

## A fixed conclusion line: proposed, not done

The contract fixes the vocabulary and leaves the place and the form to the
model, which is why the rule has to recognise several forms and cannot have
its recall measured without paid runs. A fixed line would make reading it
exact.

**Proposal.** Add one item to the writer's decision-output contract, for
decision-support mode only:

> End the Executive Summary with one line of exactly this form:
> `**Decision conclusion:** GO | CONDITIONAL_GO | NO_GO | DEFER — <one sentence with the evidence conditions and their citations>`

and have the reviewer preserve it. The rule above would then read that line
first and fall back to the present forms for reports written before the
change.

**Why it is not in this change.** It is a prompt change to the writer, and the
project measures those before adopting them:

- It adds a fourth code (`CONDITIONAL_GO`) to a contract that names three.
  Whether models then spread DEFER cases over it is a behaviour to measure,
  not assume.
- The line is one more thing the writer's guardrail and the reviewer can
  reject or rewrite; the cost in second calls is unknown.
- A model may write the line and a different conclusion in the body. The
  rule reports disagreement, but how often it happens needs runs.

**What a measurement would be.** A pre-registered comparison on
decision-support runs, which do not exist yet in any saved cohort: the ten
held-out topics each with one complete decision context, both arms on the
production model. Read per arm: runs completed, a conclusion found by the
rule, the line present and well-formed (candidate arm), conclusions that
disagree within a report, guardrail second calls, tokens. Twenty runs at about
100,000 tokens each. It needs a budget and a model, which are the
maintainer's to give.

Until then the page states the limit in place: a report with no recognisable
statement gets a card that says "The report states no clear conclusion" and
sends the reader to its recommendations.
