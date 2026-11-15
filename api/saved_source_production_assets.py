"""Whitelist-only production assets; frozen lab assets retain their exact bytes."""

from pathlib import Path

from fastapi.responses import Response

import base64
import hashlib

from api.saved_source_receipt_app import _ERROR_STATUS, _HEADERS, _error

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


# What a person sees when the page itself is refused. Until 2026-11-15 that was
# the API's JSON, shown as text: on a deployment whose visitors use one
# address and whose locator is configured for another, the sidebar's link
# opened `{"detail": ..., "error_code": "origin_denied"}`. The page says what
# happened and offers the way back. It is served exactly where the locator's
# own stylesheet is refused, so its few rules are inline, and the policy
# names those bytes by hash instead of allowing inline styles in general. It
# has no script, loads nothing, and writes neither the address asked for nor
# the configured one into itself.
_REFUSAL_STYLE = (
    "body{margin:0;font:16px/1.6 system-ui,sans-serif;background:#f4f2ee;color:#221d16}"
    "main{max-width:34rem;margin:12vh auto;padding:0 1.25rem}"
    "h1{font-size:1.25rem;line-height:1.35;margin:0 0 .75rem}"
    "p{margin:0 0 .75rem}a{color:inherit}"
    "@media (prefers-color-scheme:dark){body{background:#17140f;color:#efe9df}}"
)
_REFUSAL_POLICY = (
    "default-src 'none'; style-src 'sha256-"
    + base64.b64encode(hashlib.sha256(_REFUSAL_STYLE.encode("utf-8")).digest()).decode("ascii")
    + "'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
_REFUSAL_WORDS = {
    "origin_denied": (
        "这个地址不提供“定位已保存来源” / The saved-source locator is not available at this address",
        "这是一个实验功能，只在本部署配置的那一个地址上开放。你的评估和报告不受影响。",
        "It is an experimental feature, open only at the one address this deployment is configured for. "
        "Your assessments and reports are not affected.",
    ),
    None: (
        "“定位已保存来源”暂时不可用 / The saved-source locator is unavailable at the moment",
        "这是一个实验功能，现在无法打开。你的评估和报告不受影响。",
        "It is an experimental feature and cannot be opened right now. Your assessments and reports are not affected.",
    ),
}


def refusal_page(code):
    """The page a refused document navigation gets: same status and code as the JSON, in words."""
    if code not in _ERROR_STATUS:
        code = "receipt_unavailable"
    title, chinese, english = _REFUSAL_WORDS.get(code, _REFUSAL_WORDS[None])
    html = (
        '<!doctype html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="referrer" content="no-referrer">\n<meta name="robots" content="noindex">\n'
        f"<title>{title}</title>\n<style>{_REFUSAL_STYLE}</style>\n</head>\n<body>\n<main>\n"
        f"<h1>{title}</h1>\n<p>{chinese}</p>\n<p>{english}</p>\n"
        '<p><a href="/">返回评估应用 / Back to assessments</a></p>\n</main>\n</body>\n</html>\n'
    )
    return Response(html.encode("utf-8"), status_code=_ERROR_STATUS[code], media_type="text/html; charset=utf-8",
                    headers={**_HEADERS, "Content-Security-Policy": _REFUSAL_POLICY, "X-Error-Code": code})


def page_response(execution_allowed, *, root=WEB_ROOT):
    try:
        raw = (root / "source-locator" / "index.html").read_bytes()
        raw = _replace_once(raw, EXECUTION_MARKER.encode(), b"true" if execution_allowed else b"false")
        return Response(raw, media_type="text/html", headers=_HEADERS)
    except (OSError, ValueError):
        return _error("execution_unavailable")
