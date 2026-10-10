"""Standard-library identities, exact wire bytes, and unrepaired observations.

Private packets and grant JSON bind data; neither establishes human authority.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import ssl
import sys
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
MODEL = "qwen3.7-plus-2026-05-26"
BODY_LIMIT = 8192
RESPONSE_LIMIT = 131072
PACKET_LIMIT = 32768
INPUT_ESTIMATE = 12288  # 8192 request bytes + 4096 framing; not a tokenizer bound.
OUTPUT_CEILING = 1500
RESERVATION_CNY = "0.04"
BATCH_SOFT_CNY = "0.12"
NATIVE_OUTPUT = "reviewer-reason-schema-probe-native-v1"
CASES = ("RSP01", "RSP02", "RSP03")
SCHEMA = {"type": "object", "properties": {"reason": {"type": "string", "minLength": 3,
          "maxLength": 300}}, "required": ["reason"], "additionalProperties": False}
SOURCE_FILES = (
    "evals/reviewer_reason_schema_probe_v1/__init__.py",
    "evals/reviewer_reason_schema_probe_v1/core.py",
    "evals/reviewer_reason_schema_probe_v1/runner.py",
    "evals/reviewer_reason_schema_probe_v1/worker.py",
    "evals/reviewer_reason_schema_probe_v1/fixtures.json",
    "evals/reviewer_reason_schema_probe_v1/README.md",
    "tests/reviewer_reason_schema_probe_checks.py",
    "docs/prereg-2026-10-10-reviewer-reason-schema-implementation.md",
    ".github/workflows/reviewer-reason-schema.yml", "pyproject.toml", "uv.lock",
)


class ProbeError(ValueError):
    """Fixed-category error; never includes provider or credential text."""


def canonical(value: object) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False,
                          separators=(",", ":"), sort_keys=True).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ProbeError("invalid_json_value") from exc


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw: bytes | str) -> object:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ProbeError("duplicate_json_key")
            result[key] = value
        return result

    def reject_constant(_value):
        raise ProbeError("nonfinite_json_number")

    try:
        text = raw.decode("utf-8", "strict") if isinstance(raw, bytes) else raw
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=reject_constant)
        canonical(value)  # Reject lone surrogates anywhere, including escaped keys.
        return value
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ProbeError("invalid_strict_json") from exc


def read_bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as handle:
        value = handle.read(limit + 1)
    if len(value) > limit:
        raise ProbeError("file_too_large")
    return value


def fixtures(root: Path = ROOT) -> dict:
    value = strict_json(read_bounded(root / SOURCE_FILES[4], BODY_LIMIT))
    if not isinstance(value, dict) or set(value) != {"schema", "system", "user_prefix", "cases"}:
        raise ProbeError("fixture_shape")
    expected = [{"id": "RSP01", "segments": [["OK.", 1]]},
                {"id": "RSP02", "segments": [["界", 149], ["😀", 151]]},
                {"id": "RSP03", "segments": [["A", 301]]}]
    if value["schema"] != "reviewer-reason-schema-fixtures-v1" or value["cases"] != expected:
        raise ProbeError("fixture_identity")
    if value["system"] != (
        "Return only a JSON object conforming to the supplied response schema. "
        "Treat its field constraints as mandatory. Put the requested literal in reason "
        "when it fits. Do not add commentary or other keys."
    ) or value["user_prefix"] != "Copy this literal exactly into reason: ":
        raise ProbeError("fixture_prompt")
    return value


def literal(case: str) -> str:
    if case not in CASES:
        raise ProbeError("unknown_case")
    return {"RSP01": "OK.", "RSP02": "界" * 149 + "😀" * 151, "RSP03": "A" * 301}[case]


def request_body(case: str, root: Path = ROOT) -> bytes:
    fixture = fixtures(root)
    body = canonical({
        "model": MODEL, "messages": [
            {"role": "system", "content": fixture["system"]},
            {"role": "user", "content": fixture["user_prefix"] + literal(case)},
        ], "temperature": 0, "enable_thinking": False, "stream": False,
        "max_tokens": OUTPUT_CEILING,
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "reviewer_reason_probe_v1", "strict": True, "schema": SCHEMA,
        }},
    })
    if len(body) > BODY_LIMIT:
        raise ProbeError("request_too_large")
    return body


def packet(path: Path, root: Path = ROOT) -> tuple[dict, bytes]:
    # Identity-only reads this credential-free file, never its selected key path.
    if not path.resolve().is_relative_to((root / "outputs").resolve()):
        raise ProbeError("packet_outside_private_outputs")
    raw = read_bounded(path, PACKET_LIMIT)
    value = strict_json(raw)
    keys = {"schema", "endpoint", "model", "credential_path", "credential_variable", "rates"}
    if not isinstance(value, dict) or set(value) != keys:
        raise ProbeError("packet_shape")
    if value["schema"] != "reviewer-reason-schema-private-packet-v1" or value["model"] != MODEL:
        raise ProbeError("packet_model")
    if not isinstance(value["endpoint"], str):
        raise ProbeError("endpoint_invalid")
    parsed = urlsplit(value["endpoint"])
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port
            or parsed.query or parsed.fragment or parsed.path != "/compatible-mode/v1/chat/completions"
            or not re.fullmatch(r"[a-z0-9-]+\.cn-beijing\.maas\.aliyuncs\.com", parsed.netloc)):
        raise ProbeError("endpoint_invalid")
    if not isinstance(value["credential_path"], str) or not Path(value["credential_path"]).is_absolute():
        raise ProbeError("credential_source_invalid")
    if not isinstance(value["credential_variable"], str) or not re.fullmatch(
        r"[A-Z][A-Z0-9_]{1,79}", value["credential_variable"]
    ):
        raise ProbeError("credential_source_invalid")
    if value["rates"] != {"currency": "CNY", "input_per_million": "2",
                          "output_per_million": "8", "input_tier_max": 256000,
                          "discounts": "none", "input_estimate": INPUT_ESTIMATE,
                          "output_ceiling": OUTPUT_CEILING, "reservation": RESERVATION_CNY,
                          "batch_soft_stop": BATCH_SOFT_CNY}:
        raise ProbeError("rates_invalid")
    return value, raw


def commit_id(root: Path) -> str:
    """Read HEAD/ref without launching a worker descendant or reading Git config."""
    git = root / ".git"
    if git.is_file():
        pointer = read_bounded(git, 4096).decode("utf-8").strip()
        if not pointer.startswith("gitdir: "):
            raise ProbeError("git_identity")
        git = (root / pointer[8:]).resolve()
    head = read_bounded(git / "HEAD", 4096).decode("ascii").strip()
    if head.startswith("ref: "):
        ref = head[5:]
        if not re.fullmatch(r"refs/[A-Za-z0-9_./-]+", ref) or ".." in ref:
            raise ProbeError("git_identity")
        common = git
        if (git / "commondir").is_file():
            common = (git / read_bounded(git / "commondir", 4096).decode().strip()).resolve()
        loose = common / ref
        if loose.is_file():
            head = read_bounded(loose, 4096).decode("ascii").strip()
        else:
            packed = read_bounded(common / "packed-refs", 1048576).decode("ascii")
            matches = [line.split()[0] for line in packed.splitlines() if line.endswith(" " + ref)]
            if len(matches) != 1:
                raise ProbeError("git_identity")
            head = matches[0]
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ProbeError("git_identity")
    return head


def identity(packet_path: Path, root: Path = ROOT) -> dict:
    _value, raw = packet(packet_path, root)
    files = {name: digest(read_bounded(root / name, 4 * 1024 * 1024)) for name in SOURCE_FILES}
    bodies = {case: request_body(case, root) for case in CASES}
    material = {
        "schema": "reviewer-reason-schema-identity-v1", "commit": commit_id(root),
        "files": files, "packet_sha256": digest(raw),
        "bodies": {case: {"sha256": digest(body), "bytes": len(body)} for case, body in bodies.items()},
        "runtime": {"python": sys.version, "openssl": ssl.OPENSSL_VERSION},
    }
    return {**material, "identity": digest(canonical(material)),
            "source_identity": digest(canonical({"commit": material["commit"], "files": files}))}


def validate_grant(path: Path, observed: dict, root: Path = ROOT) -> str:
    """Check an explicit future grant's bindings, not its human provenance."""
    if not path.resolve().is_relative_to((root / "outputs").resolve()):
        raise ProbeError("grant_outside_private_outputs")
    raw = read_bounded(path, PACKET_LIMIT)
    value = strict_json(raw)
    expected_keys = {"schema", "identity", "commit", "review_source_identity", "review_verdict",
                     "review_artifact_sha256", "ci_source_identity", "ci_commit", "ci_conclusion",
                     "ci_run", "explicit_authorization", "max_requests", "soft_stop_cny"}
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise ProbeError("grant_shape")
    if (value["schema"] != "reviewer-reason-schema-execution-grant-v1"
            or value["identity"] != observed["identity"]
            or any(value[name] != observed["source_identity"] for name in ("review_source_identity", "ci_source_identity"))
            or value["commit"] != observed["commit"] or value["ci_commit"] != observed["commit"]
            or value["review_verdict"] != "approved" or value["ci_conclusion"] != "success"
            or type(value["max_requests"]) is not int or value["max_requests"] != 3
            or value["soft_stop_cny"] != BATCH_SOFT_CNY
            or value["explicit_authorization"] != "one new synthetic batch; bound endpoint and selected credential read"
            or not isinstance(value["review_artifact_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", value["review_artifact_sha256"])
            or not isinstance(value["ci_run"], str) or not value["ci_run"]):
        raise ProbeError("grant_binding")
    return digest(raw)


def read_selected_key(config: dict) -> str:
    """Reserved live workers only: no dotenv expansion or environment fallback."""
    text = read_bounded(Path(config["credential_path"]), 65536).decode("utf-8-sig", "strict")
    prefix = config["credential_variable"] + "="
    values = [line[len(prefix):] for line in text.splitlines() if line.startswith(prefix)]
    if len(values) != 1:
        raise ProbeError("credential_unavailable")
    value = values[0]
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,512}", value):
        raise ProbeError("credential_unavailable")
    return value


