"""OpenTelemetry/OpenInference adapter for the six-agent pipeline.

The files in ``outputs/<run_id>/`` remain the run's source of truth. Traces are
an optional projection for diagnosis: losing the collector must never lose a
paid report, and a trace must never contain the capability-bearing run id,
paper text, prompt, or model output.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from importlib.util import find_spec
from typing import Any, Literal, TypedDict


class ObservabilitySnapshot(TypedDict, total=False):
    """JSON-safe state written to status.json and exposed by the API."""

    state: Literal["disabled", "active", "degraded"]
    backend: str
    project_name: str
    trace_id: str | None
    delivery: Literal["not_configured", "pending", "attempted", "timed_out"]
    content_capture: Literal["redacted"]
    error_type: str


_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"", "0", "false", "no", "off"})
_DEFAULT_PROJECT = "academic-commercialization-agent"
_DEFAULT_FLUSH_TIMEOUT_MS = 2_000


class InstrumentationActivationError(RuntimeError):
    """An instrumentor returned without becoming active."""


def _enabled_setting() -> tuple[bool, str | None]:
    """Parse the explicit opt-in without treating a typo as "disabled".

    Silent disablement would make an operator believe a run was observed when
    no exporter was ever configured. An invalid value is therefore degraded,
    distinct from both an intentional off switch and an active tracer.
    """
    raw = os.getenv("AGENT_OBSERVABILITY_ENABLED", "").strip().lower()
    if raw in _TRUE:
        return True, None
    if raw in _FALSE:
        return False, None
    return False, "InvalidConfiguration"


def _flush_timeout_ms() -> int:
    raw = os.getenv(
        "AGENT_OBSERVABILITY_FLUSH_TIMEOUT_MS",
        str(_DEFAULT_FLUSH_TIMEOUT_MS),
    )
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_FLUSH_TIMEOUT_MS
    # A zero timeout cannot export anything; an unbounded timeout lets an
    # optional collector delay the paid result indefinitely.
    return min(max(value, 100), 10_000)


def _run_fingerprint(run_id: str) -> str:
    """Correlate traces without exporting the run id, which is a credential."""
    return hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:16]


def _create_provider(project_name: str) -> Any:
    """Create a Phoenix-aware provider without replacing CrewAI's provider."""
    from phoenix.otel import register

    # CrewAI 1.14.7 installs its own global provider. Overwriting it emits a
    # warning and can redirect framework telemetry unexpectedly, so both our
    # manual spans and the instrumentors below receive this provider directly.
    return register(
        project_name=project_name,
        batch=True,
        auto_instrument=False,
        set_global_tracer_provider=False,
        verbose=False,
    )


def _activate_instrumentor(instrumentor: Any, provider: Any, config: Any) -> None:
    """Fail setup when OpenTelemetry only logged a dependency conflict."""
    instrumentor.instrument(
        tracer_provider=provider,
        config=config,
    )
    if not instrumentor.is_instrumented_by_opentelemetry:
        raise InstrumentationActivationError(
            f"{type(instrumentor).__name__} did not become active"
        )


def _instrument_provider(provider: Any) -> None:
    """Attach framework and provider-SDK spans with content capture disabled."""
    from openinference.instrumentation import TraceConfig
    from openinference.instrumentation.crewai import CrewAIInstrumentor
    from openinference.instrumentation.openai import OpenAIInstrumentor

    # Code-level configuration takes precedence over environment variables.
    # That is deliberate: a deployment typo must not upload an unpublished
    # paper, system prompt, model answer, embedding text, or advertised tools.
    config = TraceConfig(
        hide_inputs=True,
        hide_outputs=True,
        hide_llm_invocation_parameters=True,
        hide_llm_tools=True,
        hide_embeddings_text=True,
        hide_embeddings_vectors=True,
    )
    _activate_instrumentor(CrewAIInstrumentor(), provider, config)
    # CrewAI 1.14.7 no longer uses LiteLLM: DeepSeek and OpenAI both call the
    # OpenAI SDK through OpenAICompletion. Instrumenting LiteLLM looked valid
    # but produced no model spans, so the adapter follows the resolved provider
    # classes instead of a historical framework dependency.
    _activate_instrumentor(OpenAIInstrumentor(), provider, config)

    # Anthropic is an optional CrewAI extra and is not installed in a default
    # DeepSeek/OpenAI deployment. Calling its instrumentor without the target
    # SDK only logs a dependency conflict and leaves tracing inactive, which is
    # indistinguishable from a successful check unless we gate it explicitly.
    if find_spec("anthropic") is not None:
        from openinference.instrumentation.anthropic import AnthropicInstrumentor

        _activate_instrumentor(AnthropicInstrumentor(), provider, config)


