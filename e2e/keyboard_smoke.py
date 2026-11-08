"""Keyboard-only journeys in real Chromium: no mouse, no element.click().

Every move between controls and every activation is a key press from
``KEYS`` (Tab, Shift+Tab, Enter, Space, Escape); text goes into fields with
``keyboard.type``. tests/test_keyboard_smoke.py rejects any other way of
driving the page from this file. As in composer_smoke, the server has static
files only and the browser answers every API request, so no paid work can run.

Two journeys, each in the light and the dark scheme:

- Desktop: the access gate keeps focus inside itself, "No code? Use your own
  API keys instead" opens BYOK, the keys are typed in, and a run is submitted
  (the POST is fulfilled in the browser).
- Phone width: signed in with a code, the closed menu's controls are out of the
  Tab order; opening the menu moves focus into it and keeps it there; Escape
  closes it and focus returns to the menu button, and "New analysis" in it
  closes it and focuses the topic.

At every stop the focused control must be on screen and not covered, and its
focus indicator must be visible: between the unfocused and the focused state,
pixels amounting to at least ``RING_MINIMUM`` of a 1 px ring around the control
change by a contrast ratio of 3:1 or more (WCAG's non-text contrast). Measured
in both themes: base.css's 2 px outline scores 1.8 to 2.9, a 1 px border that
turns to the accent colour (the gate's fields, and the composer around the
topic) 0.93 to 0.97, and the translucent 3 px shadow the composer chips had 0.
"""

from __future__ import annotations

import base64
import json
import time
from collections import Counter
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from playwright.sync_api import Page, Route, expect, sync_playwright

from e2e.browser_smoke import PROJECT_ROOT, _serve
from e2e.smoke_report import capture_failure

KEYS = frozenset({"Tab", "Shift+Tab", "Enter", "Space", "Escape"})
RING_MINIMUM = 0.75
WIDE = {"width": 1280, "height": 900}
PHONE = {"width": 390, "height": 844}
CODE = "fixture-keyboard-code"
RUN_ID = "20261104T000000Z-ffffffffffffffffffffffffffffffff"
TOPIC = "keyboard-only fixture topic"

# Which element's box carries the indicator. The composer draws the topic's
# focus on its own border (workbench.css: "Focus is expressed once, by the
# container"), so the textarea is measured by that container.
_INDICATOR = """() => {
  const el = document.activeElement;
  return el && el.matches('.composer__input') ? el.closest('.composer') : el;
}"""

_DESCRIBE = """() => {
  const el = document.activeElement;
  if (!el || el === document.body || el === document.documentElement) return null;
  const label = el.getAttribute('aria-label') || el.textContent || el.getAttribute('placeholder') || '';
  return (el.id ? '#' + el.id : el.tagName.toLowerCase() + '.' + String(el.className).split(' ')[0])
    + ' "' + label.trim().replace(/\\s+/g, ' ').slice(0, 40) + '"';
}"""

# On screen, at least 4 x 4 CSS px, and the topmost element at its centre.
_VISIBLE = """() => {
  const el = document.activeElement;
  const r = el.getBoundingClientRect();
  if (r.width < 4 || r.height < 4) return `is ${r.width}x${r.height} px`;
  if (r.right <= 0 || r.bottom <= 0 || r.left >= innerWidth || r.top >= innerHeight) return 'is off screen';
  const x = Math.min(Math.max(r.left + r.width / 2, 0), innerWidth - 1);
  const y = Math.min(Math.max(r.top + r.height / 2, 0), innerHeight - 1);
  const top = document.elementFromPoint(x, y);
  if (top && top !== el && !el.contains(top)) return `is covered by ${top.id ? '#' + top.id : top.className || top.tagName}`;
  return '';
}"""

# Decodes two PNG screenshots in a blank page (no CSP) and counts the pixels
# whose relative luminance differs by a ratio of 3:1 or more.
_CONTRAST_PIXELS = """async ([a, b]) => {
  const load = async (data) => {
    const img = new Image();
    img.src = 'data:image/png;base64,' + data;
    await img.decode();
    const canvas = document.createElement('canvas');
    canvas.width = img.width;
    canvas.height = img.height;
    const context = canvas.getContext('2d');
    context.drawImage(img, 0, 0);
    return context.getImageData(0, 0, img.width, img.height).data;
  };
  const [x, y] = [await load(a), await load(b)];
  const channel = (v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  const luminance = (d, i) => 0.2126 * channel(d[i]) + 0.7152 * channel(d[i + 1]) + 0.0722 * channel(d[i + 2]);
  let count = 0;
  for (let i = 0; i < x.length; i += 4) {
    const [p, q] = [luminance(x, i), luminance(y, i)];
    if ((Math.max(p, q) + 0.05) / (Math.min(p, q) + 0.05) >= 3) count++;
  }
  return count;
}"""


