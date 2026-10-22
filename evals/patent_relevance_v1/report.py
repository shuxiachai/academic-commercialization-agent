"""Development comparison of patent relevance rules against labelled accepted patents.

    python report.py <repo> <dev_labels.json>

Every labelled pair is a patent the current gate accepted, so a candidate rule
can only remove rows. For each rule this prints how many rows it removes, and
how many of those were labelled off-topic and how many on-topic. No request
is made.
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(ROOT / "src")]
from academic_agent import source_pipeline as sp  # noqa: E402
from academic_agent.patent_family import title_key  # noqa: E402

DATA = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))["pairs"]

# The aliases each topic's runs planned, read from the saved registries.
ALIASES: dict[str, list[str]] = {}
for path in sorted((ROOT / "outputs/benchmark-runs").glob("*/*/validated_sources.json")):
    record = json.loads(path.read_text(encoding="utf-8"))
    ALIASES.setdefault(record["topic"], record.get("search_aliases") or [])


def title(pair):
    return title_key(pair["title"] or "")[0]


def body(pair):
    return (pair["abstract"] or pair["snippet"] or "").lower()


def anchor(pair):
    return sp._academic_anchor_topic(pair["topic"], pair["search_topic"], ALIASES.get(pair["search_topic"], []))


def phrases(pair):
    return [pair["search_topic"], *ALIASES.get(pair["search_topic"], [])]


def r5_title(pair):
    return any(sp._academic_title_matches(title(pair), phrase, anchor(pair)) for phrase in phrases(pair))


def anchor_word(pair):
    core = set(sp._academic_content_words(anchor(pair) or pair["search_topic"]))
    return bool(core & {sp._academic_stem(word) for word in sp._WORD_PATTERN.findall(title(pair))})


def phrase_title(pair):
    return any(sp._academic_phrase_matches(title(pair), phrase) for phrase in phrases(pair))


def r5_title_or_abstract(pair):
    return any(sp._academic_title_matches(text, phrase, anchor(pair))
               for phrase in phrases(pair) for text in (title(pair), body(pair)))


def phrase_title_or_abstract(pair):
    return any(sp._academic_phrase_matches(text, phrase) for phrase in phrases(pair) for text in (title(pair), body(pair)))


def not_a_listing_page(pair):
    return "/assignee/" not in (pair["url"] or "")


RULES = {
    "R5 on the patent title": r5_title,
    "a user word in the title": anchor_word,
    "the planned phrase in the title": phrase_title,
    "R5 on the title or the abstract": r5_title_or_abstract,
    "the planned phrase in the title or the abstract": phrase_title_or_abstract,
    "not an assignee listing page": not_a_listing_page,
}

off = [p for p in DATA if p["label"] == "off_topic"]
print(f"pairs {len(DATA)} | topics {len({p['search_topic'] for p in DATA})} | off-topic {len(off)}")
print("off-topic by topic:", dict(Counter(p["search_topic"] for p in off)))
print(f"\n{'rule':50} {'removed':>8} {'off-topic':>10} {'on-topic':>9}")
for name, rule in RULES.items():
    removed = [p for p in DATA if not rule(p)]
    removed_off = sum(p["label"] == "off_topic" for p in removed)
    print(f"{name:50} {len(removed):>8} {removed_off:>10} {len(removed) - removed_off:>9}")
