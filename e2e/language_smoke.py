"""The interface language in real Chromium: a first visit, a reader's choice, a switch.

Each journey opens a fresh browser context with its own browser language
(``browser.new_context(locale=...)``, which sets ``navigator.languages`` and
the ``Accept-Language`` header alike) and nothing stored. As in
keyboard_smoke, the server has static files only and the browser answers
every API request, here as the public deployment answers a visitor who is
not signed in: an accounts deployment, so "/" stays on the landing. The
sample list and the scorecard are the committed samples' own (api.samples).
Nothing reaches a provider and nothing is posted.

What is held, each measured on the public site on 2026-11-21 first:

- A first visit from a zh-CN browser opens every page in Chinese: the
  landing, the workbench, the sample reader, the privacy page, and the
  notice a boot that got no answer shows. One from an en-US browser opens
  them in English. Nothing is saved for that guess.
- A reader who chose a language keeps it, whatever the browser says.
- Switching the landing's language redraws, without a reload, the scorecard
  beside the pitch and the first answer under "How long is my data kept?";
  both stayed in the old language until a reload. The screenshot further
  down follows the language too.
- The Chinese title breaks only between its phrases, at desktop and phone
  widths, and never spills out of its column. At 1280 px it broke as
  "输入一篇论文，得到一份带 / 引用的商业化初筛报告。".

The expected words are read from the page's own modules (i18n.js, result.js)
in the language on screen, so this checks that the page says what the
strings say, not a copy of them kept here.
"""

from __future__ import annotations

import json
import re
import sys
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from playwright.sync_api import Page, Route, expect, sync_playwright

from api import samples
from e2e.browser_smoke import PROJECT_ROOT, _serve
from e2e.smoke_report import capture_failure

ACCOUNTS = {"enabled": True, "signup_open": True, "signup": "open", "access_codes": False,
            "password_reset": True, "notices": True, "key_check": False, "contact": None,
            "plan_preview": False, "daily_quota": False}
RETENTION_DAYS = 90
CJK = re.compile(r"[\u4e00-\u9fff]")
# The Chinese title's phrases, as a reader groups it. A line may end after
# any of them and nowhere else.
TITLE_PHRASES = ("输入一篇论文，", "得到一份", "带引用的", "商业化初筛报告。")
TITLE_WIDTHS = (1280, 1440, 1024, 900, 861, 860, 768, 390, 375, 320)
WIDE = {"width": 1280, "height": 900}

_LINES = """() => {
  const h1 = document.querySelector('.landing__pitch h1');
  const walker = document.createTreeWalker(h1, NodeFilter.SHOW_TEXT);
  const lines = []; let top = null; let node;
  while ((node = walker.nextNode())) {
    for (let i = 0; i < node.data.length; i++) {
      if (node.data[i] === '\\u200b') continue;
      const range = document.createRange(); range.setStart(node, i); range.setEnd(node, i + 1);
      const rect = range.getClientRects()[0];
      if (!rect) continue;
      if (top === null || Math.abs(rect.top - top) > rect.height / 2) { lines.push(''); top = rect.top; }
      lines[lines.length - 1] += node.data[i];
    }
  }
  const column = h1.parentElement.getBoundingClientRect();
  const box = h1.getBoundingClientRect();
  return { lines, spills: box.right > column.right + 0.5 || h1.scrollWidth > h1.clientWidth + 0.5,
           wordBreak: getComputedStyle(h1).wordBreak };
}"""

_SAID = """async (key) => (await import('/static/js/i18n.js')).t(key)"""

# The scorecard as result.js draws it now, from the scores the landing reads,
# in the language on screen.
_FRESH_SCORECARD = """async () => {
  const result = await import('/static/js/result.js');
  const scores = await (await fetch('/api/samples/continuous-glucose-monitoring/scores')).json();
  return result.renderScoreSummary(scores).textContent;
}"""


def _json(route: Route, body, status: int = 200, headers: dict | None = None) -> None:
    route.fulfill(status=status, content_type="application/json", headers=headers or {}, body=json.dumps(body))