class Keyboard:
    """The only way this smoke operates the page."""

    def __init__(self, page: Page):
        self.page = page
        self.presses: Counter[str] = Counter()

    def press(self, key: str) -> None:
        assert key in KEYS, key
        self.presses[key] += 1
        self.page.keyboard.press(key)

    def type(self, text: str) -> None:
        self.page.keyboard.type(text)


def _json(route: Route, value: dict, *, status: int = 200) -> None:
    route.fulfill(status=status, content_type="application/json", body=json.dumps(value))


def _settle(page: Page) -> None:
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")


def _slid(page: Page) -> None:
    """Wait for the phone sidebar's slide (a CSS transform transition) to end."""
    page.locator("#sidebar").evaluate("el => Promise.all(el.getAnimations().map(a => a.finished))")


def _focused(page: Page) -> str | None:
    return page.evaluate(_DESCRIBE)


class Audit:
    """Focus checks shared by both journeys, and the numbers they report."""

    def __init__(self, page: Page, scratch: Page, keys: Keyboard, label: str):
        self.page, self.scratch, self.keys, self.label = page, scratch, keys, label
        self.rings: dict[str, float] = {}

    def _shot(self, clip: dict) -> str:
        return base64.b64encode(self.page.screenshot(clip=clip, animations="disabled")).decode()

    def inspect(self) -> str:
        """The focused control is visible and shows a focus ring; returns its name."""
        name = _focused(self.page)
        assert name, f"{self.label}: focus is on the page itself"
        problem = self.page.evaluate(_VISIBLE)
        assert not problem, f"{self.label}: focused {name} {problem}"
        if name in self.rings:
            return name
        indicator = self.page.evaluate_handle(_INDICATOR).as_element()
        box = indicator.bounding_box()
        view = self.page.viewport_size
        clip = {"x": max(0.0, box["x"] - 8), "y": max(0.0, box["y"] - 8)}
        clip["width"] = min(view["width"], box["x"] + box["width"] + 8) - clip["x"]
        clip["height"] = min(view["height"], box["y"] + box["height"] + 8) - clip["y"]
        focused = self._shot(clip)
        # The unfocused state is one Shift+Tab away; Tab comes straight back.
        self.keys.press("Shift+Tab")
        _settle(self.page)
        assert indicator.bounding_box() == box, f"{self.label}: {name} moved when it lost focus"
        unfocused = self._shot(clip)
        # From the first control Shift+Tab wraps to the last one, and Tab
        # then stops on the browser's toolbar before the page's start.
        for _ in range(2):
            self.keys.press("Tab")
            _settle(self.page)
            if _focused(self.page) is not None:
                break
        assert _focused(self.page) == name, f"{self.label}: Tab did not return to {name}"
        changed = self.scratch.evaluate(_CONTRAST_PIXELS, [focused, unfocused])
        ring = changed / (2 * (box["width"] + box["height"]))
        assert ring >= RING_MINIMUM, (
            f"{self.label}: {name} shows no visible focus ring "
            f"({changed} pixels change by 3:1, {ring:.2f} of a 1 px ring; needs {RING_MINIMUM})")
        self.rings[name] = round(ring, 2)
        return name

    def cycle(self, *, inside: str, limit: int = 60) -> list[str]:
        """Tab from the focused control until focus comes back to it.

        Every stop must be inside ``inside``; the only other place focus may
        go is the browser's own toolbar between the end of the page and its
        start, which the page sees as no focused element.
        """
        start = self.inspect()
        stops = [start]
        for _ in range(limit):
            self.keys.press("Tab")
            _settle(self.page)
            name = _focused(self.page)
            if name is None:
                continue
            if name == start:
                return stops
            within = self.page.evaluate("(selector) => document.activeElement.closest(selector) !== null", inside)
            assert within, f"{self.label}: Tab left {inside} for {name}"
            stops.append(self.inspect())
        raise AssertionError(f"{self.label}: Tab never came back to {start}: {stops}")

    def tab_to(self, target: str, *, limit: int = 30) -> None:
        for _ in range(limit):
            if _focused(self.page) and self.page.evaluate("(s) => document.activeElement.matches(s)", target):
                return
            self.keys.press("Tab")
            _settle(self.page)
        raise AssertionError(f"{self.label}: Tab never reached {target}")


