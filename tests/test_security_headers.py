"""Every response the app sends carries the security headers, whoever built it.

Until 2026-11-17 `curl -D - https://academic-agent.cc/api/runs` answered 401
with no Content-Security-Policy, no X-Content-Type-Options, no Referrer-Policy
and no Cross-Origin-Opener-Policy. The middleware that adds them was declared
before the access gate, which made it the inner of the two, and the gate
answers a visitor without a code itself: 23 of the 67 answers such a visitor
gets from the routes of a gated deployment went out bare, and so did the 500
for an exception nothing handled, which no middleware sees at all.

The existing test asked /health and /api/runs with the gate off, where every
answer comes from an endpoint, so it passed throughout. These ask as an
anonymous visitor of a gated deployment, which is what the public one is, and
they ask for the rule: every route, every method, and each response that
something other than an endpoint builds.
"""

from __future__ import annotations

import re
import unittest
from unittest.mock import patch

from fastapi import Response
from fastapi.testclient import TestClient

from api import access, upload_boundary
from api import main as api_main
from api.main import app

_EXPECTED = {name.lower(): value for name, value in api_main._SECURITY_HEADERS.items()}
_MULTIPART = {"Content-Type": "multipart/form-data; boundary=x"}
_PART = b'--x\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n\r\n' + b"0" * 4096 + b"\r\n--x--\r\n"


