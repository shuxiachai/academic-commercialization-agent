"""How many saved market sources state a publication date in their own page metadata.

    python probe.py <repo> <batch dir>[,<batch dir>...] <cache dir> <out.json> [<exclude.json>]

Reads the market sources of every run in the batch dirs (validated_sources.json),
skipping any URL listed in <exclude.json> (an earlier probe's output; the test
split passes the development probe here),
fetches each unique URL once (cached by URL hash in <cache dir>, so reruns
make no request), and records what page_dates finds and by which method. No
model or search request is made; the only network access is one GET per page.
"""
import hashlib
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(ROOT / "src")]
from academic_agent import page_dates  # noqa: E402

BATCHES = [Path(part) for part in sys.argv[2].split(",")]
CACHE, OUT = Path(sys.argv[3]), Path(sys.argv[4])
EXCLUDE = {row["url"] for row in json.loads(Path(sys.argv[5]).read_text(encoding="utf-8"))} if len(sys.argv) > 5 else set()
CACHE.mkdir(parents=True, exist_ok=True)

sources = {}
for path in sorted(p for batch in BATCHES for p in batch.glob("*/validated_sources.json")):
    record = json.loads(path.read_text(encoding="utf-8"))
    accessed = date.fromisoformat(record["collected_at"][:10])
    for source in record.get("market_sources", []):
        url = source.get("url")
        if url and url not in sources and url not in EXCLUDE:
            sources[url] = {"url": url, "title": source.get("title"), "source_type": source.get("source_type"),
                            "run": path.parent.name, "accessed": accessed.isoformat()}


def fetch(url):
    cached = CACHE / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".html")
    if cached.exists():
        text = cached.read_text(encoding="utf-8")
        return None if text == "\0" else text
    html = page_dates.fetch_html(url)
    cached.write_text(html if html is not None else "\0", encoding="utf-8")
    return html


with ThreadPoolExecutor(max_workers=8) as pool:
    pages = dict(zip(sources, pool.map(fetch, sources), strict=True))

rows = []
for url, row in sources.items():
    accessed = date.fromisoformat(row["accessed"])
    html = pages[url]
    found, method = (page_dates.date_from_html(html, url, accessed) if html is not None
                     else page_dates.date_from_url(url, accessed))
    rows.append({**row, "fetched": html is not None, "date": found.isoformat() if found else None, "method": method})

OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
by_type = Counter()
dated_by_type = Counter()
for row in rows:
    by_type[row["source_type"]] += 1
    dated_by_type[row["source_type"]] += row["date"] is not None
print("unique market URLs:", len(rows), "| fetched:", sum(r["fetched"] for r in rows),
      "| dated:", sum(r["date"] is not None for r in rows))
print("by method:", dict(Counter(r["method"] for r in rows)))
for kind in sorted(by_type):
    print(f"  {kind:20} {dated_by_type[kind]}/{by_type[kind]} dated")