def _context(browser, base: str, scheme: str, viewport: dict, log: dict):
    context = browser.new_context(color_scheme=scheme, viewport=viewport)

    def intercept(route: Route) -> None:
        request = route.request
        url = urlsplit(request.url)
        if url.netloc != urlsplit(base).netloc:
            log["unexpected"].append(f"external {request.method} {request.url}")
            route.abort()
        elif request.method == "POST" and url.path == "/api/runs":
            log["posts"].append(request.post_data_json)
            _json(route, {"run_id": RUN_ID, "topic": TOPIC, "state": "running"}, status=202)
        elif request.method != "GET":
            log["unexpected"].append(f"{request.method} {url.path}")
            route.abort()
        elif url.path == "/api/access/check":
            accepted = request.headers.get("x-access-code") == CODE
            _json(route, {"ok": True} if accepted else {"detail": "Fixture code required"},
                  status=200 if accepted else 401)
        elif url.path == "/api/runs":
            _json(route, {"runs": []})
        elif url.path == f"/api/runs/{RUN_ID}":  # a BYOK sidebar lists its runs from these
            _json(route, {"run_id": RUN_ID, "topic": TOPIC, "state": "running"})
        elif url.path == f"/api/runs/{RUN_ID}/progress":
            _json(route, {"run_id": RUN_ID, "topic": TOPIC, "state": "running", "stage": "Agent 1",
                          "steps": [], "artifacts": [], "elapsed_seconds": 3})
        elif url.path == "/health":
            _json(route, {"active_runs": 0, "active_paid_operations": 0, "max_concurrent": 5,
                          "retention_days": 30})
        elif url.path == "/" or url.path.startswith("/static/"):
            route.continue_()
        else:
            log["unexpected"].append(f"GET {url.path}")
            route.abort()

    context.route("**/*", intercept)
    page = context.new_page()
    page.on("pageerror", lambda error: log["errors"].append(str(error)))
    return context, page


def _byok_journey(browser, scratch: Page, base: str, scheme: str, log: dict) -> dict:
    """Gate, BYOK and a submitted run at desktop width, keyboard only."""
    context, page = _context(browser, base, scheme, WIDE, log)
    keys = Keyboard(page)
    audit = Audit(page, scratch, keys, f"desktop/{scheme}")
    try:
        page.goto(base)
        expect(page.locator("#gate")).to_be_visible()
        expect(page.locator("#gate-input")).to_be_focused()
        gate_stops = audit.cycle(inside="#gate")

        audit.tab_to("#gate-to-byok")
        keys.press("Space")
        expect(page.locator("#byok-form")).to_be_visible()
        expect(page.locator("#byok-llm-key")).to_be_focused()
        # The retention sentence comes from /health after the form opens and
        # moves the fields down; measure once it is there.
        expect(page.locator("#byok-retention")).to_contain_text("30")
        byok_stops = audit.cycle(inside="#gate")
        keys.type("fixture-llm-key")
        keys.press("Tab")
        expect(page.locator("#byok-model")).to_be_focused()
        keys.type("fixture-model")
        keys.press("Tab")
        expect(page.locator("#byok-search")).to_be_focused()
        keys.press("Tab")
        expect(page.locator("#byok-search-key")).to_be_focused()
        keys.type("fixture-search-key")
        keys.press("Enter")
        expect(page.locator("#gate")).to_be_hidden()
        expect(page.locator("#byok-badge")).to_be_visible()
        expect(page.locator("#topic")).to_be_focused()

        keys.type(TOPIC)
        # Once the gate is gone the whole page is in play: sidebar, composer,
        # decision context and starters.
        page_stops = audit.cycle(inside="body")
        audit.tab_to("#run-btn")
        keys.press("Enter")
        deadline = time.monotonic() + 5
        while not log["posts"] and time.monotonic() < deadline:
            page.wait_for_timeout(20)
        assert len(log["posts"]) == 1, log["posts"]
        body = log["posts"].pop()
        assert body["topic"] == TOPIC, body
        assert body["llm_api_key"] == "fixture-llm-key" and body["llm_model"] == "fixture-model", body
        assert body["tavily_api_key"] == "fixture-search-key", body
        expect(page.locator("#pane-run")).to_be_visible()
        expect(page.locator("#run-title")).to_have_text(TOPIC)
        expect(page.locator("#runlist")).to_contain_text(TOPIC)
        return {"gate_stops": len(gate_stops), "byok_stops": len(byok_stops), "page_stops": len(page_stops),
                "rings": audit.rings, "presses": dict(keys.presses)}
    except Exception:  # noqa: BLE001 - keep one inspectable artifact, then propagate the real assertion
        capture_failure(page)
        raise
    finally:
        context.close()


