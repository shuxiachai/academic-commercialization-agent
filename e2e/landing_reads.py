"""The reads the landing makes when it is shown before the access check answers.

Since 2026-11-14 a visit to "/" with nothing stored that could sign it in is
shown the landing at once, without waiting for the access check
(app.js ensureAccess). The landing asks for the sample list and for one
sample's scorecard. In these smokes' fixtures the deployment has no accounts,
so the check then puts the landing away; the two reads have gone out by then.

They are part of what the page now does, so the smokes that audit every
request answer them here instead of counting them as unexpected. Only as the
landing sends them: a GET that carries no credential. The landing is shown
only when nothing is stored, so one of these reads with an access code or a
session on it would mean a stored identity went out with a page that was
painted for nobody; that is left to the caller's audit, which fails on it.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # For the annotation only. The rule below is plain Python and is tested
    # where Playwright is not installed (tests/test_smoke_landing_reads.py):
    # the test jobs do not install the browser group.
    from playwright.sync_api import Route

_SAMPLE_SCORES = re.compile(r"/api/samples/[a-z0-9-]+/scores")
_CREDENTIAL_HEADERS = ("x-access-code", "authorization")


def is_landing_read(method: str, path: str, headers: Mapping[str, str]) -> bool:
    """Whether a request is one of the landing's two reads, sent as the landing sends them."""
    if method != "GET" or any(headers.get(name) for name in _CREDENTIAL_HEADERS):
        return False
    return path == "/api/samples" or _SAMPLE_SCORES.fullmatch(path) is not None


def answer_landing_read(route: Route) -> bool:
    """Answer the request if it is one of the landing's reads; say whether it was.

    The list is empty and the scorecard is missing: the landing copes with
    both (tests/js/landing_contract.mjs), and nothing here depends on them.
    """
    request = route.request
    path = request.url.split("?", 1)[0].split("#", 1)[0]
    path = "/" + path.split("/", 3)[3] if path.count("/") >= 3 else path
    if not is_landing_read(request.method, path, request.headers):
        return False
    if path == "/api/samples":
        route.fulfill(status=200, content_type="application/json", body="[]")
    else:
        route.fulfill(status=404, content_type="application/json", body=json.dumps({"detail": "No such sample."}))
    return True