def _span_kind(value: str) -> Any:
    from openinference.semconv.trace import OpenInferenceSpanKindValues

    return OpenInferenceSpanKindValues(value)


class RunTelemetry:
    """Best-effort Trace lifecycle owned by one worker subprocess."""

    def __init__(
        self,
        snapshot: ObservabilitySnapshot,
        *,
        provider: Any = None,
        tracer: Any = None,
        root_span: Any = None,
        context_api: Any = None,
        context_token: Any = None,
    ) -> None:
        self._snapshot = snapshot
        self._provider = provider
        self._tracer = tracer
        self._root_span = root_span
        self._context_api = context_api
        self._context_token = context_token
        self._finished = False

    def snapshot(self) -> ObservabilitySnapshot:
        """Return a copy so status serialization cannot mutate our state."""
        return dict(self._snapshot)  # type: ignore[return-value]

    def _degrade(self, error: BaseException | str) -> None:
        self._snapshot["state"] = "degraded"
        self._snapshot["error_type"] = (
            error if isinstance(error, str) else type(error).__name__
        )

    @contextmanager
    def span(
        self,
        name: str,
        kind: str,
        attributes: Mapping[str, str | bool | int | float] | None = None,
    ) -> Iterator[Any | None]:
        """Create one domain span, or a no-op when tracing is unavailable."""
        if self._tracer is None:
            yield None
            return
        try:
            manager = self._tracer.start_as_current_span(
                name,
                attributes=dict(attributes or {}),
                record_exception=False,
                set_status_on_exception=False,
                openinference_span_kind=_span_kind(kind),
            )
            span = manager.__enter__()
        except Exception as exc:  # noqa: BLE001 - tracing is not the paid operation
            self._degrade(exc)
            yield None
            return

        try:
            yield span
        except BaseException as operation_error:
            # OTel's default exception event includes the exception message,
            # which can contain user text or a source URL. Record only the
            # class, then preserve the pipeline exception even if telemetry
            # fails while closing the span.
            try:
                from opentelemetry.trace import Status, StatusCode

                span.set_attribute(
                    "academic_agent.error.type", type(operation_error).__name__
                )
                span.set_status(Status(StatusCode.ERROR, type(operation_error).__name__))
            except Exception as telemetry_error:  # noqa: BLE001 - preserve operation error
                self._degrade(telemetry_error)
            try:
                manager.__exit__(
                    type(operation_error), operation_error,
                    operation_error.__traceback__,
                )
            except Exception as telemetry_error:  # noqa: BLE001 - preserve operation error
                self._degrade(telemetry_error)
            raise
        else:
            try:
                manager.__exit__(None, None, None)
            except Exception as exc:  # noqa: BLE001 - tracing cannot fail a paid run
                self._degrade(exc)

    def set_attributes(
        self,
        attributes: Mapping[str, str | bool | int | float | None],
    ) -> None:
        if self._root_span is None:
            return
        try:
            for key, value in attributes.items():
                if value is not None:
                    self._root_span.set_attribute(key, value)
        except Exception as exc:  # noqa: BLE001 - metrics cannot fail a paid run
            self._degrade(exc)

    def finish(self, error: BaseException | None = None) -> None:
        """End and bounded-flush the Trace without raising into the run."""
        if self._finished:
            return
        self._finished = True
        if self._root_span is None:
            return

        try:
            from opentelemetry.trace import Status, StatusCode

            if error is None:
                self._root_span.set_status(Status(StatusCode.OK))
            else:
                # record_exception includes the exception message, which can
                # contain a source URL or user text. Type-only status preserves
                # the diagnostic category without exporting that content.
                self._root_span.set_attribute(
                    "academic_agent.error.type", type(error).__name__
                )
                self._root_span.set_status(
                    Status(StatusCode.ERROR, type(error).__name__)
                )
            self._context_api.detach(self._context_token)
            self._root_span.end()
        except Exception as exc:  # noqa: BLE001 - telemetry must not fail a paid run
            self._degrade(exc)
            try:
                # End is idempotent in OTel. Trying it here avoids leaking a
                # span when detach or status assignment was the failing call.
                self._root_span.end()
            except Exception:  # noqa: BLE001 - nothing else is safe to do here
                pass

        try:
            flushed = bool(
                self._provider.force_flush(timeout_millis=_flush_timeout_ms())
            )
        except Exception as exc:  # noqa: BLE001 - telemetry must not fail a paid run
            self._degrade(exc)
            self._snapshot["delivery"] = "timed_out"
            return
        self._snapshot["delivery"] = "attempted" if flushed else "timed_out"
        if not flushed:
            self._degrade("FlushTimeout")


