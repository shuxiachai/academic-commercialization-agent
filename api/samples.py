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
"""

from __future__ import annotations

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


def list_samples() -> list[dict[str, str]]:
    """Metadata for every sample, in display order. No file is read."""
    return [
        {key: value for key, value in asdict(sample).items() if key != "file"}
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