def _context(browser, base: str, log: dict, *, locale: str, viewport: dict = WIDE, access: str = "landing",
             stored: str | None = None):
    """A first visit's browser: its language, its window, nothing stored but `stored`."""
    context = browser.new_context(locale=locale, viewport=viewport)
    if stored is not None:
        # Written once, before the first page's scripts, as an earlier visit's choice would be.
        context.add_init_script(f"""try {{
          if (!sessionStorage.getItem('smoke-seeded')) {{
            localStorage.setItem('ui-language', {json.dumps(stored)});
            sessionStorage.setItem('smoke-seeded', '1');
          }}
        }} catch {{}}""")

    def intercept(route: Route) -> None:
        request = route.request
        url = urlsplit(request.url)
        path = url.path
        if url.netloc != urlsplit(base).netloc:
            log["unexpected"].append(f"external {request.method} {request.url}")
            route.abort()
        elif request.method != "GET":
            log["unexpected"].append(f"{request.method} {path}")
            route.abort()
        elif path == "/api/access/check":
            if access == "landing":
                _json(route, {"detail": "Sign in.", "accounts": ACCOUNTS}, 401)
            elif access == "told_to_wait":
                _json(route, {"detail": "Too many requests. Slow down and retry shortly."}, 429,
                      {"Retry-After": "10", "X-Error-Code": "rate_limited"})
            else:
                _json(route, {"ok": True})
        elif path == "/api/samples":
            _json(route, samples.list_samples())
        elif re.fullmatch(r"/api/samples/[a-z0-9-]+/scores", path):
            _json(route, samples.read_sample_scores(path.split("/")[3]))
        elif re.fullmatch(r"/api/samples/[a-z0-9-]+", path):
            route.fulfill(status=200, content_type="text/markdown; charset=utf-8",
                          body=samples.read_sample(path.split("/")[3]))
        elif path == "/api/site":
            _json(route, {"retention_days": RETENTION_DAYS, "contact": None, "mail": True, "account_backup_days": 14})
        elif path == "/health":
            _json(route, {"retention_days": RETENTION_DAYS, "active_runs": 0, "active_paid_operations": 0,
                          "max_concurrent": 5})
        elif path in {"/api/runs", "/api/capacity"} or path.startswith("/api/"):
            # The workbench's history and the like: an open deployment with nothing in it.
            _json(route, {"runs": []} if path == "/api/runs" else {"detail": "Not in this fixture"},
                  200 if path == "/api/runs" else 404)
        elif path in {"/", "/samples", "/privacy"} or path.startswith("/static/"):
            route.continue_()
        else:
            log["unexpected"].append(f"GET {path}")
            route.abort()

    context.route("**/*", intercept)
    page = context.new_page()
    page.on("pageerror", lambda error: log["errors"].append(f"{locale}: {error}"))
    return context, page


def _landing(page: Page, base: str) -> None:
    page.goto(base + "/")
    expect(page.locator("#landing")).to_be_visible()
    expect(page.locator("#landing-preview")).to_have_attribute("data-state", "shown")
    expect(page.locator("#landing-retention")).not_to_have_text("")


def _stored(page: Page):
    return page.evaluate("() => { try { return localStorage.getItem('ui-language'); } catch { return 'unreadable'; } }")


def _in(language: str, text: str) -> bool:
    return bool(CJK.search(text)) if language == "zh" else not CJK.search(text)


def _assert_landing_in(page: Page, language: str, label: str) -> dict:
    lang = page.evaluate("document.documentElement.lang")
    assert lang == ("zh-CN" if language == "zh" else "en"), f"{label}: <html lang> {lang}"
    title = page.evaluate(_SAID, "landing_title")
    assert _in(language, title), f"{label}: the strings' title is not in {language}: {title}"
    h1 = page.locator(".landing__pitch h1").text_content()
    assert h1 == title, f"{label}: H1 {h1!r} is not the strings' {title!r}"
    expected_select = "Simplified Chinese" if language == "zh" else "English"
    assert page.locator("#landing-lang").input_value() == expected_select, f"{label}: the select"
    assert page.title() == page.evaluate(_SAID, "brand_full"), f"{label}: tab {page.title()}"
    scorecard = page.locator("#landing-preview .scorecard").text_content()
    assert scorecard == page.evaluate(_FRESH_SCORECARD), f"{label}: the scorecard is not today's in {language}"
    assert _in(language, scorecard.replace("TRL", "")), f"{label}: scorecard {scorecard[:80]!r}"
    retention = page.locator("#landing-retention").text_content()
    assert retention == page.evaluate(_SAID, "byok_retention").replace("{days}", str(RETENTION_DAYS)), \
        f"{label}: retention {retention!r}"
    assert _in(language, retention), f"{label}: retention {retention!r}"
    answer = page.locator('[data-i18n="landing_faq_a1"]').text_content()
    assert answer == page.evaluate(_SAID, "landing_faq_a1") and _in(language, answer.replace("PDF", "").replace("API Key", ""))
    shot = page.locator("#landing-shot").get_attribute("src") or ""
    assert shot.endswith(f"-{language}.png"), f"{label}: screenshot {shot}"
    return {"lang": lang, "h1": h1, "scorecard": scorecard[:60], "retention": retention[:40]}


