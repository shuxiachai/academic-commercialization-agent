"""The browser language the smokes open the main app's pages in.

Since 2026-11-21 a first visit opens in the browser's language (i18n.js), and
Chromium under Playwright takes the system's unless a context names one:
"zh-CN" on a machine set to Chinese, "en-US" on CI. A smoke that named none
would read Chinese pages on the first and English ones on the second, and its
assertions are about the English words. Every browser context that can reach
a page built on i18n.js names its locale (tests/test_interface_language.py);
the journeys about the language itself, in language_smoke.py, name theirs.

No Playwright here: tests import the e2e modules without the browser group.
"""

SMOKE_LOCALE = "en-US"
