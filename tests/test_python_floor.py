"""The Python floor is where it is so that the lock can hold a fixed soupsieve.

soupsieve before 4.0.0 matches a descendant combinator in polynomial time
(GHSA-mmhr-3c5m-f64f, Dependabot alert 81, 2026-11-13). It is in the lock
because crewai-tools asks for beautifulsoup4; nothing in this repository
imports either. Every soupsieve from 3.0.2 on needs Python 3.11.5, so with the
floor at 3.11 the resolver kept 2.10 whatever was asked of it. The floor moved
to 3.11.5 with the upgrade; lowering it again would bring 2.x back the next
time the lock is written, and no test would otherwise say why.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PROJECT = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
_LOCK = tomllib.loads((_ROOT / "uv.lock").read_text(encoding="utf-8"))


def _numbers(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version))


def _floor(specifier: str) -> tuple[int, ...]:
    found = re.search(r">=\s*([\d.]+)", specifier)
    assert found, specifier
    return _numbers(found.group(1))


def test_the_lock_holds_a_soupsieve_with_the_fix():
    held = [package["version"] for package in _LOCK["package"] if package["name"] == "soupsieve"]
    assert len(held) == 1, held
    assert _numbers(held[0]) >= (4, 0, 0), f"soupsieve {held[0]} is before the fix in 4.0.0"


def test_the_python_floor_is_one_that_soupsieve_accepts():
    assert _floor(_PROJECT["project"]["requires-python"]) >= (3, 11, 5)
    assert _floor(_LOCK["requires-python"]) == _floor(_PROJECT["project"]["requires-python"]), (
        "the lock was written for another floor than the project states")


def test_soupsieve_is_still_only_there_for_beautifulsoup():
    # If the project comes to depend on it directly, the note above and the
    # contributor guide's sentence about the floor need another reason.
    askers = sorted(package["name"] for package in _LOCK["package"]
                    if any(dep["name"] == "soupsieve" for dep in package.get("dependencies", [])))
    assert askers == ["beautifulsoup4"], askers
    direct = " ".join(_PROJECT["project"].get("dependencies", []))
    assert "soupsieve" not in direct and "beautifulsoup4" not in direct


def test_the_contributor_guide_states_the_floor():
    guide = (_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    floor = ".".join(str(part) for part in _floor(_PROJECT["project"]["requires-python"]))
    assert f"Python {floor} or later is required" in guide
