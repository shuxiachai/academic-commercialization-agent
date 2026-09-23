"""Public HTTPS -> backend HTTP origin pinning, with unchanged paid/receipt gates."""

from copy import deepcopy
from dataclasses import replace
from unittest.mock import AsyncMock, Mock

from fastapi import Request
from fastapi.testclient import TestClient
import pytest

from api import saved_source_production as production
from api import saved_source_production_origin as origin
from api import saved_source_receipt_app as frozen
from api.saved_source_receipts import ReceiptError
from tests.test_saved_source_production import (
    CODE, QUESTION, SETTINGS, TEXT, URL, app_for, boundary as boundary, consent, count,
    headers, key, native as native, prepared as prepared,
)

PUBLIC = "https://locator.invalid"
PINNED = replace(SETTINGS, public_origin=PUBLIC)


def raw_request(**changes):
    scope = {
        "type": "http", "method": "POST", "scheme": "http", "path": URL, "query_string": b"",
        "headers": [(name.lower().encode(), value.encode()) for name, value in {
            **consent(), "Host": "locator.invalid", "Origin": PUBLIC, "Content-Type": "application/json",
        }.items()],
    }
    scope.update(changes)
    return Request(scope)


def assert_no_work(prepared, runtime):
    assert prepared.key_reads == prepared.requests == [] and count() == 0
    assert not runtime.root.exists()


def test_public_https_post_over_http_and_rollback_get_preserve_exact_delivery(prepared):
    """The old ASGI-scheme helper rejected a browser HTTPS POST before any intent."""
    runtime = prepared.build(PINNED)
    receipt_key = key()
    with TestClient(app_for(runtime), base_url="http://locator.invalid") as client:
        first = client.post(URL, json={"question": QUESTION}, headers={**consent(receipt_key), "Origin": PUBLIC})
        assert first.status_code == 200, first.text
        payload = first.json()
        assert payload["receipt"]["result"]["saved_text"]["text"] == TEXT
        assert payload["accounting"]["usage"]["status"] == "reported_complete"
        assert payload["accounting"]["cost"]["estimated_usd"] == "0.000126100"
        runtime.stop_accepting()
        assert client.get(production.PAGE_PATH).text.find('data-execution-allowed="false"') >= 0
        denied = client.post(URL, json={"question": QUESTION}, headers={**consent(), "Origin": PUBLIC})
        assert denied.status_code == 503 and denied.json()["error_code"] == "selector_disabled"
        replay = client.get(production.GET_PATH, headers=headers(receipt_key))
        assert replay.status_code == 200 and replay.json()["receipt"]["result"] == payload["receipt"]["result"]
        assert replay.json()["accounting"] == payload["accounting"]
    assert len(prepared.requests) == len(prepared.key_reads) == count() == 1


@pytest.mark.parametrize("value,expected", [
    ("HTTPS://LOCATOR.INVALID:443", ("https", "locator.invalid", 443)),
    ("http://localhost:8000", ("http", "localhost", 8000)),
    ("http://127.0.0.1", ("http", "127.0.0.1", 80)),
    ("https://[2001:0DB8:0:0:0:0:0:1]:443", ("https", "2001:db8::1", 443)),
    ("http://[::1]:8080", ("http", "::1", 8080)),
])
def test_canonical_origin_only_normalizes_defined_components(value, expected):
    """Default ports and address spelling are equivalent; URL repair is not."""
    assert origin.canonical_origin(value) == expected


BAD_ORIGINS = [
    None, " ", "null", "https://", "ftp://locator.invalid", "https://*.invalid", "https://locator.invalid/",
    "https://locator.invalid?", "https://locator.invalid#", "https://locator.invalid/path",
    "https://u@locator.invalid", "https://u:p@locator.invalid", "https://locator.invalid:0",
    "https://locator.invalid:65536", "https://locator.invalid:", "https://locator.invalid:+443",
    "https://locator.invalid:443,https://evil.invalid", "https://locator.invalid https://evil.invalid",
    "https://locator.invalid,evil.invalid", " https://locator.invalid", "https://locator.invalid\n",
    "https://locator.invalid\t", "https://locator.invalid\\evil", "https://locátor.invalid",
    "https://locator.invalid.", "https://[::1", "https://[::1]junk", "https://[fe80::1%25eth0]",
    "https://127.1", "https://127.00.0.1", "https://" + "a" * 64 + ".invalid", "x" * 2049,
]


