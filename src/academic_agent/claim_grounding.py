"""Check whether a cited source actually contains what the claim asserts.

`validate_evidence_report` checks structure: IDs are well formed, unique, and
every finding cites one that exists. What it cannot check is whether the cited
source says anything resembling the claim attached to it. A finding reading
"efficiency reached 26.1% [A3]" passes every existing rule while A3 is a paper
about manufacturing cost that never mentions 26.1%, and that is the failure
this system's whole premise depends on not happening.

**This is a screen, not a proof.** Deciding entailment in general needs a
model, which would add a second judge whose mistakes correlate with the first
agent's and whose cost scales with the number of claims. What this module does
instead is check a *necessary condition* on the subclass where a deterministic
answer exists: a claim that states a specific figure, and cites a source whose
text does not contain that figure anywhere, is not supported by that source —
whatever else may be true. High precision on the narrow question beats a
plausible score on the broad one.

**Silence is not disagreement.** Two thirds of the sources in a typical run
carry a search snippet rather than a full abstract, and a snippet is a
fragment by construction: a number missing from it says nothing about whether
the paper contains that number. Reporting those as unsupported would be the
same category error the rest of this codebase keeps running into — an absent
signal read as a negative finding. They are reported as UNVERIFIABLE, counted
separately, and never folded into the unsupported total.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

#: Below this, a summary with no declared provenance is treated as a fragment.
#: Abstracts in this pipeline run 800-2000 characters; search snippets run
#: 150-300. The gap is wide enough that the exact cut hardly matters, and
#: erring high only moves findings into "unverifiable", never into a false
#: accusation.
_SUBSTANTIVE_SUMMARY_CHARS = 400

#: A figure has to be distinctive before its absence means anything. Bare
#: small integers ("3 approaches", "TRL 5", "two of the four") appear in
#: prose constantly and would swamp the signal with noise, so a checkable
#: figure must carry a decimal point, a percent sign, a unit, or be large.
_LARGE_ENOUGH = 1000

# Alphabetic units must end at the token boundary. Without this, ``eur`` at
# the start of "European" turns an ordinary publication year into a currency
# figure; the optional unit group then bypasses the bare-year exclusion below.
_UNIT_PATTERN = (
    r"(?:%|percent|wh/kg|wh/l|mah|kwh|mwh|gwh|kw|mw|gw|mpa|gpa|kpa|"
    r"°c|℃|k|nm|µm|um|mm|cm|km|kg|mg|µg|ug|ml|mol|hz|khz|mhz|ghz|"
    r"usd|eur|billion|million|trillion|bn|yr|years?|months?|cycles?|x)"
    r"(?![A-Za-z])"
)

#: Spellings of the same unit. A claim writing "%" against a source writing
#: "percent" is quoting it; treating those as different units would flag a
#: correct sentence, which costs more here than missing one.
_UNIT_SYNONYMS = {
    "percent": "%", "pct": "%",
    "℃": "°c",
    "um": "µm", "ug": "µg",
    "bn": "billion",
    "yr": "years", "year": "years",
    "month": "months", "cycle": "cycles",
}


def _normalize_unit(unit: str) -> str:
    cleaned = (unit or "").strip().lower().rstrip(".,;:)")
    return _UNIT_SYNONYMS.get(cleaned, cleaned)


_FIGURE_RE = re.compile(
    r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(?:" + _UNIT_PATTERN + r")?",
    re.IGNORECASE,
)

#: Words that turn a following round number into a bound rather than a
#: quotation. "above 100 GPa" is the analyst's threshold, and is a correct
#: sentence when the sources say 120 and 140 — so demanding that 100 appear
#: in a source reports a sound inference as a fabrication. A *precise* figure
#: survives these: "approximately 26.1%" is still quoting 26.1.
_BOUND_QUALIFIERS = re.compile(
    r"(?:above|over|under|below|beyond|exceed(?:s|ing)?|more than|less than|"
    r"fewer than|greater than|at least|at most|up to|within|nearly|almost|"
    r"around|about|approximately|roughly|~|>=|<=|>|<|≥|≤)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClaimCheck:
    """One finding's grounding result."""

    finding_id: str
    claim: str
    source_ids: tuple[str, ...] = ()
    #: Figures stated in the claim and found in at least one cited source.
    grounded: tuple[str, ...] = ()
    #: Figures stated in the claim and absent from every cited source whose
    #: text is substantive enough for absence to mean anything.
    ungrounded: tuple[str, ...] = ()
    #: Why no verdict was possible, when there is none.
    unverifiable_reason: str | None = None

    @property
    def status(self) -> str:
        if self.unverifiable_reason:
            return "unverifiable"
        if self.ungrounded:
            return "ungrounded"
        return "grounded"

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "finding_id": self.finding_id,
            "status": self.status,
            "claim": self.claim[:300],
            "source_ids": list(self.source_ids),
        }
        if self.grounded:
            data["grounded_figures"] = list(self.grounded)
        if self.ungrounded:
            data["ungrounded_figures"] = list(self.ungrounded)
        if self.unverifiable_reason:
            data["unverifiable_reason"] = self.unverifiable_reason
        return data