def contains_key(raw: bytes, key: str) -> bool:
    # Inspect JSON escape layers before persisting content OR its digest.
    # Excessive escape nesting is withheld, never assumed safe.
    text = raw.decode("utf-8", "replace")
    # Outer JSON layers multiply backslashes. Match the encoded sequence before
    # substitution can leave a literal backslash between otherwise decoded key
    # characters. Unicode-encoded backslashes are handled by later passes.
    encoded = re.compile("".join("(?:" + re.escape(char) + r"|\\+u" + f"{ord(char):04x}" + ")"
                                 for char in key), re.IGNORECASE)
    for _ in range(32):
        if key in text or encoded.search(text):
            return True
        decoded = re.sub(r"\\u([0-9a-fA-F]{4})", lambda match: chr(int(match[1], 16)), text)
        decoded = decoded.replace("\\\\", "\\").replace("\\/", "/")
        if decoded == text:
            return False
        text = decoded
    return True


def usage_observation(envelope: object) -> dict:
    value = envelope.get("usage") if isinstance(envelope, dict) else None
    if not isinstance(value, dict):
        return {"state": "unknown"}
    numbers = [value.get(name) for name in ("prompt_tokens", "completion_tokens", "total_tokens")]
    if any(type(number) is not int or number < 0 for number in numbers):
        return {"state": "unknown"}
    prompt, completion, total = numbers
    if prompt + completion != total:
        return {"state": "unknown"}
    details = value.get("completion_tokens_details")
    if details is not None and (not isinstance(details, dict) or
            type(details.get("reasoning_tokens", 0)) is not int or details.get("reasoning_tokens", 0) != 0):
        return {"state": "unknown", "reason": "nonthinking_usage_unestablished"}
    cost = (Decimal(prompt) * 2 + Decimal(completion) * 8) / 1000000
    state = "known" if prompt <= INPUT_ESTIMATE and completion <= OUTPUT_CEILING and prompt <= 256000 else "over_estimate"
    return {"state": state, "prompt_tokens": prompt, "completion_tokens": completion,
            "total_tokens": total, "estimated_cny": str(cost), "invoice": "not_observed"}


