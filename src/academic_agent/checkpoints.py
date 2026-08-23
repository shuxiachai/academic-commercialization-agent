"""Durable, content-addressed contracts for future node-level recovery.

This module deliberately does not decide when a CrewAI task may be skipped.
It supplies the smaller primitive that decision needs: a validated node output
can be committed atomically, and a later process can distinguish a reusable
checkpoint from a missing, stale, or corrupt one.

The distinction matters for paid work.  Treating an unreadable checkpoint as a
cache miss would silently repeat a model call; treating a merely stale one as
reusable would mix outputs produced from different evidence or prompts.  The
caller must therefore handle every inspection state explicitly.

Only hashes and non-secret model identity are persisted.  Provider credentials
are intentionally absent from these models, so a recovered BYOK run will still
need the user to supply fresh credentials.  Atomic persistence also does not
claim exactly-once provider execution: a process can die after a provider has
accepted a request but before its validated response is committed.  Recovery
is consequently at-least-once at that external boundary.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


NodeId = Literal[
    "retrieval",
    "academic",
    "patent",
    "market",
    "writer",
    "reviewer",
    "scorer",
]
OutputFormat = Literal["json", "markdown", "text"]
InspectionState = Literal["reusable", "missing", "mismatch", "corrupt"]

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
Sha256 = Annotated[str, Field(pattern=_SHA256_PATTERN)]
_OUTPUT_FILE_PATTERN = r"^output-[0-9a-f]{64}\.(?:json|md|txt)$"
_OUTPUT_EXTENSIONS: dict[OutputFormat, str] = {
    "json": "json",
    "markdown": "md",
    "text": "txt",
}


class _FrozenModel(BaseModel):
    """Reject schema drift and accidental reassignment in persisted contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelIdentity(_FrozenModel):
    """Non-secret model settings that can change a node's output.

    ``endpoint_sha256`` identifies a custom endpoint without persisting its URL.
    It is not an authentication mechanism; it only prevents accidental reuse
    across providers or gateways that may implement different model behaviour.
    """

    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=200)
    endpoint_sha256: Sha256 | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    response_format: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("provider", "model", "response_format")
    @classmethod
    def _strip_non_empty_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("model identity text must not be blank")
        return stripped


class CheckpointUsage(_FrozenModel):
    """Bounded accounting retained with a completed node.

    Token counters are kept separate because provider SDKs disagree on whether
    cached tokens are included in ``prompt_tokens``.  The store records the
    observed counters without trying to reinterpret them.
    """

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    cached_prompt_tokens: int = Field(default=0, ge=0)
    cache_creation_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    total_requests: int = Field(default=0, ge=0)
    cost_usd: float | None = Field(default=None, ge=0.0)
    cost_complete: bool = False


