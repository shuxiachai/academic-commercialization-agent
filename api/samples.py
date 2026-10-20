"""Read-only sample reports a visitor can open without credentials.

A gated deployment shows nothing until an access code or BYOK keys are
entered, so a first-time visitor had no way to see what a finished report
looks like. These are the committed reports under examples/: static files,
served as they are, with no model, search or storage call behind them.

The list is a fixed allowlist rather than a directory scan. A slug never
becomes a path, so a request cannot reach any other file, and a new example
appears here only when someone decides it should.

Each entry records the commit that added it. The reports are historical runs
from an earlier pipeline; the page says so next to every one of them rather
than letting an old output pass for current behaviour.
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


SAMPLES: tuple[Sample, ...] = (
    Sample(
        slug="solid-state-batteries-ev",
        file="solid-state-batteries-ev.md",
        title="Solid-state batteries for electric vehicles",
        topic="solid-state batteries for electric vehicles",
        committed="2026-07-19",
        commit="9673a83",
    ),
    Sample(
        slug="perovskite-solar-cells-bipv",
        file="perovskite-solar-cells-bipv.md",
        title="Perovskite solar cells for building-integrated photovoltaics",
        topic="perovskite solar cells for building-integrated photovoltaics",
        committed="2026-07-19",
        commit="9673a83",
    ),
    Sample(
        slug="car-t-therapy-solid-tumors",
        file="car-t-therapy-solid-tumors.md",
        title="CAR-T cell therapy for solid tumors",
        topic="CAR-T cell therapy for solid tumors",
        committed="2026-07-19",
        commit="9673a83",
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
