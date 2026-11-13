"""Wait in the page until it has come to rest, kept apart from playwright so the
unit tests can run the script (tests/test_smoke_scroll_wait.py does, in Node).

base.css scrolls smoothly, so a key that moves focus, or follows a link to a
section, starts a scroll that takes a few hundred milliseconds. A journey that
sends its next key too soon is not testing what a reader does.

What this replaces compared window.scrollY with the value its previous look
had left on `window`. The value survived from one key press to the next, so
the first look after a new key found the page where the last key had left it
and called that stillness, in 1.6 ms, before the browser had begun to move.
Enter on a contents link then raced the scroll that was bringing the link into
view, and sometimes the page ended at the link and not at the heading, with
the URL already naming the section: 5 of 40 times on 2026-11-13, replaying the
narrow journey from a direct load, and 4 of 41 CI runs after #376 made that
scroll longer. A reader does not meet this: with keys 20 to 600 ms apart, 0 of
70 jumps were lost. (The scroll being under way is not what loses the jump;
most jumps made in the middle of one arrive. The key has to land within a few
milliseconds of the one before it.)

So the wait:

- keeps nothing between calls: every call takes its own first sample;
- looks once per animation frame and wants FRAMES looks in a row without
  movement, because a page that drew no frame was not seen holding still,
  however much time went by;
- also wants QUIET_MS without movement, because six frames can be over in
  much less than a scroll takes to begin;
- gives up after LIMIT_MS and says what it was looking at: a page still
  moving, a heading that is not in the document, or a heading that came to
  rest somewhere else and how far from the top of the window.

`page.evaluate(COMES_TO_REST, None)` watches the page's scroll position and
resolves with it. `page.evaluate(COMES_TO_REST, "section-3")` watches where
that heading sits in the window and resolves once it rests within NEAR_PX of
the top, which is where a contents link puts it (scroll-margin-top in
samples.css is 24px).
"""
from __future__ import annotations

FRAMES = 6
QUIET_MS = 100
LIMIT_MS = 15_000
NEAR_PX = 64

COMES_TO_REST = (
    "(id) => new Promise((resolve, reject) => {\n"
    f"    const FRAMES = {FRAMES}, QUIET_MS = {QUIET_MS}, LIMIT_MS = {LIMIT_MS}, NEAR_PX = {NEAR_PX};\n"
    """    const read = () => {
        if (id === null) return window.scrollY;
        const heading = document.getElementById(id);
        return heading ? heading.getBoundingClientRect().top : null;
    };
    const there = (value) => id === null || (value !== null && value >= 0 && value <= NEAR_PX);
    const began = performance.now();
    let last = read(), since = began, looks = 0;
    const look = () => {
        const now = performance.now();
        const value = read();
        if (value !== last) { last = value; since = now; looks = 0; } else { looks += 1; }
        const resting = looks >= FRAMES && now - since >= QUIET_MS;
        if (resting && there(last)) { resolve(last); return; }
        if (now - began < LIMIT_MS) { requestAnimationFrame(look); return; }
        const what = id === null ? "The page" : `#${id}`;
        if (!resting) reject(new Error(`${what} was still moving after ${LIMIT_MS} ms.`));
        else if (last === null) reject(new Error(`#${id} was not in the document after ${LIMIT_MS} ms.`));
        else reject(new Error(
            `#${id} came to rest ${last} px from the top of the window, not within ${NEAR_PX} px of it.`));
    };
    requestAnimationFrame(look);
})"""
)
