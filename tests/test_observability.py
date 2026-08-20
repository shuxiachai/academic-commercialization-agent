"""Offline contracts for the optional OpenTelemetry/OpenInference adapter.

These tests use an in-memory exporter. A test that reaches Phoenix would turn
the suite's reliability check into a network dependency and, worse, could
upload the literal secrets below while appearing to pass.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from openinference.instrumentation import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from academic_agent.observability import RunTelemetry, start_run_telemetry
from academic_agent.observability.tracing import _instrument_provider


class ObservabilityConfigurationTests(unittest.TestCase):

    def test_disabled_is_explicit_and_imports_no_backend(self) -> None:
        with patch.dict(os.environ, {}, clear=True), \
             patch("academic_agent.observability.tracing._create_provider") as create:
            telemetry = start_run_telemetry("secret-run-capability", topic_length=12)

        self.assertEqual(telemetry.snapshot(), {
            "state": "disabled",
            "backend": "phoenix",
            "trace_id": None,
            "delivery": "not_configured",
            "content_capture": "redacted",
        })
        create.assert_not_called()

    def test_invalid_switch_is_degraded_not_silently_disabled(self) -> None:
        with patch.dict(
            os.environ, {"AGENT_OBSERVABILITY_ENABLED": "perhaps"}, clear=True
        ):
            snapshot = start_run_telemetry("run-id", topic_length=3).snapshot()

        self.assertEqual(snapshot["state"], "degraded")
        self.assertEqual(snapshot["error_type"], "InvalidConfiguration")

    def test_setup_failure_never_exposes_the_exception_message(self) -> None:
        with patch.dict(
            os.environ, {"AGENT_OBSERVABILITY_ENABLED": "true"}, clear=True
        ), patch(
            "academic_agent.observability.tracing._create_provider",
            side_effect=RuntimeError("collector failed with api-key-secret"),
        ):
            snapshot = start_run_telemetry("run-id", topic_length=3).snapshot()

        self.assertEqual(snapshot["state"], "degraded")
        self.assertEqual(snapshot["error_type"], "RuntimeError")
        self.assertNotIn("api-key-secret", str(snapshot))

    def test_provider_instrumentors_receive_code_enforced_redaction(self) -> None:
        with patch(
            "openinference.instrumentation.crewai.CrewAIInstrumentor"
        ) as crewai_instrumentor, patch(
            "openinference.instrumentation.openai.OpenAIInstrumentor"
        ) as openai_instrumentor, patch(
            "academic_agent.observability.tracing.find_spec", return_value=object()
        ), patch(
            "openinference.instrumentation.anthropic.AnthropicInstrumentor"
        ) as anthropic_instrumentor:
            provider = object()
            _instrument_provider(provider)

        crew_call = crewai_instrumentor.return_value.instrument.call_args
        openai_call = openai_instrumentor.return_value.instrument.call_args
        anthropic_call = anthropic_instrumentor.return_value.instrument.call_args
        self.assertIs(crew_call.kwargs["tracer_provider"], provider)
        self.assertIs(openai_call.kwargs["tracer_provider"], provider)
        self.assertIs(anthropic_call.kwargs["tracer_provider"], provider)
        config = crew_call.kwargs["config"]
        self.assertIs(config, openai_call.kwargs["config"])
        self.assertIs(config, anthropic_call.kwargs["config"])
        self.assertTrue(config.hide_inputs)
        self.assertTrue(config.hide_outputs)
        self.assertTrue(config.hide_llm_tools)
        self.assertTrue(config.hide_llm_invocation_parameters)
        self.assertTrue(config.hide_embeddings_text)
        self.assertTrue(config.hide_embeddings_vectors)

    def test_inactive_instrumentor_is_a_setup_failure_not_a_silent_pass(self) -> None:
        crewai_instrumentor = MagicMock()
        crewai_instrumentor.is_instrumented_by_opentelemetry = True
        openai_instrumentor = MagicMock()
        openai_instrumentor.is_instrumented_by_opentelemetry = False
        with patch(
            "openinference.instrumentation.crewai.CrewAIInstrumentor",
            return_value=crewai_instrumentor,
        ), patch(
            "openinference.instrumentation.openai.OpenAIInstrumentor",
            return_value=openai_instrumentor,
        ), patch("academic_agent.observability.tracing.find_spec", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "did not become active"):
                _instrument_provider(object())

    def test_real_default_instrumentors_are_actually_enabled(self) -> None:
        """A LiteLLM adapter once passed mocked tests but instrumented nothing.

        Exercise the installed CrewAI and OpenAI SDK adapters so a missing or
        incompatible target package makes this test fail at the integration
        seam rather than merely writing a dependency warning to stderr.
        """
        from openinference.instrumentation.crewai import CrewAIInstrumentor
        from openinference.instrumentation.openai import OpenAIInstrumentor

        provider = TracerProvider()
        with patch(
            "academic_agent.observability.tracing.find_spec", return_value=None
        ):
            _instrument_provider(provider)
        crewai_instrumentor = CrewAIInstrumentor()
        openai_instrumentor = OpenAIInstrumentor()
        try:
            self.assertTrue(crewai_instrumentor.is_instrumented_by_opentelemetry)
            self.assertTrue(openai_instrumentor.is_instrumented_by_opentelemetry)
        finally:
            crewai_instrumentor.uninstrument()
            openai_instrumentor.uninstrument()
            provider.shutdown()


class InMemoryTraceTests(unittest.TestCase):

    def setUp(self) -> None:
        self.exporter = InMemorySpanExporter()
        self.provider = TracerProvider()
        self.provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.addCleanup(self.provider.shutdown)

    def _start(self, run_id: str = "secret-capability-run-id") -> RunTelemetry:
        env = {
            "AGENT_OBSERVABILITY_ENABLED": "true",
            "PHOENIX_PROJECT_NAME": "test-project",
        }
        with patch.dict(os.environ, env, clear=True), patch(
            "academic_agent.observability.tracing._create_provider",
            return_value=self.provider,
        ), patch("academic_agent.observability.tracing._instrument_provider"):
            return start_run_telemetry(run_id, topic_length=41)

    def test_root_and_domain_spans_share_one_trace_without_raw_content(self) -> None:
        run_id = "secret-capability-run-id"
        telemetry = self._start(run_id)
        with telemetry.span(
            "source_collection", "RETRIEVER",
            {"academic_agent.source.paper_seeded": False},
        ):
            telemetry.set_attributes({"academic_agent.source.academic.count": 5})
        telemetry.finish()

        spans = self.exporter.get_finished_spans()
        self.assertEqual({span.name for span in spans}, {
            "commercialization_assessment", "source_collection",
        })
        self.assertEqual(len({span.context.trace_id for span in spans}), 1)
        root = next(
            span for span in spans if span.name == "commercialization_assessment"
        )
        self.assertEqual(root.attributes["academic_agent.topic.characters"], 41)
        self.assertEqual(root.attributes["academic_agent.source.academic.count"], 5)
        self.assertNotIn(run_id, str(root.attributes))
        self.assertNotIn("topic", str(root.attributes).lower().replace(
            "academic_agent.topic.characters", ""
        ))

        snapshot = telemetry.snapshot()
        self.assertEqual(snapshot["state"], "active")
        self.assertEqual(snapshot["delivery"], "attempted")
        self.assertRegex(snapshot["trace_id"] or "", r"^[0-9a-f]{32}$")

    def test_pipeline_exception_survives_tracing_unchanged(self) -> None:
        telemetry = self._start()
        with self.assertRaisesRegex(ValueError, "pipeline failure"):
            with telemetry.span("crew_execution", "CHAIN"):
                raise ValueError("pipeline failure")
        telemetry.finish(ValueError("pipeline failure"))

        root = next(
            span for span in self.exporter.get_finished_spans()
            if span.name == "commercialization_assessment"
        )
        child = next(
            span for span in self.exporter.get_finished_spans()
            if span.name == "crew_execution"
        )
        self.assertEqual(root.attributes["academic_agent.error.type"], "ValueError")
        self.assertNotIn("pipeline failure", str(root.attributes))
        self.assertEqual(child.attributes["academic_agent.error.type"], "ValueError")
        self.assertEqual(child.events, ())
        self.assertNotIn("pipeline failure", str(child.attributes))

    def test_flush_timeout_is_degraded_not_active(self) -> None:
        telemetry = self._start()
        self.provider.force_flush = MagicMock(return_value=False)  # type: ignore[method-assign]
        telemetry.finish()

        snapshot = telemetry.snapshot()
        self.assertEqual(snapshot["state"], "degraded")
        self.assertEqual(snapshot["delivery"], "timed_out")
        self.assertEqual(snapshot["error_type"], "FlushTimeout")

    def test_exporter_exception_is_type_only_and_does_not_escape(self) -> None:
        telemetry = self._start()
        self.provider.force_flush = MagicMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("collector rejected phoenix-api-key-secret")
        )
        telemetry.finish()

        snapshot = telemetry.snapshot()
        self.assertEqual(snapshot["state"], "degraded")
        self.assertEqual(snapshot["error_type"], "RuntimeError")
        self.assertNotIn("phoenix-api-key-secret", str(snapshot))

    def test_span_creation_failure_does_not_fail_the_operation(self) -> None:
        tracer = MagicMock()
        tracer.start_as_current_span.side_effect = RuntimeError("broken tracer")
        telemetry = RunTelemetry(
            {
                "state": "active",
                "backend": "phoenix",
                "trace_id": "0" * 32,
                "delivery": "pending",
                "content_capture": "redacted",
            },
            tracer=tracer,
        )

        operation_completed = False
        with telemetry.span("source_collection", "RETRIEVER") as span:
            self.assertIsNone(span)
            operation_completed = True

        self.assertTrue(operation_completed)
        self.assertEqual(telemetry.snapshot()["state"], "degraded")


if __name__ == "__main__":
    unittest.main()