def _first_visits(browser, base: str, log: dict) -> dict:
    seen = {}
    for locale, language in (("zh-CN", "zh"), ("zh-TW", "zh"), ("en-US", "en"), ("fr-FR", "en")):
        context, page = _context(browser, base, log, locale=locale)
        try:
            _landing(page, base)
            seen[locale] = _assert_landing_in(page, language, f"first visit {locale}")
            assert _stored(page) is None, f"{locale}: the browser's language was saved as a choice"
            # The other pages a visitor reaches from the landing follow the same rule.
            for path, heading in (("/samples", "samples_title"), ("/privacy", None)):
                page.goto(base + path)
                expect(page.locator("html")).to_have_attribute("lang", "zh-CN" if language == "zh" else "en")
                if heading:
                    import_path = "/static/js/samples_i18n.js"
                    said = page.evaluate(f"async () => (await import('{import_path}')).st('{heading}')")
                    expect(page.locator("h1").first).to_have_text(said)
                    assert _in(language, said)
                else:
                    shown = page.locator("[data-lang-block]:visible")
                    expect(shown).to_have_count(1)
                    assert shown.get_attribute("data-lang-block") == language
                    assert _in(language, page.title())
            assert _stored(page) is None
        except Exception:
            capture_failure(page, {"journey": f"first visit {locale}"})
            raise
        finally:
            context.close()

        # The same browser let into the workbench (a deployment without accounts).
        context, page = _context(browser, base, log, locale=locale, access="open")
        try:
            page.goto(base + "/")
            expect(page.locator("html")).to_have_attribute("data-boot", "ready")
            expect(page.locator("#workbench")).to_be_visible()
            expect(page.locator("html")).to_have_attribute("lang", "zh-CN" if language == "zh" else "en")
            said = page.evaluate(_SAID, "compose_title")
            expect(page.locator(".compose__title")).to_have_text(said)
            assert _in(language, said)
            assert page.locator("#ui-lang").input_value() == ("Simplified Chinese" if language == "zh" else "English")
        except Exception:
            capture_failure(page, {"journey": f"workbench {locale}"})
            raise
        finally:
            context.close()

        # A boot the request limiter told to wait says so in the same language (#427).
        context, page = _context(browser, base, log, locale=locale, access="told_to_wait")
        try:
            page.goto(base + "/")
            expect(page.locator("#boot-failure")).to_be_visible()
            expect(page.locator("html")).to_have_attribute("lang", "zh-CN" if language == "zh" else "en")
            for selector in ("#boot-failure-title", "#boot-failure-text", "#boot-failure-retry"):
                text = page.locator(selector).text_content()
                assert text and _in(language, text), f"{locale}: {selector} {text!r}"
        except Exception:
            capture_failure(page, {"journey": f"told to wait {locale}"})
            raise
        finally:
            context.close()
    return seen


def _choices_kept(browser, base: str, log: dict) -> dict:
    seen = {}
    for locale, stored, language in (("zh-CN", "English", "en"), ("en-US", "Simplified Chinese", "zh")):
        context, page = _context(browser, base, log, locale=locale, stored=stored)
        try:
            _landing(page, base)
            seen[f"{locale} chose {stored}"] = _assert_landing_in(page, language, f"{locale} who chose {stored}")
            page.reload()
            _landing(page, base)
            _assert_landing_in(page, language, f"{locale} who chose {stored}, reloaded")
            page.goto(base + "/privacy")
            expect(page.locator("html")).to_have_attribute("lang", "zh-CN" if language == "zh" else "en")
            assert _stored(page) == stored
        except Exception:
            capture_failure(page, {"journey": f"{locale} chose {stored}"})
            raise
        finally:
            context.close()
    return seen


