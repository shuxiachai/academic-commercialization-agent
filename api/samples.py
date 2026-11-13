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
in. The six samples run from 48.6 to 74.9, which is the tool telling an early
technology from a mature one, and until 2026-11-13 a visitor had to open each
report to see it. They travel with the list, one request, for the reader's
cards and the landing page's list alike; the alternative was a request per
sample from each page. The grade ("Strong", "Early") is not here: the page
computes it with the scorecard's own function, so there is one set of
thresholds.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

_EXAMPLES_ROOT = Path(__file__).resolve().parents[1] / "examples"


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
        topic="continuous glucose monitoring for diabetes",
        committed="2026-11-08",
        commit="9bd948c",
        model="deepseek-v4-pro",
    ),
    Sample(
        slug="robotic-assisted-surgery",
        file="robotic-assisted-surgery.md",
        title="Robotic-assisted surgery",
        topic="robotic-assisted surgery",
        committed="2026-11-08",
        commit="14a2097",
        model="deepseek-v4-pro",
    ),
    Sample(
        slug="pig-kidney-xenotransplantation",
        file="pig-kidney-xenotransplantation.md",
        title="Pig kidney xenotransplantation",
        topic="pig kidney xenotransplantation",
        committed="2026-11-08",
        commit="9bd948c",
        model="deepseek-v4-pro",
    ),
    Sample(
        slug="space-based-solar-power",
        file="space-based-solar-power.md",
        title="Space-based solar power",
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
        topic="hyperloop",
        committed="2026-10-21",
        commit="a8cc424",
        model="qwen3.8-27b",
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


def list_samples() -> list[dict[str, str | float | None]]:
    """Every sample in display order: its entry without the file name, and
    the overall score and readiness level its run's scorecard holds."""
    return [
        {**{key: value for key, value in asdict(sample).items() if key != "file"}, **_card_scores(sample)}
        for sample in SAMPLES
    ]


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