class CheckpointIdentity(_FrozenModel):
    """Everything that must match before a node result can be reused.

    The hashes are deliberately supplied by the orchestration layer.  That
    layer knows which topic, uploaded paper, evidence, prompt files, weight
    profile, and runtime settings reach each node; this storage primitive must
    not guess at those dependency seams.
    """

    node_id: NodeId
    input_sha256: Sha256
    evidence_sha256: Sha256
    config_sha256: Sha256
    upstream_sha256: dict[NodeId, Sha256] = Field(default_factory=dict)
    pipeline_revision: str = Field(min_length=1, max_length=200)
    as_of_date: date
    model: ModelIdentity | None = None

    @field_validator("pipeline_revision")
    @classmethod
    def _strip_revision(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("pipeline_revision must not be blank")
        return stripped

    @model_validator(mode="after")
    def _reject_self_dependency(self) -> CheckpointIdentity:
        if self.node_id in self.upstream_sha256:
            raise ValueError("a checkpoint cannot depend on its own output")
        return self


class CheckpointManifest(_FrozenModel):
    """The commit record written only after the output file is durable."""

    schema_version: Literal[1] = 1
    status: Literal["validated"] = "validated"
    identity: CheckpointIdentity
    identity_sha256: Sha256
    output_sha256: Sha256
    output_file: str = Field(pattern=_OUTPUT_FILE_PATTERN)
    output_format: OutputFormat
    output_bytes: int = Field(ge=0)
    completed_at: datetime
    usage: CheckpointUsage | None = None

    @field_validator("completed_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("completed_at must include a timezone")
        return value

    @model_validator(mode="after")
    def _require_content_addressed_filename(self) -> CheckpointManifest:
        extension = _OUTPUT_EXTENSIONS[self.output_format]
        expected = f"output-{self.output_sha256}.{extension}"
        if self.output_file != expected:
            raise ValueError("output_file must match output_sha256 and output_format")
        return self


@dataclass(frozen=True)
class CheckpointInspection:
    """One explicit inspection outcome; only ``reusable`` carries payload."""

    state: InspectionState
    reasons: tuple[str, ...] = ()
    manifest: CheckpointManifest | None = None
    payload: bytes | None = None

    def text(self) -> str:
        """Decode a reusable UTF-8 payload without hiding state mistakes."""

        if self.state != "reusable" or self.payload is None:
            raise RuntimeError(f"checkpoint is {self.state}, not reusable")
        return self.payload.decode("utf-8")


def hash_bytes(value: bytes) -> str:
    """Return the full SHA-256 digest used by persisted checkpoint contracts."""

    return hashlib.sha256(value).hexdigest()


def hash_text(value: str) -> str:
    """Hash UTF-8 text after normalising platform line endings.

    Line-ending normalisation prevents the same checked-out prompt from being
    treated as different on Linux and Windows.  No whitespace is stripped:
    leading, trailing, and repeated spaces can change an LLM request and must
    therefore change its identity.
    """

    normalised = value.replace("\r\n", "\n").replace("\r", "\n")
    return hash_bytes(normalised.encode("utf-8"))


def hash_json(value: object) -> str:
    """Hash canonical JSON while preserving semantic string content.

    Mapping keys are sorted and insignificant JSON whitespace is removed.  The
    function intentionally rejects NaN and non-JSON values instead of falling
    back to ``str(value)``; a lossy fallback could make two different runtime
    inputs appear reusable.
    """

    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hash_bytes(encoded)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Fsync a same-directory temporary file before atomically replacing path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        # A failed replace leaves only an unreferenced temporary file.  Cleanup
        # is best-effort because masking the original disk error would make the
        # recovery diagnosis less truthful.
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


class CheckpointStore:
    """Persist and inspect node checkpoints below one run directory."""

    def __init__(self, run_directory: Path | str):
        self.run_directory = Path(run_directory)
        self.root = self.run_directory / "checkpoints"

    def _node_directory(self, node_id: NodeId) -> Path:
        return self.root / node_id

    def _manifest_path(self, node_id: NodeId) -> Path:
        return self._node_directory(node_id) / "manifest.json"

    def commit(
        self,
        identity: CheckpointIdentity,
        output: str,
        *,
        output_format: OutputFormat,
        usage: CheckpointUsage | None = None,
        completed_at: datetime | None = None,
    ) -> CheckpointManifest:
        """Atomically publish one validated output.

        The content-addressed output is written first and the manifest is the
        commit point.  If the process fails between those writes, the old
        manifest still points to its unchanged payload and the new file is only
        an orphan.  Reusing a fixed output filename would corrupt the previous
        checkpoint in exactly that failure window.
        """

        payload = output.encode("utf-8")
        output_sha256 = hash_bytes(payload)
        extension = _OUTPUT_EXTENSIONS[output_format]
        output_file = f"output-{output_sha256}.{extension}"
        node_directory = self._node_directory(identity.node_id)
        manifest = CheckpointManifest(
            identity=identity,
            identity_sha256=hash_json(identity),
            output_sha256=output_sha256,
            output_file=output_file,
            output_format=output_format,
            output_bytes=len(payload),
            completed_at=completed_at or datetime.now(UTC),
            usage=usage,
        )

        # Do not delete superseded content-addressed outputs here.  A concurrent
        # reader may already have loaded the old manifest; pruning its payload
        # would turn a valid observation into a transient corruption report.
        _atomic_write_bytes(node_directory / output_file, payload)
        manifest_payload = (manifest.model_dump_json(indent=2) + "\n").encode("utf-8")
        _atomic_write_bytes(self._manifest_path(identity.node_id), manifest_payload)
        return manifest

    def inspect(self, expected: CheckpointIdentity) -> CheckpointInspection:
        """Classify the on-disk checkpoint without treating silence as a pass."""

        manifest_path = self._manifest_path(expected.node_id)
        try:
            raw_manifest = manifest_path.read_bytes()
        except FileNotFoundError:
            return CheckpointInspection("missing", ("manifest",))
        except OSError as exc:
            return CheckpointInspection("corrupt", (f"manifest_read:{type(exc).__name__}",))

        try:
            manifest = CheckpointManifest.model_validate_json(raw_manifest)
        except (ValidationError, ValueError) as exc:
            return CheckpointInspection("corrupt", (f"manifest_parse:{type(exc).__name__}",))

        actual_identity_sha256 = hash_json(manifest.identity)
        if manifest.identity_sha256 != actual_identity_sha256:
            return CheckpointInspection("corrupt", ("identity_sha256",), manifest)

        node_directory = self._node_directory(expected.node_id)
        output_path = node_directory / manifest.output_file
        try:
            resolved_node = node_directory.resolve()
            resolved_output = output_path.resolve(strict=True)
        except (FileNotFoundError, OSError) as exc:
            return CheckpointInspection(
                "corrupt",
                (f"output_resolve:{type(exc).__name__}",),
                manifest,
            )
        if resolved_output.parent != resolved_node or not resolved_output.is_file():
            return CheckpointInspection("corrupt", ("output_path",), manifest)

        try:
            payload = resolved_output.read_bytes()
        except OSError as exc:
            return CheckpointInspection(
                "corrupt",
                (f"output_read:{type(exc).__name__}",),
                manifest,
            )
        integrity_errors = []
        if len(payload) != manifest.output_bytes:
            integrity_errors.append("output_bytes")
        if hash_bytes(payload) != manifest.output_sha256:
            integrity_errors.append("output_sha256")
        if integrity_errors:
            return CheckpointInspection("corrupt", tuple(integrity_errors), manifest)

        expected_values = expected.model_dump(mode="json")
        actual_values = manifest.identity.model_dump(mode="json")
        mismatches = tuple(
            f"identity.{field_name}"
            for field_name in CheckpointIdentity.model_fields
            if actual_values[field_name] != expected_values[field_name]
        )
        if mismatches:
            return CheckpointInspection("mismatch", mismatches, manifest)

        return CheckpointInspection("reusable", (), manifest, payload)
