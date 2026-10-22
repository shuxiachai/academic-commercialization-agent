"""Patent family ground truth from Google Patents pages, for saved patent registries.

    python families.py <repo> <batch dir>[,<batch dir>...] <cache dir> <out.json> [<exclude.json>]

Reads every run's patent registry (validated_sources.json) in the batch dirs,
skipping publication numbers listed in <exclude.json> (an earlier output),
derives each patent's publication number from its URL, and fetches its Google
Patents page once (cached by number; robots.txt allows /patent/). From each
page it records the page's own number and its DOCDB family ("Also Published
As") plus the same application's other publications ("Other versions").
Requests are sequential and paced. No model or search request is made.
"""
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(sys.argv[1]).resolve()
BATCHES = [Path(part) for part in sys.argv[2].split(",")]
CACHE, OUT = Path(sys.argv[3]), Path(sys.argv[4])
EXCLUDE = ({row["number"] for row in json.loads(Path(sys.argv[5]).read_text(encoding="utf-8"))["patents"]}
           if len(sys.argv) > 5 else set())
CACHE.mkdir(parents=True, exist_ok=True)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AcademicAgentEvidenceVerifier/1.0)", "Accept": "text/html"}
PACE_SECONDS = 1.5

_KIND = re.compile(r"^([A-Z]{2}\d+?)([A-Z]\d?)?$")
_GOOGLE_NUMBER = re.compile(r"^/patent/([A-Z]{2}\d+[A-Z]?\d?)(?:/|$)")
_WO = re.compile(r"(WO\d{10})")


def number_from_url(url: str) -> str | None:
    """The publication number a saved patent URL points at, kind code kept when present."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host == "patents.google.com":
        match = _GOOGLE_NUMBER.match(parts.path)
        return match[1] if match else None
    if host == "patentscope.wipo.int":
        doc = parse_qs(parts.query).get("docId", [""])[0] or parts.path
        match = _WO.search(doc)
        return match[1] if match else None
    if host == "patents.justia.com":
        match = re.match(r"^/patent/(\d{7,11})(?:/|$)", parts.path)
        return f"US{match[1]}" if match else None
    return None


def bare(number: str) -> str:
    """A publication number without its kind code: US9422922B2 -> US9422922."""
    match = _KIND.match(number)
    return match[1] if match else number


def family_from_page(html: str) -> dict:
    # Applications carry citation_patent_publication_number ("WO:2016093905:A1");
    # granted patents carry citation_patent_number ("US:9855103", no kind code).
    own = re.search(r'<meta name="citation_patent_(?:publication_)?number" content="([A-Z]{2}):([^:"]+):?([^"]*)"', html)
    docdb = [n for row in re.findall(r'<tr itemprop="docdbFamily"[^>]*>(.*?)</tr>', html, re.S)
             for n in re.findall(r'itemprop="publicationNumber">([^<]+)<', row)]
    direct = [n for dd in re.findall(r'<dd itemprop="directAssociations"[^>]*>(.*?)</dd>', html, re.S)
              for n in re.findall(r'itemprop="publicationNumber">([^<]+)<', dd)]
    return {"own": "".join(own.groups()) if own else None, "docdb": docdb, "direct": direct}


def fetch(number: str) -> tuple[str | None, int | None]:
    cached = CACHE / (hashlib.sha256(number.encode()).hexdigest()[:24] + ".html")
    if cached.exists():
        text = cached.read_text(encoding="utf-8")
        return (None, int(text[1:])) if text.startswith("\0") else (text, 200)
    time.sleep(PACE_SECONDS)
    try:
        with urlopen(Request(f"https://patents.google.com/patent/{number}/en", headers=HEADERS), timeout=30) as resp:
            html, status = resp.read().decode("utf-8", errors="replace"), resp.status
    except HTTPError as exc:
        html, status = None, exc.code
    except (URLError, TimeoutError, OSError):
        html, status = None, 0
    cached.write_text(html if html is not None else f"\0{status}", encoding="utf-8")
    return html, status


patents: dict[str, dict] = {}
registries = []
for path in sorted(p for batch in BATCHES for p in batch.glob("*/validated_sources.json")):
    record = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for source in record.get("patent_sources", []):
        number = number_from_url(source.get("url") or "")
        rows.append({"source_id": source["source_id"], "url": source.get("url"), "title": source.get("title"),
                     "number": number})
        if number and number not in EXCLUDE and number not in patents:
            patents[number] = {"number": number, "url": source.get("url"), "title": source.get("title")}
    if any(row["number"] not in EXCLUDE for row in rows):
        registries.append({"batch": path.parent.parent.name, "run": path.parent.name, "patents": rows})

for number, row in patents.items():
    html, status = fetch(number)
    row["status"] = status
    row.update(family_from_page(html) if html is not None else {"own": None, "docdb": [], "direct": []})

OUT.write_text(json.dumps({"patents": list(patents.values()), "registries": registries},
                          ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
read = [r for r in patents.values() if r["own"]]
print(f"registries: {len(registries)} | unique patents: {len(patents)} | pages read: {len(read)} "
      f"| unmapped rows: {sum(r['number'] is None for g in registries for r in g['patents'])}")
print("statuses:", {s: sum(r['status'] == s for r in patents.values()) for s in {r['status'] for r in patents.values()}})