def _phone_menu_journey(browser, scratch: Page, base: str, scheme: str, log: dict) -> dict:
    """The phone menu at 390 px: out of the Tab order when closed, and Escape returns focus."""
    context, page = _context(browser, base, scheme, PHONE, log)
    keys = Keyboard(page)
    audit = Audit(page, scratch, keys, f"phone/{scheme}")
    menu = page.locator("#mobile-menu")
    workbench = page.locator("#workbench")
    try:
        page.goto(base)
        expect(page.locator("#gate-input")).to_be_focused()
        keys.type(CODE)
        keys.press("Enter")
        expect(page.locator("#gate")).to_be_hidden()
        expect(page.locator("#topic")).to_be_focused()
        closed_stops = audit.cycle(inside="#main")

        audit.tab_to("#mobile-menu")
        keys.press("Enter")
        expect(workbench).to_have_attribute("data-sidebar-open", "true")
        _slid(page)
        expect(menu).to_have_attribute("aria-expanded", "true")
        assert page.evaluate("() => document.activeElement.closest('#sidebar') !== null"), (
            f"phone/{scheme}: opening the menu left focus on {_focused(page) or 'the page itself'}")
        open_stops = audit.cycle(inside="#sidebar")

        keys.press("Escape")
        expect(workbench).to_have_attribute("data-sidebar-open", "false")
        expect(menu).to_have_attribute("aria-expanded", "false")
        expect(menu).to_be_focused()
        audit.inspect()

        # The sidebar's own toggle closes it too, and focus must not be lost
        # with the sidebar it was in.
        keys.press("Space")
        expect(workbench).to_have_attribute("data-sidebar-open", "true")
        _slid(page)
        audit.tab_to("#collapse-btn")
        keys.press("Enter")
        expect(workbench).to_have_attribute("data-sidebar-open", "false")
        expect(menu).to_be_focused()

        # "New analysis" closes the menu and puts focus in the topic, as it
        # does at desktop width.
        keys.press("Enter")
        _slid(page)
        audit.tab_to("#new-run-btn")
        keys.press("Enter")
        expect(workbench).to_have_attribute("data-sidebar-open", "false")
        expect(page.locator("#topic")).to_be_focused()
        return {"closed_stops": len(closed_stops), "open_stops": len(open_stops),
                "rings": audit.rings, "presses": dict(keys.presses)}
    except Exception:  # noqa: BLE001 - keep one inspectable artifact, then propagate the real assertion
        capture_failure(page)
        raise
    finally:
        context.close()


def main() -> None:
    app = FastAPI()
    reached_server: list[str] = []

    @app.middleware("http")
    async def static_only(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"} or request.url.path.startswith("/api/"):
            reached_server.append(f"{request.method} {request.url.path}")
            return JSONResponse({"detail": "No API exists in the keyboard fixture"}, status_code=500)
        return await call_next(request)

    app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "web/static"), name="static")

    @app.get("/")
    def index():
        return FileResponse(PROJECT_ROOT / "web/index.html")

    log = {"posts": [], "unexpected": [], "errors": []}
    results = {}
    with _serve(app) as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        scratch_context = browser.new_context()
        scratch = scratch_context.new_page()
        try:
            for scheme in ("light", "dark"):
                results[f"desktop_{scheme}"] = _byok_journey(browser, scratch, base, scheme, log)
                results[f"phone_{scheme}"] = _phone_menu_journey(browser, scratch, base, scheme, log)
        finally:
            scratch_context.close()
            browser.close()
    assert not log["unexpected"], log["unexpected"]
    assert not reached_server, reached_server
    assert not log["errors"], log["errors"]
    rings = [ring for result in results.values() for ring in result["rings"].values()]
    presses = Counter()
    for result in results.values():
        presses.update(result["presses"])
    assert set(presses) <= KEYS, presses
    print(json.dumps({
        "status": "passed", "browser": "chromium", "schemes": ["light", "dark"],
        "stops": {name: {key: value for key, value in result.items() if key.endswith("_stops")}
                  for name, result in results.items()},
        "focus_rings_checked": len(rings), "weakest_ring": min(rings), "ring_minimum": RING_MINIMUM,
        "key_presses": dict(sorted(presses.items())), "submitted_runs": 2,
        "api_requests_reaching_server": len(reached_server), "unexpected_requests": len(log["unexpected"]),
        "paid_provider_requests": 0, "page_errors": len(log["errors"]),
    }))


if __name__ == "__main__":
    main()
