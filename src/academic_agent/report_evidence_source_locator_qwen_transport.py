"""Offline-prepared, single-selection Qwen boundary; no live authority or runner.

The unchanged locator owns the sole local read and saved-text JSON projection.
Only the frozen base key validation, one-shot HTTP, journal/accounting and pure
validation/scanning helpers are reused, never an older adapter's __call__.
Dependencies below are paths, not verified hashes or transmission permission.

Explicit LocatorQwenLedger construction creates/fsyncs a fresh private journal;
transport construction performs no I/O. Requests contain questions and title/ID
metadata, so that journal is not public-safe. Prices are inherited frozen
engineering estimates, not invoices or a new allowance. Both objects require
one synchronous owner: no concurrency, resume, retry or production integration.
"""

import asyncio
from copy import deepcopy

import httpx

from academic_agent import report_evidence_source_locator as locator
from academic_agent.report_evidence_catalog_followup import build_catalog
from academic_agent.report_evidence_catalog_qwen_transport import _contains_secret
from academic_agent.report_evidence_followup import MAX_ARGUMENT_CHARS, _strict_json
from academic_agent.report_evidence_qwen_canary import (
    CanaryLedger, CanaryStopped, INPUT_RESERVATION, MAX_TOKENS, MODEL,
    REQUEST_BYTES, _encoded, configuration,
)
from academic_agent.report_evidence_qwen_transport import (
    QwenFollowupTransport, _project_message, _usage,
)
from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot

TRANSPORT_IDENTITY = "report_evidence_source_locator_qwen_transport_v1"
MAX_REQUESTS = 1
FROZEN_DEPENDENCY_COUPLING = (
    "src/academic_agent/report_evidence_source_locator.py",
    "src/academic_agent/report_evidence_catalog_followup.py",
    "src/academic_agent/report_evidence_catalog_qwen_transport.py",
    "src/academic_agent/report_evidence_followup.py",
    "src/academic_agent/report_evidence_snapshot.py",
    "src/academic_agent/report_evidence_qwen_transport.py",
    "src/academic_agent/report_evidence_qwen_canary.py",
    "pyproject.toml", "uv.lock",
)
_SAFE_ERRORS = frozenset({
    "batch_already_stopped", "unresolved_request", "request_limit", "budget_limit",
    "persistence_failed", "request_identity_mismatch", "conversation_closed",
    "invalid_request_contract", "invalid_request_body", "request_too_large",
    "empty_catalog", "secret_in_request", "http_status_rejected",
    "response_encoding_rejected", "response_too_large", "invalid_response_protocol",
    "usage_unknown_or_contradictory", "unexpected_response_model",
    "token_reservation_exceeded", "secret_in_response", "invalid_selection",
    "mixed_response", "unadvertised_tool", "read_id_not_permitted",
    "invalid_decline", "request_timeout", "response_or_transport_failed",
})


def locator_qwen_configuration() -> dict:
    """Describe the new one-request limit, not the base six-request allowance."""
    return {
        **configuration(), "max_requests": MAX_REQUESTS, "method_id": locator.METHOD_ID,
        "callback_contract": "one_positional_exact_dict",
        "response_format": "omitted", "max_local_reads": 1,
        "ownership": "synchronous_single_owner_not_thread_safe",
        "ledger_construction": "fresh_directory_manifest_and_events_fsynced",
        "transport_construction": "no_io", "live_authorization": False,
    }


def _safe_error(exc: Exception, fallback: str) -> str:
    # The shared exception type is not a trust boundary: never call str(exc),
    # including subclasses or a CanaryStopped carrying arbitrary provider text.
    if type(exc) is CanaryStopped and len(exc.args) == 1:
        reason = exc.args[0]
        if type(reason) is str and reason in _SAFE_ERRORS:
            return reason
    return fallback


class LocatorQwenLedger(CanaryLedger):
    """Fresh filesystem-writing ledger; one reservation across all instances.

    Inherited reserve/finish fsync and conservative accounting remain unchanged.
    This is single-owner intent persistence, not provider exactly-once or
    disk-loss safety. A partially created/used directory is never reusable.
    """

    def __init__(self, output_dir):
        super().__init__(output_dir, {
            "transport_identity": TRANSPORT_IDENTITY, "method_id": locator.METHOD_ID,
            "scope": "offline_contract_no_live_authorization", "live_authorization": False,
            "configuration": locator_qwen_configuration(),
            "journal_scope": "private_question_and_title_id_metadata_not_public_safe",
            "frozen_dependency_coupling": list(FROZEN_DEPENDENCY_COUPLING),
        })

    def reserve(self, body: dict) -> int:
        # This guard belongs to the ledger, not just a transport constructor.
        # Two transports can have been constructed while this ledger was fresh.
        if self.stop_reason is not None:
            raise CanaryStopped("batch_already_stopped")
        if self.pending is not None:
            self.stop("unresolved_request")
            raise CanaryStopped("unresolved_request")
        if len(self.records) >= MAX_REQUESTS:
            self.stop("request_limit")
            raise CanaryStopped("request_limit")
        return super().reserve(body)


def _admit_selection(message: dict, visible_ids: tuple[str, ...]) -> None:
    """Validate without repairing; the locator repeats these checks before read."""
    calls = message.get("tool_calls") or []
    if not calls:
        if message.get("refusal"):
            return  # _project_message already requires standalone refusal.
        try:
            locator._Decline.model_validate(_strict_json(message.get("content") or ""))
        except (ValueError, TypeError, RecursionError):
            raise CanaryStopped("invalid_decline") from None
        return
    if message.get("content"):
        raise CanaryStopped("mixed_response")
    function = calls[0]["function"]
    if function["name"] != "read_source":
        raise CanaryStopped("unadvertised_tool")
    try:
        arguments = function["arguments"]
        if len(arguments) > MAX_ARGUMENT_CHARS:
            raise ValueError("argument_budget_exceeded")
        choice = locator._Selection.model_validate(_strict_json(arguments))
    except (ValueError, TypeError, RecursionError):
        raise CanaryStopped("invalid_selection") from None
    if choice.source_id not in visible_ids:
        raise CanaryStopped("read_id_not_permitted")