def start_run_telemetry(run_id: str, *, topic_length: int) -> RunTelemetry:
    """Start an opt-in root Trace, returning a no-op/degraded object on failure."""
    enabled, configuration_error = _enabled_setting()
    if configuration_error is not None:
        return RunTelemetry({
            "state": "degraded",
            "backend": "phoenix",
            "trace_id": None,
            "delivery": "not_configured",
            "content_capture": "redacted",
            "error_type": configuration_error,
        })
    if not enabled:
        return RunTelemetry({
            "state": "disabled",
            "backend": "phoenix",
            "trace_id": None,
            "delivery": "not_configured",
            "content_capture": "redacted",
        })

    project_name = os.getenv("PHOENIX_PROJECT_NAME", _DEFAULT_PROJECT).strip()
    project_name = project_name or _DEFAULT_PROJECT
    try:
        provider = _create_provider(project_name)
        _instrument_provider(provider)
        tracer = provider.get_tracer("academic_agent.pipeline")

        from opentelemetry import context as context_api
        from opentelemetry import trace as trace_api

        root_span = tracer.start_span(
            "commercialization_assessment",
            attributes={
                "academic_agent.run_fingerprint": _run_fingerprint(run_id),
                "academic_agent.topic.characters": topic_length,
                "academic_agent.pipeline.agents": 6,
            },
            openinference_span_kind=_span_kind("CHAIN"),
        )
        token = context_api.attach(trace_api.set_span_in_context(root_span))
        span_context = root_span.get_span_context()
        trace_id = (
            f"{span_context.trace_id:032x}" if span_context.is_valid else None
        )
        return RunTelemetry(
            {
                "state": "active",
                "backend": "phoenix",
                "project_name": project_name,
                "trace_id": trace_id,
                # "attempted" after flush still does not claim the remote
                # collector persisted it; that acknowledgement is unavailable.
                "delivery": "pending",
                "content_capture": "redacted",
            },
            provider=provider,
            tracer=tracer,
            root_span=root_span,
            context_api=context_api,
            context_token=token,
        )
    except Exception as exc:  # noqa: BLE001 - optional telemetry cannot block analysis
        return RunTelemetry({
            "state": "degraded",
            "backend": "phoenix",
            "project_name": project_name,
            "trace_id": None,
            "delivery": "not_configured",
            "content_capture": "redacted",
            "error_type": type(exc).__name__,
        })
