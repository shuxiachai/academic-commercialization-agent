"""Whitelist-only production assets; frozen lab assets retain their exact bytes."""

from pathlib import Path

from fastapi.responses import Response

from api.saved_source_receipt_app import _HEADERS, _error

WEB_ROOT = Path(__file__).resolve().parents[1] / "web"
STATIC_PREFIX = "/source-locator-static"
EXECUTION_MARKER = "{{SOURCE_LOCATOR_EXECUTION_ALLOWED}}"


def _replace_once(source, old, new):
    # A changed frozen script must not silently omit consent or boot twice.
    if source.count(old) != 1:
        raise ValueError("asset_contract_changed")
    return source.replace(old, new, 1)


def receipt_script(source):
    """Production-only hooks: consent precedes intent persistence, never GET."""
    source = _replace_once(
        source, "  clearExtra = () => {}, renderExtra = () => {},\n",
        "  clearExtra = () => {}, renderExtra = () => {},\n"
        "  beforeSubmit = () => true, requestHeaders = () => ({}),\n",
    )
    source = _replace_once(
        source, "  if (!recover && !beginIntent()) return;",
        "  let extraHeaders = {};\n"
        "  if (!recover) {\n"
        "    try {\n"
        "      if (beforeSubmit() !== true) return;\n"
        "      const candidate = requestHeaders();\n"
        "      if (candidate === null || typeof candidate !== 'object' || Array.isArray(candidate)\n"
        "          || ![Object.prototype, null].includes(Object.getPrototypeOf(candidate))\n"
        "          || Reflect.ownKeys(candidate).length !== 1) throw Error('Invalid consent');\n"
        "      const consent = Object.getOwnPropertyDescriptor(candidate, 'X-Source-Locator-Consent');\n"
        "      if (!consent || consent.get || consent.set || consent.value !== 'question-catalog-v1')\n"
        "        throw Error('Invalid consent');\n"
        "      extraHeaders = { 'X-Source-Locator-Consent': 'question-catalog-v1' };\n"
        "    } catch { status('Request consent could not be confirmed.', 'error'); return; }\n"
        "  }\n"
        "  if (!recover && !beginIntent()) return;",
    )
    return _replace_once(
        source, 'headers: { "Idempotency-Key": input.key, "X-Access-Code": input.code },',
        'headers: { ...extraHeaders, '
        '"Idempotency-Key": input.key, "X-Access-Code": input.code },',
    )


def asset_bytes(name, *, root=WEB_ROOT):
    """Never mount a directory or accept a caller-controlled filesystem path."""
    files = {
        "entry.js": root / "source-locator" / "entry.js",
        "outcome.js": root / "source-locator" / "outcome.js",
        "app.css": root / "source-locator" / "app.css",
        "result.js": root / "saved-source-receipts" / "result.js",
        "receipt.css": root / "saved-source-receipts" / "app.css",
        "receipt.js": root / "saved-source-receipts" / "app.js",
        "accounting.js": root / "saved-source-usage" / "accounting.js",
    }
    if name not in files:
        raise KeyError(name)
    raw = files[name].read_bytes()
    if name == "receipt.js":
        # Normalize only this derived script, matching text-mode reads on
        # Windows. Direct aliases above remain byte-for-byte unchanged.
        raw = receipt_script(raw.decode("utf-8").replace("\r\n", "\n")).encode("utf-8")
    elif name == "accounting.js":
        raw = _replace_once(raw, b"/receipt-static/result.js", b"/source-locator-static/result.js")
    return raw


def asset_response(name, *, root=WEB_ROOT):
    try:
        raw = asset_bytes(name, root=root)
        return Response(raw, media_type="text/javascript" if name.endswith(".js") else "text/css",
                        headers=_HEADERS)
    except KeyError:
        return _error("not_found")
    except (OSError, UnicodeError, ValueError):
        return _error("execution_unavailable")


def page_response(execution_allowed, *, root=WEB_ROOT):
    try:
        raw = (root / "source-locator" / "index.html").read_bytes()
        raw = _replace_once(raw, EXECUTION_MARKER.encode(), b"true" if execution_allowed else b"false")
        return Response(raw, media_type="text/html", headers=_HEADERS)
    except (OSError, ValueError):
        return _error("execution_unavailable")