class _Case(unittest.TestCase):
    def setUp(self):
        # Gated, as the public deployment is, and no code.
        self._code = patch.object(access, "ACCESS_CODE", "secret123")
        self._code.start()
        self.addCleanup(self._code.stop)
        # An endpoint that raises answers 500 here, as a server does, instead
        # of raising into the test.
        self.client = TestClient(app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def assert_the_four(self, response, status: int | None = None):
        if status is not None:
            self.assertEqual(response.status_code, status)
        self.assertEqual({name: response.headers.get(name) for name in _EXPECTED}, _EXPECTED)

    def _temporary_route(self, path: str, endpoint) -> None:
        app.add_api_route(path, endpoint, include_in_schema=False)
        added = app.router.routes[-1]
        self.addCleanup(app.router.routes.remove, added)


class EveryRouteTests(_Case):

    def test_there_are_four_and_these_are_the_four(self):
        """The other tests compare against the dictionary itself, so an entry
        dropped from it would be dropped from them as well."""
        self.assertEqual(sorted(_EXPECTED), ["content-security-policy", "cross-origin-opener-policy",
                                             "referrer-policy", "x-content-type-options"])

    def test_every_answer_to_a_visitor_without_a_code_carries_the_four(self):
        """The rule, not the instances: a route added later is asked too."""
        asked, refused = 0, 0
        for route in app.routes:
            path = re.sub(r"\{[^}]*\}", "x", route.path)
            for method in sorted(getattr(route, "methods", None) or ()):
                asked += 1
                with self.subTest(method=method, path=path):
                    # Not followed: it is the answer at this address that is asked about.
                    response = self.client.request(method, path, follow_redirects=False)
                    refused += response.status_code == 401
                    for name in _EXPECTED:
                        self.assertIn(name, response.headers)
        # Silence is not a pass: the walk must reach the API, and the gate
        # must have answered a good part of it by itself.
        self.assertGreater(asked, 50, "the walk must reach the API")
        self.assertGreater(refused, 15, "the gate must be on and answering for the walk to mean anything")

    def test_it_is_the_outermost_middleware(self):
        """A middleware declared after it would sit outside it, and whatever
        that one answered by itself would go out bare. The walk above cannot
        see a refusal it does not happen to provoke; the position can."""
        outermost = app.user_middleware[0]
        self.assertIs(outermost.kwargs.get("dispatch"), api_main._security_headers)

    def test_a_response_that_chose_its_own_value_keeps_it(self):
        """The saved-source locator's refusal page sends a stricter policy of
        its own; the default must not replace it."""
        def own_policy():
            return Response("x", headers={"Content-Security-Policy": "default-src 'none'",
                                          "Referrer-Policy": "no-referrer"})

        self._temporary_route("/__own-policy", own_policy)
        response = self.client.get("/__own-policy")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-security-policy"], "default-src 'none'")
        self.assertEqual(response.headers["referrer-policy"], "no-referrer")
        # ...and the two it did not choose are still added.
        for name in ("x-content-type-options", "cross-origin-opener-policy"):
            self.assertEqual(response.headers[name], _EXPECTED[name])


class SelfAnsweredTests(_Case):
    """Responses that no endpoint builds. Each was measured on 2026-11-17;
    only the gate's and the unhandled exception's lacked the headers."""

    def test_the_gates_refusal(self):
        self.assert_the_four(self.client.get("/api/runs"), 401)
        # An address under /api/ that does not exist never reaches the
        # router: the gate answers it too.
        self.assert_the_four(self.client.get("/api/no-such-thing"), 401)
        self.assert_the_four(self.client.post("/api/no-such-thing", json={}), 401)

    def test_the_rate_limiters_refusal(self):
        limit = api_main._RATE_LIMIT_REQUESTS
        self.addCleanup(setattr, api_main, "_RATE_LIMIT_REQUESTS", limit)
        api_main._RATE_LIMIT_REQUESTS = 1
        api_main._rate_buckets.clear()
        self.assertEqual(self.client.get("/api/samples").status_code, 200)
        refusal = self.client.get("/api/samples")
        self.assertEqual(refusal.headers.get("x-error-code"), "rate_limited")
        self.assert_the_four(refusal, 429)

    def test_the_upload_boundarys_refusals(self):
        """It answers below FastAPI, by calling a response on the raw send."""
        declared = self.client.post("/api/papers", headers={**_MULTIPART, "Content-Length": "999999999"}, content=b"")
        self.assertEqual(declared.headers.get("x-error-code"), "upload_too_large")
        self.assert_the_four(declared, 413)

        malformed = self.client.post("/api/papers", headers={**_MULTIPART, "Content-Length": "abc"}, content=b"")
        self.assertEqual(malformed.json(), {"detail": "Invalid upload Content-Length."})
        self.assert_the_four(malformed, 400)

        with patch.object(upload_boundary, "MAX_UPLOAD_PARSERS", 0):
            full = self.client.post("/api/papers", headers=_MULTIPART, content=_PART)
        self.assertEqual(full.headers.get("x-error-code"), "upload_capacity")
        self.assert_the_four(full, 429)

        # No declared length, so the limit is met while the body is read and
        # the refusal replaces the parser's own answer at the send seam.
        with patch.object(upload_boundary.papers, "MAX_UPLOAD_BYTES", 10), \
                patch.object(upload_boundary, "MAX_MULTIPART_OVERHEAD_BYTES", 10):
            streamed = self.client.post("/api/papers", headers=_MULTIPART, content=iter([_PART]))
        self.assertEqual(streamed.headers.get("x-error-code"), "upload_too_large")
        self.assert_the_four(streamed, 413)

        with patch.object(upload_boundary, "UPLOAD_TOTAL_SECONDS", -1.0):
            late = self.client.post("/api/papers", headers=_MULTIPART, content=iter([_PART]))
        self.assertEqual(late.headers.get("x-error-code"), "upload_timeout")
        self.assert_the_four(late, 408)

    def test_what_the_router_and_the_static_files_answer_without_an_endpoint(self):
        self.assert_the_four(self.client.get("/nothing-here"), 404)
        self.assert_the_four(self.client.get("/samples/", follow_redirects=False), 307)
        self.assert_the_four(self.client.post("/health"), 405)
        self.assert_the_four(self.client.get("/static/js/no-such-module.js"), 404)
        first = self.client.get("/static/js/app.js")
        self.assert_the_four(first, 200)
        unchanged = self.client.get("/static/js/app.js", headers={"If-None-Match": first.headers["etag"]})
        self.assertEqual(unchanged.content, b"")
        self.assert_the_four(unchanged, 304)

    def test_the_answer_to_an_exception_nothing_handled(self):
        """Ordering cannot reach this one: the exception passes every
        middleware as an exception, and the layer outside all of them sends
        the 500. It is the same 500 as before, with the headers."""
        def raises():
            raise RuntimeError("a detail that must not reach the caller")

        self._temporary_route("/__raises", raises)
        response = self.client.get("/__raises")
        self.assert_the_four(response, 500)
        self.assertEqual(response.text, "Internal Server Error")
        self.assertTrue(response.headers["content-type"].startswith("text/plain"))

        # The exception is still raised past the response, which is what
        # makes the server log the traceback.
        with TestClient(app) as raising, self.assertRaisesRegex(RuntimeError, "must not reach the caller"):
            raising.get("/__raises")

    def test_an_exception_inside_the_gate_is_answered_the_same_way(self):
        """A middleware that raises is no different from an endpoint that does."""
        with patch.object(api_main.identity, "resolve", side_effect=RuntimeError("boom")):
            self.assert_the_four(self.client.get("/api/runs"), 500)


if __name__ == "__main__":
    unittest.main()