@pytest.mark.parametrize("value", BAD_ORIGINS)
def test_invalid_config_fails_closed_before_body_and_never_claims_page_enabled(prepared, monkeypatch, value):
    """Malformed explicit configuration cannot fall back to ASGI or forwarded authority."""
    runtime = prepared.build(replace(PINNED, public_origin=value))
    assert not runtime.execution_allowed
    body = AsyncMock(side_effect=AssertionError("Bad config read request body"))
    monkeypatch.setattr(production, "_body", body)
    with TestClient(app_for(runtime), base_url="http://locator.invalid") as client:
        for method, path in (("POST", URL), ("GET", production.GET_PATH), ("GET", production.PAGE_PATH),
                             ("GET", production.PAGE_PATH + "/"), ("GET", "/source-locator-static/entry.js")):
            reply = client.request(method, path, headers={**consent(), "Origin": PUBLIC}, json={"question": QUESTION})
            assert reply.status_code == 503 and reply.json()["error_code"] == "execution_unavailable"
    body.assert_not_called()
    assert_no_work(prepared, runtime)


@pytest.mark.parametrize("field,value", [
    ("Origin", "http://locator.invalid"), ("Origin", "https://evil.invalid"),
    ("Origin", "https://locator.invalid:8443"), ("Origin", "null"), ("Origin", ""),
    ("Origin", "https://locator.invalid/"), ("Origin", "https://locator.invalid?"),
    ("Origin", "https://u@locator.invalid"), ("Origin", "https://locator.invalid,https://evil.invalid"),
    ("Origin", "https://locator.invalid https://evil.invalid"),
    ("Host", "evil.invalid"), ("Host", "locator.invalid:80"), ("Host", "locator.invalid:8443"),
    ("Host", "locator.invalid:"), ("Host", "locator.invalid/"), ("Host", "locator.invalid?"),
    ("Host", "locator.invalid,evil.invalid"), ("Host", "u@locator.invalid"), ("Host", ""),
])
@pytest.mark.parametrize("method", ["POST", "GET"])
def test_untrusted_origin_or_host_denied_before_body_and_controller(prepared, monkeypatch, field, value, method):
    """Neither a valid Origin nor attacker-controlled proxy metadata can replace Host binding."""
    runtime = prepared.build(PINNED)
    forbidden = AsyncMock(side_effect=AssertionError("Denied request crossed ingress"))
    monkeypatch.setattr(production, "_body", forbidden)
    monkeypatch.setattr(runtime.controller, "execute", forbidden)
    monkeypatch.setattr(runtime.controller, "lookup", forbidden)
    supplied = {**consent(), "Origin": PUBLIC, "Host": "locator.invalid", field: value,
                "Forwarded": 'host=locator.invalid;proto=https',
                "X-Forwarded-Host": "locator.invalid", "X-Forwarded-Proto": "https"}
    with TestClient(app_for(runtime), base_url="http://locator.invalid") as client:
        reply = client.request(method, URL if method == "POST" else production.GET_PATH,
                               json={"question": QUESTION}, headers=supplied)
        assert reply.status_code == 403 and reply.json()["error_code"] == "origin_denied"
    forbidden.assert_not_called()
    assert_no_work(prepared, runtime)


@pytest.mark.parametrize("name", sorted(frozen._CRITICAL | {production.CONSENT_HEADER}))
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_duplicate_critical_headers_still_refused_before_body(prepared, monkeypatch, name, method):
    """Public-origin acceptance must not collapse duplicate security/body/consent headers."""
    runtime = prepared.build(PINNED)
    forbidden = AsyncMock(side_effect=AssertionError("Duplicate header reached body"))
    monkeypatch.setattr(production, "_body", forbidden)
    supplied = [(key, value) for key, value in raw_request().scope["headers"] if key != name]
    supplied += [(name, b"PRIVATE"), (name.upper(), b"PRIVATE")]
    with TestClient(app_for(runtime)) as client:
        reply = client.request(method, URL if method == "POST" else production.GET_PATH, headers=supplied)
        assert reply.status_code == 422 and reply.json()["error_code"] == "invalid_request"
    forbidden.assert_not_called()
    assert_no_work(prepared, runtime)


