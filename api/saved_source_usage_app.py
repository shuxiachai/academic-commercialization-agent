"""Opt-in accounting envelope; isolated from production and the legacy wire."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.responses import FileResponse, Response

from academic_agent.saved_source_usage import UsageProjectionV1, unavailable_usage
from api.saved_source_accounting import AccountingStore
from api.saved_source_controller import SavedSourceController
from api.saved_source_receipt_app import (
    MAX_RESPONSE_BYTES, _HEADERS, _WEB_ROOT as _RECEIPT_ROOT, _assemble_receipt_app, _wire_reply,
)

CONTRACT = "saved_source_receipt_usage_v1"
POST_PATH = "/api/runs/{run_id}/saved-source-usage"
GET_PATH = "/api/saved-source-usage-receipts"
MAX_ACCOUNTING_BYTES = 4096
_WEB_ROOT = Path(__file__).resolve().parents[1] / "web" / "saved-source-usage"


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _unavailable(receipt, fault="accounting_unavailable"):
    """Failure to observe spending is unknown, never an invented zero invoice."""
    return unavailable_usage(receipt["receipt_key_sha256"], receipt["run_id"], receipt["expires_at"], fault)


def _accounting(value, receipt):
    try:
        raw = _json_bytes(value)
        if len(raw) > MAX_ACCOUNTING_BYTES:
            raise ValueError("accounting_too_large")
        checked = UsageProjectionV1.model_validate(value, strict=True).model_dump(mode="json")
        # Exact comparison forbids coercion/default filling in every nested layer.
        if json.dumps(value, sort_keys=True, allow_nan=False) != json.dumps(checked, sort_keys=True, allow_nan=False):
            raise ValueError("changed_accounting")
        if any(checked[key] != receipt[key] for key in ("receipt_key_sha256", "run_id", "expires_at")):
            return _unavailable(receipt, "binding_mismatch")
        return value
    except (ValueError, TypeError, RecursionError):
        return _unavailable(receipt)


def _wire_usage_reply(reply, key, *, run_id=None):
    """Keep a valid excerpt even when its independent accounting is unavailable."""
    if type(reply) is not dict:
        raise ValueError("invalid_envelope")
    legacy = {name: value for name, value in reply.items() if name != "accounting"}
    receipt = json.loads(_wire_reply(legacy, key, run_id=run_id).body)
    # A supplier's non-JSON accounting value is a component fault before HTTP,
    # unlike an invalid JSON response received by the browser. Still reject a
    # serializable oversized original instead of hiding transport overflow.
    try:
        original = _json_bytes(reply)
    except (ValueError, TypeError, RecursionError):
        original = None
    if original is not None and len(original) > MAX_RESPONSE_BYTES:
        raise ValueError("response_too_large")
    accounting = _accounting(reply.get("accounting"), receipt)
    raw = _json_bytes({"contract": CONTRACT, "receipt": receipt, "accounting": accounting})
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("response_too_large")
    return Response(raw, media_type="application/json", headers=_HEADERS)


def create_saved_source_usage_app(*, load_snapshot, journal_root, accounted_selector=None,
                                  selector_identity=None, accounting_store=None):
    """Own one disabled-by-default controller; never discover a provider or key."""
    controller = SavedSourceController(
        load_snapshot, journal_root, selector_identity=selector_identity,
        accounted_selector=accounted_selector,
        accounting_store=AccountingStore(journal_root) if accounting_store is None else accounting_store,
    )
    app = _assemble_receipt_app(
        controller, web_root=_WEB_ROOT, static_prefix="/usage-static",
        post_path=POST_PATH, get_path=GET_PATH, wire_reply=_wire_usage_reply,
    )
    # Serve only the reused scripts/style, not another page or legacy API mount.
    for name in ("app.js", "result.js", "app.css"):
        def asset_path(filename=name):
            async def asset():
                return FileResponse(_RECEIPT_ROOT / filename)
            return asset
        app.add_api_route(f"/receipt-static/{name}", asset_path(), methods=["GET"], include_in_schema=False)
    return app
