"""Isolated one-query Qwen wire/accounting boundary; no live authority or runner.

Only the question leaves the caller: the unchanged candidate wrapper owns the
snapshot and local search, never a read or a second model turn. Explicit ledger
construction creates a fresh private journal; transport construction is I/O-free.
The offline scope declaration is NOT a network guard. An explicit real key could
make a real request; native key/region compatibility remains unproven.
"""

import asyncio
from decimal import Decimal

import httpx

from academic_agent import saved_source_candidate_search as candidate
from academic_agent.report_evidence_catalog_qwen_transport import _contains_secret
from academic_agent.report_evidence_followup import _strict_json
from academic_agent.report_evidence_qwen_canary import (
    CanaryLedger, CanaryStopped, CONNECT_SECONDS, ENDPOINT, INPUT_RATE,
    INPUT_RESERVATION, MAX_TOKENS, MODEL, OUTPUT_RATE, REQUEST_BYTES,
    RESERVATION_USD, RESPONSE_BYTES, TOTAL_SECONDS, _encoded,
)
from academic_agent.report_evidence_qwen_transport import (
    QwenFollowupTransport, _project_message, _usage, validate_key,
)

METHOD_ID = "saved_source_candidate_query_v1"
TRANSPORT_IDENTITY = "saved_source_candidate_query_qwen_transport_v1"
MAX_REQUESTS = 1
MAX_ARGUMENT_BYTES = 4096
# These are actual direct/transitive local imports, not verified source hashes.
# Importing the scanner couples its catalog/stage modules, NOT their callbacks,
# fixtures or allowances. A later native protocol must freeze its own identities.
FROZEN_DEPENDENCY_COUPLING = (
    "src/academic_agent/saved_source_candidate_search.py",
    "src/academic_agent/report_evidence_catalog_qwen_transport.py",
    "src/academic_agent/report_evidence_catalog_followup.py",
    "src/academic_agent/report_evidence_stage_qwen_transport.py",
    "src/academic_agent/report_evidence_followup.py",
    "src/academic_agent/report_evidence_snapshot.py",
    "src/academic_agent/report_evidence_qwen_transport.py",
    "src/academic_agent/report_evidence_qwen_canary.py",
    "pyproject.toml", "uv.lock",
)
NATIVE_POLICY = (
    "Native wire encoding overrides the internal proposal-object notation: "
    "propose a query only by one search_saved_candidates function call with "
    "arguments {\"query\":\"...\"}, without assistant text. "
    "To decline, make no tool call and return exactly {\"action\":\"decline\"} "
    "as JSON content. Never put query JSON in content. No answer, explanation, "
    "source selection or second turn is requested."
)
_SAFE_ERRORS = frozenset({
    "batch_already_stopped", "unresolved_request", "request_limit", "budget_limit",
    "persistence_failed", "request_identity_mismatch", "conversation_closed",
    "invalid_request_contract", "invalid_request_body", "request_too_large",
    "secret_guard_unbound", "secret_guard_key_mismatch", "secret_in_request",
    "http_status_rejected", "response_encoding_rejected", "response_too_large",
    "invalid_response_protocol", "usage_unknown_or_contradictory",
    "unexpected_response_model", "token_reservation_exceeded", "secret_in_response",
    "invalid_query", "invalid_decline", "mixed_response", "unadvertised_tool",
    "provider_refusal", "request_timeout", "response_or_transport_failed",
    "synchronous_callback_required",
})


def candidate_query_qwen_configuration() -> dict:
    """Independent one-request engineering ceiling, never the old batch grant."""
    return {
        "model": MODEL, "endpoint": ENDPOINT, "method_id": METHOD_ID,
        "max_requests": MAX_REQUESTS, "reservation_usd": str(RESERVATION_USD),
        "max_reserved_usd": str(RESERVATION_USD),
        "input_rate_per_million": str(INPUT_RATE), "output_rate_per_million": str(OUTPUT_RATE),
        "price_scope": "frozen_conservative_estimate_not_invoice",
        "input_token_reservation": INPUT_RESERVATION, "max_tokens": MAX_TOKENS,
        "request_bytes": REQUEST_BYTES, "response_bytes": RESPONSE_BYTES,
        "raw_argument_bytes": MAX_ARGUMENT_BYTES, "proposal_bytes": candidate.MAX_PROPOSAL_BYTES,
        "question_characters": candidate.MAX_QUESTION_CHARS,
        "connect_seconds": CONNECT_SECONDS, "total_seconds": TOTAL_SECONDS,
        "stream": False, "enable_thinking": False, "parallel_tool_calls": False,
        "temperature": 0, "tool_choice": "auto", "response_format": "omitted",
        "retries": 0, "follow_redirects": False, "trust_env": False, "verify_tls": True,
        "callback_contract": "two_positional_exact_strings_plain_proposal",
        "max_local_reads": 0, "max_result_return_turns": 0,
        "ownership": "synchronous_single_owner_not_thread_safe",
        "ledger_construction": "fresh_directory_manifest_and_events_fsynced",
        "transport_construction": "no_io", "live_authorization": False,
    }


