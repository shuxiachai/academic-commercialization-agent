"""Read-only sample reports a visitor can open without credentials.

A gated deployment shows nothing until an access code or BYOK keys are
entered, so a first-time visitor had no way to see what a finished report
looks like. These are the committed reports under examples/: static files,
served as they are, with no model, search or storage call behind them.

The list is a fixed allowlist rather than a directory scan. A slug never
becomes a path, so a request cannot reach any other file, and a new example
appears here only when someone decides it should.

Each entry records the pipeline revision and the model the run was made
with. The page says both next to every report, with the date, rather than
letting any output pass for current behaviour or for a measure of accuracy;
the citations in a sample have not been re-verified.

Beside each report is the scorecard its run wrote (`<name>.scores.json`, the
run's commercialization_scores.json as written). A run delivers a report and
a score; the page showed only the first, so a visitor deciding whether to
sign up never saw the verdict, the five dimensions or the reasons. The name
is derived from the report's, not listed: there is one allowlist, and a
scorecard cannot be served for anything that is not on it.

The list says three things from that scorecard and the entry beside each
title: the overall score, the readiness level and the language the report is
in. The samples run from 48.6 to 74.9, which is the tool telling an early
technology from a mature one, and until 2026-11-13 a visitor had to open each
report to see it. They travel with the list, one request, for the reader's
cards and the landing page's list alike; the alternative was a request per
sample from each page. The grade ("Strong", "Early") is not here: the page
computes it with the scorecard's own function, so there is one set of
thresholds.

One sample was run with a decision context, and its entry keeps the four
fields that run was given (`SampleDecision`). Until 2026-11-20 none was, so
no sample showed what the form's decision fields buy: a report that states a
conclusion for the decision-maker, and the card that quotes it (#428). The
conclusion itself is not kept here. It is read from the committed report on
each request (`sample_decision`), by the function that reads a run's, so the
card cannot say something the report on the same page does not.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from academic_agent.decision_verdict import find_verdict
from academic_agent.report_display import conclusion_for_display

_EXAMPLES_ROOT = Path(__file__).resolve().parents[1] / "examples"


@dataclass(frozen=True)
class SampleDecision:
    """The decision context a sample's run was given, as it was entered.

    The four fields that put a run in decision-support mode, in the form's
    order. The gate that permits a conclusion needs all four, so an entry
    that carries this says the run was permitted one, and the report's own
    applicability paragraph says the same (tests/test_samples.py compares).
    """

    asset_description: str
    target_application: str
    decision_owner: str
    decision_type: str


@dataclass(frozen=True)
class Sample:
    slug: str
    file: str
    title: str
    topic: str
    committed: str
    commit: str
    # The model the run was made with; the page says it beside the date and
    # the pipeline revision, so a reader can weigh the report accordingly.
    model: str
    # The language the report is written in, by the name the page's language
    # selector uses. The report's, not the visitor's: a card says it so that
    # nobody opens the one Chinese report expecting English, or the reverse.
    language: str = "English"
    # The sample's name for a reader whose interface is Chinese. A card in
    # the Chinese interface named an English report in English between
    # Chinese labels; the card still says which language the report is in.
    # Empty where the title is already Chinese.
    title_zh: str = ""
    # Set where the run was given a decision context; the page then says what
    # was asked and quotes the conclusion the report states.
    decision: SampleDecision | None = None


SAMPLES: tuple[Sample, ...] = (
    # Live runs of 2026-11-08 from the CLI on the current pipeline, with
    # deepseek-v4-pro: five of the ten held-out topics of the spot check
    # (docs/results-2026-11-08-heldout-spot-check-deepseek-v4-pro*.md), kept
    # verbatim as the writer and reviewer left them. A CLI run carries no
    # decision context, so these have no applicability block; the hyperloop
    # production run below keeps that paragraph on the page.
    Sample(
        slug="continuous-glucose-monitoring",
        file="continuous-glucose-monitoring.md",
        title="Continuous glucose monitoring for diabetes",
        title_zh="糖尿病连续血糖监测",
        topic="continuous glucose monitoring for diabetes",
        committed="2026-11-08",
        commit="9bd948c",
        model="deepseek-v4-pro",
    ),
    Sample(
        slug="robotic-assisted-surgery",
        file="robotic-assisted-surgery.md",
        title="Robotic-assisted surgery",
        title_zh="机器人辅助手术",
        topic="robotic-assisted surgery",
        committed="2026-11-08",
        commit="14a2097",
        model="deepseek-v4-pro",
    ),
    Sample(
        slug="pig-kidney-xenotransplantation",
        file="pig-kidney-xenotransplantation.md",
        title="Pig kidney xenotransplantation",
        title_zh="猪肾异种移植",
        topic="pig kidney xenotransplantation",
        committed="2026-11-08",
        commit="9bd948c",
        model="deepseek-v4-pro",
    ),
    Sample(
        slug="space-based-solar-power",
        file="space-based-solar-power.md",
        title="Space-based solar power",
        title_zh="空间太阳能发电",
        topic="space-based solar power",
        committed="2026-11-08",
        commit="14a2097",
        model="deepseek-v4-pro",
    ),
    Sample(
        slug="uhvdc-transmission-zh",
        file="uhvdc-transmission-zh.md",
        title="特高压直流输电",
        topic="特高压直流输电",
        committed="2026-11-08",
        commit="14a2097",
        model="deepseek-v4-pro",
        language="Simplified Chinese",
    ),
    # Production run of 2026-10-21 (pipeline a8cc424, qwen3.8-27b), kept
    # verbatim: the one-word input, and the one sample with the applicability
    # paragraph a web run gets.
    Sample(
        slug="hyperloop",
        file="hyperloop.md",
        title="Hyperloop",
        title_zh="超级高铁（Hyperloop）",
        topic="hyperloop",
        committed="2026-10-21",
        commit="a8cc424",
        model="qwen3.8-27b",
    ),
    # Local web run of 2026-11-20 (pipeline ab908f9, claude-opus-5-5), the
    # run the README's demo recording shows, kept verbatim: the one sample
    # that was given a decision context, and so the one whose report states a
    # conclusion (DEFER). Last in the list on purpose: the landing page lists
    # the first five, and /samples opens the first.
    Sample(
        slug="perovskite-silicon-tandem",
        file="perovskite-silicon-tandem.md",
        title="Perovskite-silicon tandem solar cells",
        title_zh="钙钛矿-硅叠层太阳能电池",
        topic="perovskite-silicon tandem solar cells",
        committed="2026-11-20",
        commit="ab908f9",
        model="claude-opus-5-5",
        decision=SampleDecision(
            asset_description="Lab-scale perovskite-silicon tandem solar cell technology from a university research group",
            target_application="Utility-scale photovoltaic modules",
            decision_owner="Technology transfer office",
            decision_type="License the technology",
        ),
    ),
)


_BY_SLUG = {sample.slug: sample for sample in SAMPLES}


def _score(value: object, lowest: float, highest: float) -> float | None:
    """`value` when it is a number a card can show, otherwise None."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    # NaN and the infinities are in no range, so this refuses them too.
    return value if lowest <= value <= highest else None