@dataclass(frozen=True)
class GroundingReport:
    checks: tuple[ClaimCheck, ...] = ()
    #: Findings with a figure absent from every checkable cited source.
    ungrounded_count: int = 0
    #: Findings carrying a checkable figure that a verdict could be reached on.
    checked_count: int = 0
    #: Findings skipped: no figure to check, or no substantive source text.
    unverifiable_count: int = 0
    #: Exact repeated claim/source occurrences excluded from the counts above.
    duplicates_collapsed: int = 0
    error: str | None = field(default=None)

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "checked": self.checked_count,
            "ungrounded": self.ungrounded_count,
            "unverifiable": self.unverifiable_count,
            "duplicates_collapsed": self.duplicates_collapsed,
            # Only the interesting rows. A run with 40 fully grounded findings
            # should produce a short file, or nobody will open it.
            "findings": [c.as_dict() for c in self.checks if c.status != "grounded"],
        }
        if self.error:
            data["error"] = self.error
        return data


def _normalize_number(raw: str) -> str:
    """'1,250.0' -> '1250'. Thousands separators and trailing zeros are
    formatting, not content, and a claim that writes 26.10% against a source
    that writes 26.1% is quoting the same figure."""
    cleaned = raw.replace(",", "").strip()
    if "." in cleaned:
        cleaned = cleaned.rstrip("0").rstrip(".")
    return cleaned or "0"


def checkable_figures(text: str) -> list[tuple[str, str]]:
    """Distinctive (number, unit) pairs stated in `text`, normalised.

    The unit travels with the number because without it "26.1%" matches a
    source saying "26.1 million" and "100 MW" matches "100 kg" — the same
    digits describing unrelated quantities, reported as a verified citation.

    Deliberately conservative: a figure that is not distinctive produces noise
    rather than signal, and a check people learn to ignore is worse than no
    check.
    """
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in _FIGURE_RE.finditer(text or ""):
        raw = match.group(1)
        unit = _normalize_unit(match.group(0)[len(raw):])
        number = _normalize_number(raw)
        try:
            value = float(number)
        except ValueError:
            continue
        # A bare four-digit year is the noisiest thing this could flag. Claims
        # routinely date themselves against the analyst's present ("as of
        # 2026, no commercial product exists") while citing a source from an
        # earlier year, and demanding the year appear in the source would
        # report that ordinary, correct sentence as a fabrication. A figure
        # carrying a unit stays even if it looks like a year: "2024 GWh" is a
        # quantity, not a date.
        if not unit and 1900 <= value <= 2100 and "." not in number:
            continue

        # A round number behind a comparative is a bound the analyst chose,
        # not a figure taken from a source. All three flags this screen
        # produced on the first baseline it was run against were of this
        # shape — "more than 10 years", "above 100 GPa" — and all three were
        # sound sentences. A check that reports correct reasoning as
        # fabrication is one people stop reading.
        if "." not in number and _BOUND_QUALIFIERS.search(text[: match.start()]):
            continue

        distinctive = bool(unit) or "." in number or value >= _LARGE_ENOUGH
        key = f"{number}|{unit}"
        if distinctive and key not in seen:
            seen.add(key)
            found.append((number, unit))
    return found


def _source_is_checkable(source: Any) -> bool:
    """Whether absence of a figure in this source means anything.

    A search snippet is a fragment by construction, so no. The label wins over
    length: a long snippet is still a truncation of something longer, and
    treating it as complete is how "we did not see it" becomes "it is not
    there".
    """
    if getattr(source, "summary_source", None) == "search_snippet":
        return False
    text = str(getattr(source, "evidence_summary", "") or "")
    return len(text) >= _SUBSTANTIVE_SUMMARY_CHARS


def _source_text(source: Any) -> str:
    """Everything the source states, prose and structured fields alike.

    citation_count and published_date are in here because a claim citing them
    is quoting the source, and they live in fields rather than in the summary
    text. Leaving them out produced exactly the false accusation this module
    exists to avoid: "10,614 citations for the 2012 paper" was reported as a
    figure absent from its source, when the source carried it — in a field the
    haystack did not read.
    """
    parts = [str(getattr(source, attr, "") or "")
             for attr in ("title", "evidence_summary", "publisher")]
    for attr in ("citation_count", "published_date"):
        value = getattr(source, attr, None)
        if value is not None:
            parts.append(str(value))
    return " ".join(parts)