def _safe_code(value: object, fallback: str) -> str:
    return value if type(value) is str and value in _SAFE_ERRORS else fallback


def _safe_error(exc: Exception, fallback: str) -> str:
    # Even CanaryStopped can carry arbitrary provider text or a hostile __str__.
    if type(exc) is CanaryStopped and len(exc.args) == 1:
        return _safe_code(exc.args[0], fallback)
    return fallback


def _request(question: str) -> dict:
    return {
        "model": MODEL, "messages": [
            {"role": "system", "content": candidate.QUERY_POLICY},
            {"role": "system", "content": NATIVE_POLICY},
            {"role": "user", "content": question},
        ],
        "tools": [{"type": "function", "function": {
            "name": "search_saved_candidates",
            "description": "Propose one local saved-title/summary search query; no evidence read or answer.",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": candidate.MAX_QUERY_CHARS},
            }, "required": ["query"], "additionalProperties": False},
        }}],
        "tool_choice": "auto", "stream": False, "enable_thinking": False,
        "parallel_tool_calls": False, "temperature": 0, "max_tokens": MAX_TOKENS,
    }


class CandidateQueryQwenLedger(CanaryLedger):
    """One fresh synchronous owner's journal, not distributed quota or recovery.

    Guard state contains the explicit key in memory only. Reserve's global cap
    matters even when several transports were constructed before the first call.
    File fsync is not directory fsync or a power-loss/provider exactly-once claim.
    """

    def __init__(self, output_dir):
        self._guard_key: str | None = None
        super().__init__(output_dir, {
            "transport_identity": TRANSPORT_IDENTITY, "method_id": METHOD_ID,
            "scope": "offline_contract_no_live_authorization", "live_authorization": False,
            "configuration": candidate_query_qwen_configuration(),
            "journal_scope": "private_question_only_not_public_safe",
            "frozen_dependency_coupling": list(FROZEN_DEPENDENCY_COUPLING),
        })

    def bind_key(self, api_key: str) -> None:
        """No I/O, no key hash, and no replacement of an established scan guard."""
        validate_key(api_key)
        if self._guard_key is not None and api_key != self._guard_key:
            raise CanaryStopped("secret_guard_key_mismatch")
        if self.stop_reason is not None or self.pending is not None or self.records:
            raise CanaryStopped("fresh_candidate_query_ledger_required")
        self._guard_key = api_key

    def stop(self, reason: str) -> None:
        # A public inherited stop method must not become an exception-text sink.
        super().stop(_safe_code(reason, "response_or_transport_failed"))

    def reserve(self, body: dict) -> int:
        if self.stop_reason is not None:
            raise CanaryStopped("batch_already_stopped")
        if self.pending is not None:
            self.stop("unresolved_request")
            raise CanaryStopped("unresolved_request")
        if len(self.records) >= MAX_REQUESTS:
            self.stop("request_limit")
            raise CanaryStopped("request_limit")
        if self._guard_key is None:
            self.stop("secret_guard_unbound")
            raise CanaryStopped("secret_guard_unbound")
        # Screening belongs before inherited reserve, whose event stores the
        # entire request. It cannot be delegated to a later response check.
        if _contains_secret(body, self._guard_key):
            self.stop("secret_in_request")
            raise CanaryStopped("secret_in_request")
        if len(_encoded(body)) > REQUEST_BYTES:
            self.stop("request_too_large")
            raise CanaryStopped("request_too_large")
        self.case_id = None  # No borrowed runner/case metadata belongs in this scope.
        return super().reserve(body)

    def finish(self, ordinal: int, *, received: bool, usage: dict | None,
               error: str | None, message: dict | None = None,
               response_model_matches_authorized: bool | None = None) -> None:
        # Never persist a reply, even if a direct caller supplies the inherited
        # optional message argument. The transport's proposal is in-memory only.
        super().finish(ordinal, received=received, usage=usage,
                       error=None if error is None else _safe_code(error, "response_or_transport_failed"),
                       response_model_matches_authorized=response_model_matches_authorized)


def _scalar_payload(payload: dict) -> bool:
    pending = [payload]
    while pending:
        value = pending.pop()
        if type(value) is str:
            if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
                return False
        elif type(value) is dict:
            pending.extend(child for pair in value.items() for child in pair)
        elif type(value) is list:
            pending.extend(value)
    return True


def _proposal(message: dict) -> dict:
    if message.get("refusal"):
        raise CanaryStopped("provider_refusal")
    calls = message.get("tool_calls") or []
    if calls:
        if message.get("content"):
            raise CanaryStopped("mixed_response")
        function = calls[0]["function"]
        if function["name"] != "search_saved_candidates":
            raise CanaryStopped("unadvertised_tool")
        raw = function["arguments"]
        try:
            if len(raw.encode("utf-8")) > MAX_ARGUMENT_BYTES:
                raise ValueError("raw argument limit")
            action, query, _ = candidate._canonical_proposal(_strict_json(raw))
            if action != "query":
                raise ValueError("native query required")
        except (ValueError, TypeError, RecursionError):
            raise CanaryStopped("invalid_query") from None
        return {"query": query}
    try:
        action, _, _ = candidate._canonical_proposal(_strict_json(message.get("content") or ""))
        if action != "decline":
            raise ValueError("native no-call decline required")
    except (ValueError, TypeError, RecursionError):
        raise CanaryStopped("invalid_decline") from None
    return {"action": "decline"}