def _card_scores(sample: Sample) -> dict[str, float | None]:
    """The two numbers a card shows, from the scorecard of the sample's run.

    A scorecard that is missing, unreadable or holds something else costs the
    card its numbers and nothing more: the list is still served, and the
    report still opens.
    """
    try:
        scores = read_sample_scores(sample.slug)
    except (KeyError, OSError, ValueError):   # a JSON error is a ValueError
        scores = {}
    return {"overall_score": _score(scores.get("overall_score"), 0, 100),
            "trl_score": _score(scores.get("trl_score"), 1, 9)}


def _summary(sample: Sample) -> dict[str, Any]:
    return {**{key: value for key, value in asdict(sample).items() if key != "file"}, **_card_scores(sample)}


def list_samples() -> list[dict[str, Any]]:
    """Every sample in display order: its entry without the file name (the
    decision context as its four fields, or None), and the overall score and
    readiness level its run's scorecard holds."""
    return [_summary(sample) for sample in SAMPLES]


def sample_summary(slug: str) -> dict[str, Any] | None:
    """One sample's line of `list_samples()`, or None for a name that is not
    listed. For the head of /samples/<slug> (api/crawlers.py), which states
    the same two numbers as the sample's card and must read them the same
    way; it wants one sample, not every scorecard opened to keep one."""
    sample = _BY_SLUG.get(slug)
    return _summary(sample) if sample is not None else None


def read_sample(slug: str) -> str:
    """Return one sample's Markdown.

    Raises KeyError for a slug outside the allowlist and FileNotFoundError
    when an allowlisted file is missing from this deployment (for example an
    image built without examples/). The caller maps both to 404.
    """
    sample = _BY_SLUG[slug]
    return (_EXAMPLES_ROOT / sample.file).read_text(encoding="utf-8")


def read_sample_scores(slug: str) -> dict:
    """Return the scorecard of one sample's run.

    Raises KeyError for a slug outside the allowlist, FileNotFoundError when
    the file is not in this deployment, and ValueError when it is not a JSON
    object. The caller maps all three to 404: the page then shows the report
    without a score, as it did before scorecards were kept.
    """
    sample = _BY_SLUG[slug]
    name = Path(sample.file).with_suffix(".scores.json").name
    scores = json.loads((_EXAMPLES_ROOT / name).read_text(encoding="utf-8"))
    if not isinstance(scores, dict):
        raise ValueError(f"{name} is not a scorecard")
    return scores


def sample_decision(slug: str) -> dict[str, Any]:
    """What one sample's run was asked and what its report states, in the
    shape GET /api/runs/{run_id}/decision answers in.

    `asked` is False, and nothing else is filled, for a sample whose run was
    given no decision context: its report was told to give no conclusion, so
    none is looked for. Otherwise the question is the entry's owner and
    decision, and the conclusion is read from the committed report now
    (decision_verdict.find_verdict) and put in the words the displayed
    report uses, as a run's is. Nothing is stored beside the report.

    Raises KeyError for a slug outside the allowlist and FileNotFoundError
    when the report is not in this deployment; the caller maps both to 404.
    """
    sample = _BY_SLUG[slug]
    if sample.decision is None:
        return {"asked": False, "question": None, "conclusion": None}
    report = read_sample(slug)
    return {
        "asked": True,
        "question": {"decision_owner": sample.decision.decision_owner,
                     "decision_type": sample.decision.decision_type},
        # No language is passed, as none is where the report itself is
        # served for display (GET /api/samples/{slug}): the two must name
        # a section alike for the card's link to find it.
        "conclusion": conclusion_for_display(find_verdict(report), report),
    }