@pytest.mark.parametrize("changes,error", [
    ({"content-type": "application/json; charset=utf-8"}, "unsupported_media_type"),
    ({"content-encoding": "identity"}, "unsupported_media_type"),
    ({"content-length": "-1"}, "invalid_request"),
    ({"content-length": "1,1"}, "invalid_request"),
    ({"content-length": "1", "transfer-encoding": "chunked"}, "invalid_request"),
    ({"content-length": str(frozen.MAX_BODY_BYTES + 1)}, "body_too_large"),
    ({"x-access-code": "x" * (frozen.MAX_ACCESS_CODE_BYTES + 1)}, "headers_too_large"),
    ({"origin": "x" * frozen.MAX_CRITICAL_HEADER_BYTES}, "headers_too_large"),
    ({"idempotency-key": "invalid"}, "invalid_receipt_key"),
    ({"x-access-code": ""}, "access_denied"),
    ({"x-source-locator-consent": "wrong"}, "consent_required"),
])
def test_pinned_authority_retains_strict_non_origin_header_rules(changes, error):
    """Pinning origin cannot admit encoding, length, code, key or consent drift."""
    request = raw_request()
    request.scope["headers"] = [(name, value) for name, value in request.scope["headers"] if name.decode() not in changes]
    request.scope["headers"] += [(name.encode(), value.encode()) for name, value in changes.items()]
    with pytest.raises(ReceiptError) as caught:
        production._production_headers(request, origin.OriginPolicy(PUBLIC))
    assert caught.value.code == error


@pytest.mark.parametrize("body", [b'{"question":"x","question":"y"}', b'{"question":NaN}', b'{}', b'\xff'])
def test_pinned_origin_does_not_bypass_body_contract(prepared, body):
    """The trusted public origin cannot make malformed question bytes valid."""
    runtime = prepared.build(PINNED)
    with TestClient(app_for(runtime), base_url="http://locator.invalid") as client:
        reply = client.post(URL, content=body, headers={**consent(), "Origin": PUBLIC, "Content-Type": "application/json"})
        assert reply.status_code == 422 and reply.json()["error_code"] == "invalid_request"
    assert_no_work(prepared, runtime)


def test_forwarded_headers_have_no_authority_and_request_scope_is_untouched():
    """Only a validated explicit pin can bridge HTTPS/HTTP; raw metadata stays intact."""
    request = raw_request()
    request.scope["headers"] += [(b"forwarded", b"host=evil.invalid;proto=ftp"),
                                 (b"x-forwarded-host", b"evil.invalid"), (b"x-forwarded-proto", b"https")]
    before = deepcopy(request.scope)
    with pytest.raises(ReceiptError) as old:
        frozen._request_headers(request)
    assert old.value.code == "origin_denied"
    with pytest.raises(ReceiptError) as unconfigured:
        production._production_headers(request, origin.OriginPolicy())
    assert unconfigured.value.code == "origin_denied"
    assert production._production_headers(request, origin.OriginPolicy(PUBLIC))[1] == CODE
    assert request.scope == before


@pytest.mark.parametrize("host,origin_value", [
    ("LOCATOR.INVALID:443", "HTTPS://locator.invalid"),
    ("locator.invalid", "https://LOCATOR.INVALID:443"),
    ("locator.invalid:443", None),
])
def test_effective_public_port_and_optional_origin_are_explicit(host, origin_value):
    """An origin-less client is still bound to the configured Host and effective port."""
    request = raw_request(method="GET")
    request.scope["headers"] = [(name, value) for name, value in request.scope["headers"] if name not in {b"host", b"origin"}]
    request.scope["headers"].append((b"host", host.encode()))
    if origin_value is not None:
        request.scope["headers"].append((b"origin", origin_value.encode()))
    assert production._production_headers(request, origin.OriginPolicy(PUBLIC))[1] == CODE
    request.scope["headers"] = [(name, value) for name, value in request.scope["headers"] if name != b"host"]
    with pytest.raises(ReceiptError) as caught:
        production._production_headers(request, origin.OriginPolicy(PUBLIC))
    assert caught.value.code == "origin_denied"


