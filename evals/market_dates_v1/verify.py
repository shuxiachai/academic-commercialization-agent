"""Check each extracted date against the page as a browser renders it.

    python verify.py <repo> <probe.json> <render cache dir> <out.json>

For every row probe.py dated under should_date(), load the page in headless
Chromium and look for the extracted date, in common written forms, in the
rendered visible text (cached, so reruns load nothing). A row is "verified"
when the date is found. The rest keep a text excerpt for a reader to judge:
the date may simply not be printed on the page, or the page may print a
different one. A printed date one day either side counts as found: pages
render dates in the reader's time zone (here Sydney), metadata in its own.
"""
import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(ROOT / "src")]
from academic_agent import page_dates  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

ROWS = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
CACHE, OUT = Path(sys.argv[3]), Path(sys.argv[4])
CACHE.mkdir(parents=True, exist_ok=True)


def forms(d: date) -> set[str]:
    day, month, short = str(d.day), d.strftime("%B"), d.strftime("%b")
    return {
        d.isoformat(), d.strftime("%Y/%m/%d"), d.strftime("%d/%m/%Y"), d.strftime("%m/%d/%Y"),
        f"{month} {day}, {d.year}", f"{short} {day}, {d.year}", f"{short}. {day}, {d.year}",
        f"{month} {d.strftime('%d')}, {d.year}", f"{short} {d.strftime('%d')}, {d.year}",
        f"{day} {month} {d.year}", f"{day} {short} {d.year}", f"{d.strftime('%d')} {month} {d.year}",
        f"{d.strftime('%d')} {short} {d.year}", f"{d.year}年{d.month}月{d.day}日", f"{d.year}.{d.month:02d}.{d.day:02d}",
    }


def rendered_text(page, url: str) -> str | None:
    cached = CACHE / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".txt")
    if cached.exists():
        text = cached.read_text(encoding="utf-8")
        return None if text == "\0" else text
    text = None
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(2500)
        text = page.evaluate("document.body ? document.body.innerText : ''")[:60000]
    except Exception:  # noqa: BLE001 - an unloadable page is recorded as unrendered
        text = None
    cached.write_text(text if text is not None else "\0", encoding="utf-8")
    return text


results = []
dated = [r for r in ROWS if r["date"] and page_dates.should_date(r["source_type"], r["url"])]
with sync_playwright() as pw:
    browser = pw.chromium.launch()
    context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                             "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
    page = context.new_page()
    for row in dated:
        text = rendered_text(page, row["url"])
        found = date.fromisoformat(row["date"])
        candidates = set().union(*(forms(found + timedelta(days=shift)) for shift in (-1, 0, 1)))
        verified = text is not None and any(form in text for form in candidates)
        results.append({**row, "rendered": text is not None, "verified": verified,
                        "excerpt": None if verified or text is None else " ".join(text.split())[:700]})
    browser.close()

OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
eligible = sum(page_dates.should_date(r["source_type"], r["url"]) for r in ROWS)
print(f"eligible: {eligible} | dated: {len(dated)} | rendered: {sum(r['rendered'] for r in results)} "
      f"| verified: {sum(r['verified'] for r in results)}")
for r in results:
    if not r["verified"]:
        print(f"  {r['date']}  {r['source_type']:18} {r['url'][:90]}")
