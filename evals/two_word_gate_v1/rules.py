"""Candidate two-word rules, applied to the rows label_set.py selected.

Every selected row is one the production gate (R5) accepts although the
anchor's two words are not adjacent, in order, in the title. Each rule
returns True to keep the row (as production does) or False to remove it.
The rules only ever remove rows, so they agree with production elsewhere.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src")]
from academic_agent import source_pipeline as sp  # noqa: E402


def _words(text: str) -> list[str]:
    return [sp._academic_stem(w) for w in sp._WORD_PATTERN.findall(text.lower())]


def _within(words: list[str], core: list[str], gap: int) -> bool:
    """The two core words in order, with at most `gap` words between them."""
    first, second = core
    for i, word in enumerate(words):
        if word == first and second in words[i + 1:i + 2 + gap]:
            return True
    return False


def _core(anchor: str) -> list[str]:
    return sp._academic_content_words(anchor)


def w0(row: dict) -> bool:
    """Adjacency: the two words next to each other in the title."""
    return _within(_words(row["title"]), _core(row["anchor"]), 0)


def w1(row: dict) -> bool:
    """One intervening word allowed ("carbon dioxide capture", "tidal stream power")."""
    return _within(_words(row["title"]), _core(row["anchor"]), 1)


def _abstract_rescue(row: dict) -> bool:
    return _within(_words(row.get("abstract") or ""), _core(row["anchor"]), 0)


def w0_abstract(row: dict) -> bool:
    """W0, or the adjacent phrase in the abstract."""
    return w0(row) or _abstract_rescue(row)


def w1_abstract(row: dict) -> bool:
    """W1, or the adjacent phrase in the abstract."""
    return w1(row) or _abstract_rescue(row)


RULES = {"W0": w0, "W1": w1, "W0+A": w0_abstract, "W1+A": w1_abstract}


def anchor_words_present(row: dict) -> int:
    """How many of the two anchor words the title holds (the gate's second path can accept one)."""
    words = set(_words(row["title"]))
    return sum(1 for w in _core(row["anchor"]) if w in words)