def test_page_slash_is_relative_and_page_assets_reject_wrong_host(prepared):
    """ASGI slash redirects previously emitted HTTP Location at the public HTTPS edge."""
    runtime = prepared.build(PINNED)
    with TestClient(app_for(runtime), base_url="http://locator.invalid", follow_redirects=False) as client:
        slash = client.get(production.PAGE_PATH + "/")
        assert slash.status_code == 307 and slash.headers["location"] == production.PAGE_PATH
        page = client.get(production.PAGE_PATH)
        assert page.status_code == 200 and 'data-execution-allowed="true"' in page.text
        assert client.get("/source-locator-static/entry.js").status_code == 200
        for path in (production.PAGE_PATH, production.PAGE_PATH + "/", "/source-locator-static/entry.js"):
            denied = client.get(path, headers={"Host": "evil.invalid"})
            assert denied.status_code == 403 and denied.json()["error_code"] == "origin_denied"
    assert_no_work(prepared, runtime)


def test_public_origin_env_is_snapshot_only_and_never_discovers_keys(tmp_path, monkeypatch):
    """Configuration reads only the explicit public origin; later env changes do not repin."""
    monkeypatch.setenv("SOURCE_LOCATOR_PUBLIC_ORIGIN", PUBLIC)
    configured = production.Settings.from_env()
    assert configured.public_origin == PUBLIC
    forbidden = Mock(side_effect=AssertionError("Configuration discovered a provider key"))
    runtime = production.build_runtime(settings=replace(PINNED, public_origin=configured.public_origin),
                                       output_root=tmp_path, key_loader=forbidden)
    monkeypatch.setenv("SOURCE_LOCATOR_PUBLIC_ORIGIN", "https://evil.invalid")
    assert runtime.origin_policy.expected == ("https", "locator.invalid", 443)
    assert production._production_headers(raw_request(), runtime.origin_policy)[1] == CODE
    forbidden.assert_not_called()
    assert not runtime.root.exists()


@pytest.mark.parametrize("case", [
    "valid", "origin_absent", "query", "missing_code", "nonascii_code", "control_code", "code_cap",
    "missing_key", "bad_key", "bad_media", "encoding", "length_empty", "length_negative",
    "length_comma", "length_digits_cap", "body_cap", "length_and_transfer", "aggregate_cap",
    *("duplicate_" + name.decode() for name in sorted(frozen._CRITICAL)),
])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_non_origin_ingress_decisions_match_frozen_helper(case, method):
    """Copied critical-header checks must retain the frozen helper's actual outcomes."""
    request = raw_request(method=method)
    request.scope["scheme"] = "https"
    mutations = {
        "missing_code": (b"x-access-code", None), "nonascii_code": (b"x-access-code", b"\xff"),
        "control_code": (b"x-access-code", b"a\x00b"), "code_cap": (b"x-access-code", b"x" * 4097),
        "missing_key": (b"idempotency-key", None), "bad_key": (b"idempotency-key", b"invalid"),
        "origin_absent": (b"origin", None), "bad_media": (b"content-type", b"text/plain"),
        "encoding": (b"content-encoding", b"identity"), "length_empty": (b"content-length", b""),
        "length_negative": (b"content-length", b"-1"), "length_comma": (b"content-length", b"1,1"),
        "length_digits_cap": (b"content-length", b"0" * 21),
        "body_cap": (b"content-length", str(frozen.MAX_BODY_BYTES + 1).encode()),
        "aggregate_cap": (b"origin", b"x" * frozen.MAX_CRITICAL_HEADER_BYTES),
    }
    if case in mutations:
        name, value = mutations[case]
        request.scope["headers"] = [(key, raw) for key, raw in request.scope["headers"] if key != name]
        if value is not None:
            request.scope["headers"].append((name, value))
    elif case == "query":
        request.scope["query_string"] = b"key=private"
    elif case == "length_and_transfer":
        request.scope["headers"] += [(b"content-length", b"1"), (b"transfer-encoding", b"chunked")]
    elif case.startswith("duplicate_"):
        name = case.removeprefix("duplicate_").encode()
        request.scope["headers"] = [(key, raw) for key, raw in request.scope["headers"] if key != name]
        request.scope["headers"] += [(name, b"PRIVATE"), (name.upper(), b"PRIVATE")]

    def outcome(check):
        try:
            return "accepted", check(request)
        except ReceiptError as exc:
            return "rejected", exc.code
    assert outcome(lambda request: origin.request_headers(request, origin.OriginPolicy(PUBLIC))) == outcome(frozen._request_headers)
