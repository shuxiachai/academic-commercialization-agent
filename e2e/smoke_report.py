"""What a browser-smoke failure leaves behind, kept apart from playwright so the
unit tests can import it. A picture of the page says what it looked like; the
JSON beside it says why it may have looked that way: whether the page's own
scripts ran (`data-boot` on the document, set by app.js), which script files
the browser fetched and how each answered, which storage keys existed (names
only), what the console and the page reported, and the HTTP failures the
journey saw. The two CI failures before this existed had identical pictures of
a page that had not booted and nothing else to go on; the first JSON showed
the page's modules answered 429 by the API rate limit.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = PROJECT_ROOT / "output" / "playwright"

_PAGE_FACTS = """() => {
  const hidden = (sel) => { const el = document.querySelector(sel); return el ? el.hidden : null; };
  const keys = (store) => { try { return Object.keys(store); } catch (e) { return "threw: " + e.message; } };
  return {
    url: location.href, readyState: document.readyState, boot: document.documentElement.dataset.boot ?? null,
    hidden: { workbench: hidden("#workbench"), landing: hidden("#landing"), gate: hidden("#gate"),
              byok_badge: hidden("#byok-badge"), code_badge: hidden("#code-badge") },
    storage: { local: keys(localStorage), session: keys(sessionStorage) },
    scripts: performance.getEntriesByType("resource")
      .filter((e) => e.name.includes("/static/js/"))
      .map((e) => ({ name: e.name.split("/static/js/")[1], start: Math.round(e.startTime),
                     end: Math.round(e.responseEnd), size: e.transferSize })),
    runlist_children: document.querySelector("#runlist")?.children.length ?? null,
  };
}"""


def capture_failure(page, notes: dict | None = None, *, root: Path | None = None) -> None:
    """Keep one inspectable browser artifact without dirtying successful runs.

    `page` is a playwright Page, or anything with is_closed(), screenshot()
    and evaluate(). Diagnostics must never replace the original failure, so
    every step here swallows its own errors and says so on stderr.
    """
    if page is None or page.is_closed():
        return
    root = root or ARTIFACT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=root / "browser-smoke-failure.png", full_page=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[browser-smoke] failure screenshot unavailable: {type(exc).__name__}", file=sys.stderr)
    try:
        facts = page.evaluate(_PAGE_FACTS)
    except Exception as exc:  # noqa: BLE001 - the page may be gone; the picture still stands
        facts = {"unavailable": type(exc).__name__}
    try:
        (root / "browser-smoke-failure.json").write_text(
            json.dumps({"page": facts, **(notes or {})}, indent=2, default=str), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"[browser-smoke] failure facts unavailable: {type(exc).__name__}", file=sys.stderr)