class CandidateQueryQwenTransport(QwenFollowupTransport):
    """Bind two callback strings without I/O; reuse ONLY the one-shot _post.

    No source object, catalog, live runner, ambient key or production config is
    accepted. The caller must own a synchronous context, not an active event loop.
    """

    def __init__(self, api_key: str, ledger: CandidateQueryQwenLedger, *, question: str):
        if type(ledger) is not CandidateQueryQwenLedger:
            raise CanaryStopped("candidate_query_ledger_required")
        if not candidate._scalars_string(question, candidate.MAX_QUESTION_CHARS):
            raise CanaryStopped("invalid_question")
        super().__init__(api_key, ledger)
        ledger.bind_key(api_key)
        self._question = question
        self._policy = candidate.QUERY_POLICY
        self._attempted = False

    def _stop(self, reason: str) -> None:
        reason = _safe_code(reason, "response_or_transport_failed")
        try:
            self.ledger.stop(reason)
        except Exception:  # noqa: BLE001 -- persistence diagnostics may expose paths/credentials.
            self.ledger.stop_reason = "persistence_failed"
            raise CanaryStopped("persistence_failed") from None
        raise CanaryStopped(reason) from None

    def __call__(self, question, policy, /):
        attempted = self._attempted
        self._attempted = True  # Invalid entry consumes this instance and stops its shared ledger.
        if self.ledger.stop_reason is not None:
            raise CanaryStopped("batch_already_stopped")
        if attempted:
            self._stop("conversation_closed")
        try:
            if (type(question) is not str or type(policy) is not str
                    or question != self._question or policy != self._policy
                    or policy != candidate.QUERY_POLICY):
                raise CanaryStopped("invalid_request_contract")
            # Check BEFORE creating a coroutine: asyncio.run's rejection alone
            # would leave an unawaited coroutine and misstate a possible POST.
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                pass
            else:
                raise CanaryStopped("synchronous_callback_required")
            body = _request(self._question)
            wire = _encoded(body)
            if len(wire) > REQUEST_BYTES:
                raise CanaryStopped("request_too_large")
        except Exception as exc:  # noqa: BLE001 -- callback inputs and helper diagnostics are untrusted.
            self._stop(_safe_error(exc, "invalid_request_body"))
        try:
            ordinal = self.ledger.reserve(body)
        except Exception as exc:  # noqa: BLE001 -- a failed fsync/reservation never permits dispatch.
            self._stop(_safe_error(exc, "persistence_failed"))

        observation = {"received": False}
        usage = proposal = error = model_matches = None
        try:
            raw = asyncio.run(self._post(wire, observation))
            payload = _strict_json(raw.decode("utf-8"))
            if type(payload) is not dict:
                raise CanaryStopped("invalid_response_protocol")
            model_matches = payload.get("model") == MODEL
            usage = _usage(payload)  # Valid accounting survives all later protocol failures.
            if usage is None:
                raise CanaryStopped("usage_unknown_or_contradictory")
            if not model_matches:
                raise CanaryStopped("unexpected_response_model")
            if usage["prompt_tokens"] > INPUT_RESERVATION or usage["completion_tokens"] > MAX_TOKENS:
                raise CanaryStopped("token_reservation_exceeded")
            if _contains_secret(payload, self._api_key):
                raise CanaryStopped("secret_in_response")
            if not _scalar_payload(payload):
                raise CanaryStopped("invalid_response_protocol")
            proposal = _proposal(_project_message(payload))
        except (TimeoutError, httpx.TimeoutException):
            error = "request_timeout"
        except Exception as exc:  # noqa: BLE001 -- never stringify even a malicious CanaryStopped.
            error = _safe_error(exc, "response_or_transport_failed")
        try:
            self.ledger.finish(ordinal, received=observation["received"], usage=usage, error=error,
                               response_model_matches_authorized=model_matches)
        except Exception:  # noqa: BLE001 -- retain spent intent and facts even if finish failed before entry.
            record = self.ledger.records[ordinal - 1]
            record.update(provider_response_received=observation["received"], protocol_accepted=False,
                          response_model_matches_authorized=model_matches, error="persistence_failed",
                          usage_status="complete" if usage is not None else "unknown")
            if usage is not None:
                record["reported_usage"] = dict(usage)
                record["estimated_usd"] = str((Decimal(usage["prompt_tokens"]) * INPUT_RATE
                                               + Decimal(usage["completion_tokens"]) * OUTPUT_RATE) / 1_000_000)
            self.ledger.pending = ordinal
            self.ledger.stop_reason = "persistence_failed"
            raise CanaryStopped("persistence_failed") from None
        if error is not None:
            raise CanaryStopped(error) from None
        return proposal