def _switches(browser, base: str, log: dict) -> dict:
    seen = {}
    for locale, start, steps in (("en-US", "en", ("zh", "en")), ("zh-CN", "zh", ("en", "zh"))):
        context, page = _context(browser, base, log, locale=locale)
        try:
            _landing(page, base)
            _assert_landing_in(page, start, f"{locale} before switching")
            page.evaluate("window.__sameDocument = true")
            before = page.locator("#landing-preview .scorecard").text_content()
            for language in steps:
                page.locator("#landing-lang").select_option("Simplified Chinese" if language == "zh" else "English")
                expect(page.locator("html")).to_have_attribute("lang", "zh-CN" if language == "zh" else "en")
                expect(page.locator("#landing-preview")).to_have_attribute("data-state", "shown")
                label = f"{locale} switched to {language}"
                seen[label] = _assert_landing_in(page, language, label)
                assert page.evaluate("window.__sameDocument === true"), f"{label}: the page was reloaded"
                after = page.locator("#landing-preview .scorecard").text_content()
                assert after != before, f"{label}: the scorecard did not change"
                before = after
                assert _stored(page) == ("Simplified Chinese" if language == "zh" else "English")
        except Exception:
            capture_failure(page, {"journey": f"switch {locale}"})
            raise
        finally:
            context.close()
    return seen


def _title_lines(browser, base: str, log: dict) -> dict:
    breaks = set()
    offset = 0
    for phrase in TITLE_PHRASES[:-1]:
        offset += len(phrase)
        breaks.add(offset)
    whole = "".join(TITLE_PHRASES)
    seen = {}
    for width in TITLE_WIDTHS:
        for locale in ("zh-CN", "en-US"):
            # Chosen, not guessed: the title's lines are held apart from the first-visit rule.
            context, page = _context(browser, base, log, locale=locale, viewport={"width": width, "height": 900},
                                     stored="Simplified Chinese" if locale == "zh-CN" else "English")
            try:
                _landing(page, base)
                measured = page.evaluate(_LINES)
                lines = measured["lines"]
                label = f"{locale} at {width}px"
                assert not measured["spills"], f"{label}: the title is wider than its column: {lines}"
                if locale == "zh-CN":
                    assert "".join(lines) == whole, f"{label}: {lines}"
                    ends, at = [], 0
                    for line in lines[:-1]:
                        at += len(line)
                        ends.append(at)
                    assert set(ends) <= breaks, f"{label}: a line ends inside a phrase: {lines}"
                    assert measured["wordBreak"] == "keep-all"
                else:
                    # The English title is left to break at its spaces, as before.
                    assert measured["wordBreak"] == "normal", f"{label}: {measured['wordBreak']}"
                    assert all(line.endswith(" ") for line in lines[:-1]), f"{label}: {lines}"
                seen[label] = lines
            except Exception:
                capture_failure(page, {"journey": f"title lines {locale} {width}"})
                raise
            finally:
                context.close()
    return seen


JOURNEYS = {
    "first_visits": _first_visits,
    "choices_kept": _choices_kept,
    "switches": _switches,
    "title_lines": _title_lines,
}


def main() -> None:
    app = FastAPI()
    reached_server: list[str] = []

    @app.middleware("http")
    async def static_only(request: Request, call_next):
        if request.method not in {"GET", "HEAD"} or request.url.path.startswith("/api/"):
            reached_server.append(f"{request.method} {request.url.path}")
            return JSONResponse({"detail": "No API exists in the language fixture"}, status_code=500)
        return await call_next(request)

    app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "web/static"), name="static")

    @app.get("/")
    def index():
        return FileResponse(PROJECT_ROOT / "web/index.html")

    @app.get("/samples")
    def samples_page():
        return FileResponse(PROJECT_ROOT / "web/samples.html")

    @app.get("/privacy")
    def privacy_page():
        return FileResponse(PROJECT_ROOT / "web/privacy.html")

    # All four by default, as CI runs it; naming some runs only those.
    names = sys.argv[1:] or list(JOURNEYS)
    unknown = set(names) - set(JOURNEYS)
    assert not unknown, f"No such journey: {sorted(unknown)}; choose from {list(JOURNEYS)}"
    log = {"unexpected": [], "errors": []}
    with _serve(app) as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            results = {name: JOURNEYS[name](browser, base, log) for name in names}
        finally:
            browser.close()
    assert not log["unexpected"], log["unexpected"]
    assert not reached_server, reached_server
    assert not log["errors"], log["errors"]
    print(json.dumps({"status": "passed", "browser": "chromium", **results}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