class LocatorQwenTransport(QwenFollowupTransport):
    """Explicit-key, detached snapshot/question binding with no constructor I/O.

    Network-capable when explicitly called, not a network sandbox or live grant.
    The inherited _post alone fixes TLS, endpoint, timeouts, response byte cap,
    no proxies, no retries and no redirects. No saved text goes to the model.
    """

    def __init__(self, api_key: str, ledger: LocatorQwenLedger, *, snapshot: ReportEvidenceSnapshot, question: str):
        if type(ledger) is not LocatorQwenLedger:
            raise CanaryStopped("locator_ledger_required")
        if ledger.stop_reason is not None or ledger.pending is not None or ledger.records:
            raise CanaryStopped("fresh_locator_ledger_required")
        super().__init__(api_key, ledger)
        if type(question) is not str or not 1 <= len(question) <= 4096 or not question.strip():
            raise CanaryStopped("invalid_question")
        try:
            if type(snapshot) is not ReportEvidenceSnapshot:
                raise ValueError("invalid_snapshot")
            self._snapshot = ReportEvidenceSnapshot.model_validate(snapshot.model_dump(warnings="error"))
            self._catalog = build_catalog(self._snapshot)
        except Exception:  # noqa: BLE001 -- malformed constructed models must not expose input or diagnostics.
            raise CanaryStopped("invalid_snapshot") from None
        self._question = question
        self._visible_ids = tuple(item["source_id"] for item in self._catalog["entries"])
        self._attempted = False

    def _stop(self, reason: str) -> None:
        try:
            self.ledger.stop(reason)
        except Exception:  # noqa: BLE001 -- persistence errors cannot carry paths, credentials or raw exception text.
            self.ledger.stop_reason = "persistence_failed"
            raise CanaryStopped("persistence_failed") from None
        raise CanaryStopped(reason) from None

    def __call__(self, request, /):
        # Callback entry consumes the attempt even when validation/reservation
        # fails. No invalid first input can be repaired with a second instance.
        attempted = self._attempted
        self._attempted = True
        if self.ledger.stop_reason is not None:
            raise CanaryStopped("batch_already_stopped")
        if attempted:
            self._stop("conversation_closed")
        error = None
        try:
            if type(request) is not dict or set(request) != {"messages", "tools", "tool_choice"}:
                raise CanaryStopped("invalid_request_contract")
            detached = deepcopy(request)
            body = {**detached, "model": MODEL, "stream": False, "enable_thinking": False,
                    "parallel_tool_calls": False, "temperature": 0, "max_tokens": MAX_TOKENS}
            wire = _encoded(body)
            if len(wire) > REQUEST_BYTES:
                raise CanaryStopped("request_too_large")
            if _contains_secret(body, self._api_key):
                raise CanaryStopped("secret_in_request")
            if not self._visible_ids:
                raise CanaryStopped("empty_catalog")
            expected = locator._request(self._question, self._catalog)
            if _encoded(detached) != _encoded(expected):
                raise CanaryStopped("request_identity_mismatch")
        except Exception as exc:  # noqa: BLE001 -- only code-owned allowlisted categories survive request failures.
            error = _safe_error(exc, "invalid_request_body")
        if error is not None:
            self._stop(error)

        # The same canonical body is fsynced before any possible _post. Failed
        # reserve means zero dispatch; finish failure leaves spent pending intent.
        try:
            ordinal = self.ledger.reserve(body)
        except Exception as exc:  # noqa: BLE001 -- never disclose arbitrary journal/helper exception details.
            error = _safe_error(exc, "persistence_failed")
        if error is not None:
            self._stop(error)
        observation = {"received": False}
        usage = message = None
        model_matches = None
        try:
            raw = asyncio.run(self._post(wire, observation))
            payload = _strict_json(raw.decode("utf-8"))
            if type(payload) is not dict:
                raise CanaryStopped("invalid_response_protocol")
            model_matches = payload.get("model") == MODEL
            usage = _usage(payload)
            if usage is None:
                raise CanaryStopped("usage_unknown_or_contradictory")
            if not model_matches:
                raise CanaryStopped("unexpected_response_model")
            if usage["prompt_tokens"] > INPUT_RESERVATION or usage["completion_tokens"] > MAX_TOKENS:
                raise CanaryStopped("token_reservation_exceeded")
            if _contains_secret(payload, self._api_key):
                raise CanaryStopped("secret_in_response")
            projected = _project_message(payload)
            _admit_selection(projected, self._visible_ids)
            message = projected
        except (TimeoutError, httpx.TimeoutException):
            error = "request_timeout"
        except Exception as exc:  # noqa: BLE001 -- arbitrary CanaryStopped text is untrusted too.
            error = _safe_error(exc, "response_or_transport_failed")
        try:
            # No reply body is needed for this audit. In particular, refusals,
            # call IDs, argument strings and generated prose never reach disk.
            self.ledger.finish(ordinal, received=observation["received"], usage=usage, error=error,
                               response_model_matches_authorized=model_matches)
        except Exception:  # noqa: BLE001 -- preserve inherited pending/observed usage without unsafe diagnostics.
            self.ledger.stop_reason = "persistence_failed"
            raise CanaryStopped("persistence_failed") from None
        if error is not None:
            raise CanaryStopped(error) from None
        return deepcopy(message)
