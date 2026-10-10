"""One reserved slot, one HTTPS POST, no threads, descendants, retry or proxy.

Only the parent owns wall time. Socket timeout is an additional bound, not proof
of remote cancellation. Invocation requires a fresh explicit external grant.
"""

from __future__ import annotations

import argparse
import http.client
import ssl
import sys
from pathlib import Path
from urllib.parse import urlsplit

# -I -S invocation deliberately does not use project packages or site startup.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evals.reviewer_reason_schema_probe_v1 import core


def send_frozen(connection, actual: bytes, frozen: bytes) -> None:
    """The comparison is immediately at the actual HTTP body send boundary."""
    if not isinstance(actual, bytes) or actual != frozen or len(actual) > core.BODY_LIMIT:
        raise core.ProbeError("wire_bytes_changed")
    connection.send(actual)


def one_post(endpoint: str, body: bytes, frozen: bytes, key: str, case: str) -> dict:
    if body != frozen or len(body) > core.BODY_LIMIT:
        raise core.ProbeError("wire_bytes_changed")
    parsed = urlsplit(endpoint)
    connection = http.client.HTTPSConnection(parsed.hostname, timeout=90, context=ssl.create_default_context())
    # HTTPSConnection connects directly: no environment proxies, redirects or SDK.
    result = core.empty_observation(case)
    try:
        connection.putrequest("POST", parsed.path, skip_accept_encoding=True)
        connection.putheader("Authorization", "Bearer " + key)
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", str(len(body)))
        connection.putheader("Connection", "close")
        connection.endheaders()
        send_frozen(connection, body, frozen)
        response = connection.getresponse()
        raw = response.read(core.RESPONSE_LIMIT + 1)
        if response.getheader("Content-Encoding", "identity") != "identity":
            result["failure"] = "response_encoding"
        else:
            result = core.observe(response.status, raw, case, key)
            length = response.getheader("Content-Length")
            if length is not None and (not length.isascii() or not length.isdecimal() or int(length) != len(raw)):
                result.update(delivery="unavailable", disposition="observation_unavailable", failure="incomplete_body")
                result["continue"] = False
        result["wire_sha256"] = core.digest(body)
        return result
    except (OSError, ValueError, http.client.HTTPException):
        # Raw exceptions may contain headers/provider text. Never print or persist them.
        result["continue"] = False
        result["disposition"] = "observation_unavailable"
        result["delivery"] = "unavailable"
        result["failure"] = "transport_unavailable"
        return result
    finally:
        connection.close()


def execute(packet_path: Path, grant_path: Path, expected: str, case: str, root: Path = core.ROOT) -> dict:
    observed = core.identity(packet_path, root)
    if observed["identity"] != expected:
        raise core.ProbeError("identity_changed")
    grant_hash = core.validate_grant(grant_path, observed, root)
    output = root / "outputs" / core.NATIVE_OUTPUT
    reservation = core.strict_json(core.read_bounded(output / (case + ".reservation.json"), 4096))
    required = {"schema": "reviewer-reason-schema-reservation-v1", "case": case,
                "identity": expected, "grant_sha256": grant_hash,
                "body_sha256": observed["bodies"][case]["sha256"], "reserved_cny": core.RESERVATION_CNY}
    if reservation != required:
        raise core.ProbeError("reservation_invalid")
    body = core.read_bounded(output / (case + ".request.json"), core.BODY_LIMIT)
    frozen = core.request_body(case, root)
    if body != frozen or core.digest(body) != reservation["body_sha256"]:
        raise core.ProbeError("wire_bytes_changed")
    # A second worker cannot spend the same reservation, even after parent failure.
    core.durable_new(output / (case + ".dispatch-claimed.json"), core.canonical({"identity": expected}))
    config, raw = core.packet(packet_path, root)
    # Bind the actual configuration used below, not merely an earlier read.
    if core.digest(raw) != observed["packet_sha256"]:
        raise core.ProbeError("packet_changed_after_claim")
    key = core.read_selected_key(config)
    return one_post(config["endpoint"], body, frozen, key, case)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--grant", type=Path, required=True)
    parser.add_argument("--expected-identity", required=True)
    parser.add_argument("--case", choices=core.CASES, required=True)
    args = parser.parse_args(argv)
    result = core.empty_observation(args.case)
    try:
        if not args.live:
            raise core.ProbeError("live_not_selected")
        result = execute(args.packet, args.grant, args.expected_identity, args.case)
    except Exception:  # noqa: BLE001 -- child boundary must never emit secrets or raw tracebacks.
        result["failure"] = "worker_preflight_or_persistence_failed"
    sys.stdout.buffer.write(core.canonical(result))
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
