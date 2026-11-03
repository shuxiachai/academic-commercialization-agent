"""Candidate title-gate rules, developed on the dev split only.

Every variant tried is kept here and reported, not just the best one.

Idea (from the dev error analysis): the planner expands the user's words
("hyperloop") into a longer search phrase ("Hyperloop high-speed vacuum tube
transportation"). The expansion adds category words (high, speed, power,
transmission) that unrelated titles share, while the user's own words carry the
subject. So a title should contain the user's core words.
"""
import re
import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[2] / "src")]
from academic_agent import source_pipeline as sp  # noqa: E402

_FUNCTION_WORDS = {"for", "the", "and", "of", "in", "on", "to", "with", "via", "from", "into", "by", "a", "an",
                   "its", "their", "as", "at", "or"}
# "-based" compounds ("space-based", "inverter-based") split into a word that
# matches almost any title; treat it like the existing topic stopwords.
_EXTRA_STOPWORDS = {"based"}
_LATIN = re.compile(r"[a-z0-9]+")


def _stem(token):
    for suffix in ("ing", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def _core(display_topic):
    words = _LATIN.findall(display_topic.lower())
    core = {_stem(w) for w in words
            if len(w) >= 3 and w not in _FUNCTION_WORDS and w not in sp._TOPIC_STOPWORDS and w not in _EXTRA_STOPWORDS}
    return core or None


def _title_stems(title):
    return {_stem(w) for w in _LATIN.findall(title.lower())}


def r2_user_words(title, topic, row):
    """R2: the user's core words must appear; one is enough for a one-word topic.

    Accept if the title holds min(2, |core|) of the display topic's core words,
    or if the current rule accepts AND at least one core word is present.
    Topics with no Latin core words (Chinese input) keep the current rule.
    """
    core = _core(row["display_topic"])
    if core is None:
        return sp._title_matches_topic(title, topic)
    hits = len(core & _title_stems(title))
    if hits >= min(2, len(core)):
        return True
    return hits >= 1 and sp._title_matches_topic(title, topic)


def _stem_tokens(text, min_len):
    return [_stem(w) for w in _LATIN.findall(text.lower())
            if len(w) >= min_len and w not in _FUNCTION_WORDS and w not in sp._TOPIC_STOPWORDS
            and w not in _EXTRA_STOPWORDS]


def _match_phrase(title, phrase, adjacency_from=4):
    """source_pipeline._title_matches_topic's logic on stemmed tokens.

    Same thresholds: at least two shared content words, and for phrases of
    four or more content words, an adjacent pair matched in the phrase must
    also be adjacent in the title. Differences: light stemming, so 'farms'
    meets 'farming', and 'based' is not a content word.
    """
    phrase_list = _stem_tokens(phrase, 3)
    phrase_tokens = set(phrase_list)
    if not phrase_tokens:
        return True
    title_list = [_stem(w) for w in _LATIN.findall(title.lower())]
    overlap = phrase_tokens & set(title_list)
    if len(overlap) < 2:
        return False
    if len(phrase_tokens) >= adjacency_from:
        bigrams = set(zip(title_list, title_list[1:], strict=False))
        adjacent = [(a, b) for a, b in zip(phrase_list, phrase_list[1:], strict=False) if a in overlap and b in overlap]
        if adjacent and not any(pair in bigrams for pair in adjacent):
            return False
    return True


def r3_user_phrase(title, topic, row):
    """R3: match the user's own phrase with the production logic.

    One-word input: the word must appear (no generic expansion can qualify).
    Multi-word input: the user's phrase must match by the production rule
    (stemmed), or the expanded topic matches AND one user word is present.
    No Latin words (Chinese input): the current rule, unchanged.
    """
    core = _core(row["display_topic"])
    if core is None:
        return sp._title_matches_topic(title, topic)
    stems = _title_stems(title)
    if len(core) == 1:
        return bool(core & stems)
    if _match_phrase(title, row["display_topic"]):
        return True
    return bool(core & stems) and sp._title_matches_topic(title, topic)


def r4_user_phrase_adjacent3(title, topic, row):
    """R4: R3 with the adjacency guard from three content words, not four.

    Dropping 'based' left 'space-based solar power' with three words, which
    switched the production guard off; 'solar' and 'power' apart then matched
    solar-physics titles. Three-word phrases need the guard as much.
    """
    core = _core(row["display_topic"])
    if core is None:
        return sp._title_matches_topic(title, topic)
    stems = _title_stems(title)
    if len(core) == 1:
        return bool(core & stems)
    if _match_phrase(title, row["display_topic"], adjacency_from=3):
        return True
    return bool(core & stems) and sp._title_matches_topic(title, topic)


def r5_one_matcher(title, topic, row):
    """R5: R4 with the improved matcher everywhere, not the production one.

    The production matcher still counts 'based' and guards adjacency only from
    four words, so R4's second clause let 'power' + 'based' through. R5 uses
    _match_phrase(adjacency_from=3) for the user's phrase, for the expanded
    topic, and for inputs with no Latin words (Chinese), whose expanded English
    topic it matches the same way. Last dev variant: the rule freezes after it.
    """
    core = _core(row["display_topic"])
    if core is None:
        return _match_phrase(title, topic, adjacency_from=3)
    stems = _title_stems(title)
    if len(core) == 1:
        return bool(core & stems)
    if _match_phrase(title, row["display_topic"], adjacency_from=3):
        return True
    return bool(core & stems) and _match_phrase(title, topic, adjacency_from=3)


RULES = {"r2_user_words": r2_user_words, "r3_user_phrase": r3_user_phrase,
         "r4_user_phrase_adjacent3": r4_user_phrase_adjacent3, "r5_one_matcher": r5_one_matcher}
