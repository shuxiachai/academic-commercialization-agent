"""Unique (topic, patent) pairs from saved registries, with title, snippet and page abstract (no network)."""
import hashlib
import html as html_lib
import json
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(ROOT / "src")]
from academic_agent.patent_family import publication_number  # noqa: E402

BATCHES = [Path(b) for b in sys.argv[2].split(",")]
CACHE, OUT = Path(sys.argv[3]), Path(sys.argv[4])


def abstract(number):
    if not number:
        return None
    path = CACHE / (hashlib.sha256(number.encode()).hexdigest()[:24] + ".html")
    if not path.exists():
        return None
    page = path.read_text(encoding="utf-8")
    m = re.search(r'<meta name="DC\.description" content="([^"]*)"', page) or \
        re.search(r'<meta name="description" content="([^"]*)"', page)
    return " ".join(html_lib.unescape(m[1]).split())[:900] if m else None


pairs = {}
for path in sorted(p for b in BATCHES for p in b.glob("*/validated_sources.json")):
    record = json.loads(path.read_text(encoding="utf-8"))
    topic = record.get("display_topic") or record.get("topic")
    for s in record.get("patent_sources", []):
        number = publication_number(s.get("url"))
        key = (record.get("topic"), number or s.get("url"))
        row = pairs.setdefault(key, {"topic": topic, "search_topic": record.get("topic"), "number": number,
                                     "url": s.get("url"), "title": s.get("title"),
                                     "snippet": s.get("evidence_summary"), "abstract": abstract(number),
                                     "runs": []})
        row["runs"].append(f"{path.parent.parent.name}/{path.parent.name}")
rows = sorted(pairs.values(), key=lambda r: (r["search_topic"], r["number"] or ""))
for i, row in enumerate(rows, 1):
    row["pair_id"] = f"D{i:03d}"
OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
print("pairs", len(rows), "| topics", len({r["search_topic"] for r in rows}),
      "| with abstract", sum(r["abstract"] is not None for r in rows))