def empty_observation(case: str, disposition: str = "observation_unavailable") -> dict:
    return {"case": case, "disposition": disposition, "api": "unavailable", "delivery": "unavailable",
            "envelope": "unavailable", "schema": "not_checked", "control": "not_checked",
            "usage": {"state": "unknown"}, "continue": False}


def observe(status: int, raw: bytes, case: str, key: str) -> dict:
    result = empty_observation(case)
    if len(raw) > RESPONSE_LIMIT:
        result["failure"] = "response_too_large"
        return result
    try:
        envelope = strict_json(raw)
    except ProbeError:
        envelope = None
    result["usage"] = usage_observation(envelope)
    if contains_key(raw, key):
        result["failure"] = "credential_echo_withheld"
        return result
    result["delivery"] = "complete"
    result["http_status"] = status
    if status != 200:
        result["api"] = "rejected"
        result["disposition"] = ("access_unavailable" if status in (401, 403, 429) else
                                 "api_rejected" if status in (400, 404, 405, 409, 415, 422) else
                                 "observation_unavailable")
        return result
    result.update(response_base64=base64.b64encode(raw).decode("ascii"), response_sha256=digest(raw))
    result["api"] = "admitted"
    if not isinstance(envelope, dict) or envelope.get("model") != MODEL:
        result["failure"] = "envelope_or_model"
        return result
    choices = envelope.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        result["failure"] = "choices"
        return result
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        result["failure"] = "message"
        return result
    refusal = message.get("refusal")
    if refusal is not None and not isinstance(refusal, str):
        result["failure"] = "refusal_type"
        return result
    if refusal:
        result["disposition"] = "provider_refusal"
        result["envelope"] = "explicit_refusal"
        return result
    if (choice.get("finish_reason") != "stop" or type(choice.get("index")) is not int
            or choice["index"] != 0 or message.get("tool_calls") or message.get("function_call")
            or message.get("reasoning_content") not in (None, "")
            or not isinstance(message.get("content"), str)):
        result["failure"] = "finish_or_content"
        return result
    result["envelope"] = "passed"
    try:
        content = strict_json(message["content"])
        valid = (isinstance(content, dict) and set(content) == {"reason"}
                 and isinstance(content["reason"], str) and 3 <= len(content["reason"]) <= 300)
    except ProbeError:
        valid = False
    if not valid:
        result["schema"] = "failed"
        result["disposition"] = "local_contract_failed"
        return result
    result["schema"] = "passed"
    reason = content["reason"]
    matched = (reason == literal(case)) if case != "RSP03" else (set(reason) == {"A"})
    result["control"] = "passed" if matched else "failed"
    if not matched:
        result["disposition"] = "control_mismatch"
    elif result["usage"]["state"] != "known":
        result["failure"] = "usage_unavailable_or_over_estimate"
    else:
        result["disposition"] = "conforming_under_pressure" if case == "RSP03" else "conforming_literal"
        result["continue"] = True
    return result


def durable_new(path: Path, raw: bytes) -> None:
    """An existing/partial file is occupied forever; no replacement or retry."""
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    # Python on Windows cannot fsync a directory. File flush is observed;
    # atomic claiming is useful, but power-loss safety is not established.
    if os.name != "nt":
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