def _render(number: str, unit: str) -> str:
    """How a figure is shown back to a reader. The unit is part of the claim,
    so a report saying "26.1 is absent" when the claim said "26.1%" sends the
    reader looking for the wrong thing."""
    return f"{number}{unit}" if unit in {"%", ""} else f"{number} {unit}"


def _supported(number: str, unit: str, present: list[tuple[str, str]],
               haystack: str) -> bool:
    """Whether a cited source states this figure.

    Units must not conflict. Without that, "26.1%" is satisfied by a source
    saying "26.1 million" and "100 MW" by "100 kg" — the same digits attached
    to an unrelated quantity, reported as a verified citation.

    A source figure carrying *no* unit still counts. That is the same rule
    this module applies everywhere else: absence of a unit is not evidence of
    a different one, and refusing it would turn "the source wrote the number
    without repeating the unit" into an accusation of fabrication.
    """
    for source_number, source_unit in present:
        if source_unit and unit and source_unit != unit:
            continue
        # Prefix, not equality: a claim rounding a source's 26.15 to 26.1 is
        # quoting it.
        if source_number == number or source_number.startswith(number):
            return True
    # Last resort for a figure the extractor did not pick up as distinctive on
    # the source side — but only for unitless claims, since a bare substring
    # hit carries no unit to compare.
    return not unit and number in haystack.replace(",", "")


def check_report(report: Any, sources: Any = None) -> GroundingReport:
    """Screen every finding in `report` against the sources it cites.

    Never raises: this runs beside a finished report, and an accounting bug
    here must not destroy the assessment it was auditing.
    """
    try:
        return _check_report(report, sources)
    except Exception as exc:  # noqa: BLE001 - an audit must not fail a run
        return GroundingReport(error=f"{type(exc).__name__}: {exc}"[:200])


def _check_report(report: Any, sources: Any = None) -> GroundingReport:
    pool = list(sources if sources is not None else getattr(report, "sources", None) or [])
    by_id = {str(getattr(s, "source_id", "")): s for s in pool}

    checks: list[ClaimCheck] = []
    ungrounded = checked = unverifiable = duplicates_collapsed = 0
    seen_claims: set[tuple[str, tuple[str, ...]]] = set()

    for finding in getattr(report, "findings", None) or []:
        claim = str(getattr(finding, "claim", "") or "")
        cited_ids = tuple(getattr(finding, "source_ids", None) or ())
        figures = checkable_figures(claim)

        if not figures:
            # Nothing deterministic to check. Not a pass and not a failure —
            # this screen simply has no opinion about a purely qualitative
            # claim, and saying so beats implying it was verified.
            continue

        # One production evidence agent repeated five numeric findings later
        # in the same output. The reliability panel counted all 19 positions
        # even though they represented only 14 distinct assertions. Collapse
        # only byte-for-byte claim text with the same source set: fuzzy prose
        # matching would risk merging two legitimately separate estimates,
        # which is worse than leaving a near-duplicate visible.
        duplicate_key = (claim, tuple(sorted(set(cited_ids))))
        if duplicate_key in seen_claims:
            duplicates_collapsed += 1
            continue
        seen_claims.add(duplicate_key)

        cited = [by_id[i] for i in cited_ids if i in by_id]
        checkable = [s for s in cited if _source_is_checkable(s)]

        if not cited:
            checks.append(ClaimCheck(
                finding_id=str(getattr(finding, "finding_id", "")), claim=claim,
                source_ids=cited_ids,
                unverifiable_reason="cites no source present in the registry",
            ))
            unverifiable += 1
            continue

        if not checkable:
            checks.append(ClaimCheck(
                finding_id=str(getattr(finding, "finding_id", "")), claim=claim,
                source_ids=cited_ids,
                unverifiable_reason=(
                    "every cited source carries only a search snippet, which is "
                    "a fragment — a figure missing from it is not evidence the "
                    "source lacks it"
                ),
            ))
            unverifiable += 1
            continue

        haystack = " ".join(_source_text(s) for s in checkable)
        present = checkable_figures(haystack)
        hit, miss = [], []
        for number, unit in figures:
            if _supported(number, unit, present, haystack):
                hit.append(_render(number, unit))
            else:
                miss.append(_render(number, unit))

        checks.append(ClaimCheck(
            finding_id=str(getattr(finding, "finding_id", "")), claim=claim,
            source_ids=cited_ids, grounded=tuple(hit), ungrounded=tuple(miss),
        ))
        checked += 1
        if miss:
            ungrounded += 1

    return GroundingReport(
        checks=tuple(checks),
        ungrounded_count=ungrounded,
        checked_count=checked,
        unverifiable_count=unverifiable,
        duplicates_collapsed=duplicates_collapsed,
    )
