"""Tests for per-run token accounting and cost estimation.

The interesting assertions here are not "does it add up". They are the two
places where a wrong answer would look completely reasonable:

  * an unpriced model must yield no cost rather than $0.00, because a zero
    reads as "this run was free" and nobody re-checks a cheap-looking bill
  * cached prompt tokens are a subset of prompt_tokens on OpenAI-shaped
    providers and a disjoint counter on Anthropic, so the same numbers must
    price differently depending on which one reported them
"""

from __future__ import annotations

import os
from unittest import TestCase, mock

from academic_agent.token_usage import (
    PRICES_AS_OF,
    AgentUsage,
    RunUsage,
    collect_usage,
    cost_for,
    price_for,
)


class _Metrics:
    """Stand-in for crewai's UsageMetrics."""

    def __init__(self, prompt=0, cached=0, completion=0, created=0,
                 reasoning=0, total=None, requests=1):
        self.prompt_tokens = prompt
        self.cached_prompt_tokens = cached
        self.completion_tokens = completion
        self.cache_creation_tokens = created
        self.reasoning_tokens = reasoning
        self.total_tokens = total if total is not None else prompt + completion
        self.successful_requests = requests


class _LLM:
    def __init__(self, model, metrics):
        self.model = model
        self._metrics = metrics

    def get_token_usage_summary(self):
        return self._metrics


class _Agent:
    def __init__(self, role, llm):
        self.role = role
        self.llm = llm


class _Crew:
    def __init__(self, agents):
        self.agents = agents


def _clean_env():
    """LLM_PRICE_PER_MTOK unset — a developer machine that has it exported
    would otherwise silently replace the table these tests are checking."""
    return mock.patch.dict(os.environ, {"LLM_PRICE_PER_MTOK": ""})


class PricingLookupTests(TestCase):

    def test_known_model_is_priced(self):
        with _clean_env():
            price = price_for("deepseek-chat")
        self.assertIsNotNone(price)
        self.assertGreater(price.output, price.input)

    def test_provider_prefix_and_date_suffix_both_resolve(self):
        """Model ids arrive in three shapes depending on configuration, and
        all three name the same model."""
        with _clean_env():
            for model in ("deepseek/deepseek-chat", "deepseek-chat",
                          "claude-sonnet-4-20250514"):
                with self.subTest(model=model):
                    self.assertIsNotNone(price_for(model))

    def test_unknown_model_has_no_price(self):
        with _clean_env():
            self.assertIsNone(price_for("some-model-shipped-next-year"))

    def test_basis_names_the_table_and_its_date(self):
        """A cost with no stated basis cannot be judged for staleness, which
        is the failure mode a hardcoded price table actually has."""
        with _clean_env():
            self.assertIn(PRICES_AS_OF, price_for("deepseek-chat").basis)

    def test_deepseek_v4_flash_uses_conservative_peak_rates_and_own_date(self):
        """A later row must not falsely refresh every older provider price."""
        with _clean_env():
            price = price_for("deepseek-v4-flash")
        self.assertEqual(
            (price.input, price.cached, price.output),
            (0.44, 0.014, 1.32),
        )
        self.assertIn("peak", price.basis)
        self.assertIn("2026-08-30", price.basis)
        self.assertNotIn(PRICES_AS_OF, price.basis)

    def test_deepseek_v4_flash_cost_uses_openai_cache_shape(self):
        """Cached input is a subset of prompt input for DeepSeek's API."""
        with _clean_env():
            cost = cost_for(
                "deepseek-v4-flash",
                _Metrics(
                    prompt=1_000_000,
                    cached=250_000,
                    completion=100_000,
                ),
            )
        self.assertAlmostEqual(cost, 0.4655, places=6)

    def test_env_override_wins_over_the_table(self):
        with mock.patch.dict(os.environ, {"LLM_PRICE_PER_MTOK": "1.0:2.0"}):
            price = price_for("deepseek-chat")
        self.assertEqual((price.input, price.output), (1.0, 2.0))
        self.assertIn("env", price.basis)

    def test_env_override_prices_an_otherwise_unknown_model(self):
        """The override is the escape hatch for a model newer than the table,
        so it has to work for exactly the models the table does not know."""
        with mock.patch.dict(os.environ, {"LLM_PRICE_PER_MTOK": "1.0:2.0"}):
            self.assertIsNotNone(price_for("some-model-shipped-next-year"))

    def test_cache_rate_defaults_to_the_full_input_rate(self):
        """Not to zero: assuming cache reads are free understates the bill,
        and understating is the direction nobody audits."""
        with mock.patch.dict(os.environ, {"LLM_PRICE_PER_MTOK": "1.0:2.0"}):
            self.assertEqual(price_for("x").cached, 1.0)

    def test_malformed_override_is_ignored_rather_than_crashing(self):
        for raw in ("", "abc", "1.0", "1:2:3:4", "-1:2"):
            with self.subTest(raw=raw), mock.patch.dict(
                os.environ, {"LLM_PRICE_PER_MTOK": raw}
            ):
                price = price_for("deepseek-chat")
                self.assertIsNotNone(price, "should fall back to the table")
                self.assertNotIn("env", price.basis)


class CostArithmeticTests(TestCase):

    def test_unpriced_model_costs_none_not_zero(self):
        """The whole point. 0.00 is a number a reader will believe."""
        with _clean_env():
            cost = cost_for("some-model-shipped-next-year",
                            _Metrics(prompt=1_000_000, completion=1_000_000))
        self.assertIsNone(cost)

    def test_openai_shaped_cache_is_subtracted_from_prompt_tokens(self):
        """OpenAI reports cached tokens *inside* prompt_tokens, so charging
        the full prompt count and the cache count both would double-bill."""
        with mock.patch.dict(os.environ, {"LLM_PRICE_PER_MTOK": "10:0:1"}):
            # 1M prompt of which 400k cached; input $10/M, cache $1/M, output free.
            cost = cost_for("gpt-4o", _Metrics(prompt=1_000_000, cached=400_000))
        self.assertAlmostEqual(cost, 0.6 * 10 + 0.4 * 1, places=6)

    def test_anthropic_shaped_cache_is_not_subtracted(self):
        """Anthropic's input_tokens already excludes cache reads. Subtracting
        again would undercount the input and, with a big enough cache hit,
        drive the charged input negative."""
        with mock.patch.dict(os.environ, {"LLM_PRICE_PER_MTOK": "10:0:1"}):
            cost = cost_for("claude-sonnet-4",
                            _Metrics(prompt=1_000_000, cached=400_000))
        self.assertAlmostEqual(cost, 1.0 * 10 + 0.4 * 1, places=6)

    def test_the_two_conventions_actually_disagree(self):
        """Guards the distinction itself: if someone collapses the branches,
        every other test here still passes on identical numbers."""
        with mock.patch.dict(os.environ, {"LLM_PRICE_PER_MTOK": "10:0:1"}):
            metrics = _Metrics(prompt=1_000_000, cached=400_000)
            self.assertNotEqual(cost_for("gpt-4o", metrics),
                                cost_for("claude-sonnet-4", metrics))

    def test_cache_reads_never_drive_the_charged_input_negative(self):
        """A provider reporting cached >= prompt must not produce a credit."""
        with mock.patch.dict(os.environ, {"LLM_PRICE_PER_MTOK": "10:0:0"}):
            cost = cost_for("gpt-4o", _Metrics(prompt=1000, cached=5000))
        self.assertGreaterEqual(cost, 0.0)

    def test_cache_writes_cost_more_than_plain_input(self):
        with mock.patch.dict(os.environ, {"LLM_PRICE_PER_MTOK": "10:0:1"}):
            written = cost_for("claude-sonnet-4", _Metrics(created=1_000_000))
            plain = cost_for("claude-sonnet-4", _Metrics(prompt=1_000_000))
        self.assertGreater(written, plain)

    def test_reasoning_tokens_are_not_charged_a_second_time(self):
        """They are already inside completion_tokens; adding them again would
        double the most expensive category on reasoning models."""
        with mock.patch.dict(os.environ, {"LLM_PRICE_PER_MTOK": "0:10"}):
            with_reasoning = cost_for("gpt-4o", _Metrics(completion=1000, reasoning=800))
            without = cost_for("gpt-4o", _Metrics(completion=1000))
        self.assertEqual(with_reasoning, without)

    def test_provider_is_detected_from_the_llm_object_when_model_is_opaque(self):
        """A deployment naming its model "default" behind an Anthropic proxy
        still has to be billed on Anthropic's convention."""
        class _Anthropicish:
            pass
        _Anthropicish.__module__ = "crewai.llms.providers.anthropic.completion"

        with mock.patch.dict(os.environ, {"LLM_PRICE_PER_MTOK": "10:0:1"}):
            cost = cost_for("default", _Metrics(prompt=1_000_000, cached=400_000),
                            llm=_Anthropicish())
        self.assertAlmostEqual(cost, 1.0 * 10 + 0.4 * 1, places=6)


class CollectionTests(TestCase):

    def _crew(self, *specs):
        return _Crew([_Agent(role, _LLM(model, metrics))
                      for role, model, metrics in specs])

    def test_agent_roles_are_stripped(self):
        """Roles come from a YAML block scalar and arrive with a trailing
        newline. Left in, it lands inside a JSON string in status.json and
        breaks any table that aligns these in a column — which is what the
        first real run's output looked like."""
        with _clean_env():
            usage = collect_usage(self._crew(
                ("Scientific Report Quality Reviewer\n", "deepseek-chat",
                 _Metrics(prompt=10, completion=1)),
            ))
        self.assertEqual(usage.agents[0].role, "Scientific Report Quality Reviewer")

    def test_per_agent_attribution(self):
        """The point of collecting per agent rather than reading the crew
        total: 'which agent is expensive' is the question worth answering."""
        with _clean_env():
            usage = collect_usage(self._crew(
                ("Academic", "deepseek-chat", _Metrics(prompt=1000, completion=100)),
                ("Patent", "deepseek-chat", _Metrics(prompt=5000, completion=900)),
            ))
        self.assertEqual([a.role for a in usage.agents], ["Academic", "Patent"])
        self.assertGreater(usage.agents[1].cost_usd, usage.agents[0].cost_usd)
        self.assertEqual(usage.total_tokens, 1100 + 5900)
        self.assertEqual(usage.total_requests, 2)

    def test_one_unpriced_agent_marks_the_whole_total_incomplete(self):
        """A partial sum presented as the total understates the bill by an
        unknown amount, which is worse than reporting no total at all."""
        with _clean_env():
            usage = collect_usage(self._crew(
                ("Academic", "deepseek-chat", _Metrics(prompt=1000, completion=100)),
                ("Patent", "model-from-the-future", _Metrics(prompt=9_000_000, completion=9_000_000)),
            ))
        self.assertFalse(usage.cost_complete)
        self.assertIn("model-from-the-future", usage.unpriced_models)
        # Tokens are measured, so they stay exact even when cost cannot.
        self.assertEqual(usage.total_tokens, 1100 + 18_000_000)

    def test_all_priced_reports_a_complete_total(self):
        with _clean_env():
            usage = collect_usage(self._crew(
                ("Academic", "deepseek-chat", _Metrics(prompt=1000, completion=100)),
            ))
        self.assertTrue(usage.cost_complete)
        self.assertEqual(usage.unpriced_models, ())

    def test_agent_whose_llm_cannot_report_usage_is_skipped_not_fatal(self):
        """`agents` is a duck-typed seam. An llm without the method should
        drop out of the accounting rather than abort a finished run."""
        crew = self._crew(("Academic", "deepseek-chat", _Metrics(prompt=1000)))
        crew.agents.append(_Agent("Legacy", object()))
        with _clean_env():
            usage = collect_usage(crew)
        self.assertEqual(len(usage.agents), 1)
        self.assertIsNone(usage.collection_error)

    def test_collection_never_raises(self):
        """Called on the failure path, where an exception would replace a real
        diagnosis with an accounting bug."""
        class _Exploding:
            @property
            def agents(self):
                raise RuntimeError("boom")

        usage = collect_usage(_Exploding())
        self.assertIn("boom", usage.collection_error)
        self.assertEqual(usage.agents, ())

    def test_no_crew_yields_an_empty_report_rather_than_an_error(self):
        usage = collect_usage(None)
        self.assertEqual(usage.agents, ())
        self.assertIsNone(usage.collection_error)


class SerialisationTests(TestCase):

    def test_payload_carries_the_basis_alongside_the_number(self):
        """status.json is what the client renders, so the caveats have to
        survive the trip — a cost without its basis is unjudgeable."""
        with _clean_env():
            data = collect_usage(_Crew([
                _Agent("Academic", _LLM("deepseek-chat", _Metrics(prompt=1000, completion=10)))
            ])).as_dict()
        self.assertIn(PRICES_AS_OF, data["price_basis"])
        self.assertTrue(data["cost_complete"])
        self.assertEqual(len(data["agents"]), 1)

    def test_payload_is_json_serialisable(self):
        """It is written straight into status.json; a stray dataclass or tuple
        would fail there, mid-run, long after this code ran."""
        import json

        with _clean_env():
            data = collect_usage(_Crew([
                _Agent("Academic", _LLM("deepseek-chat",
                                        _Metrics(prompt=1000, cached=200, completion=10)))
            ])).as_dict()
        self.assertIsInstance(json.dumps(data), str)

    def test_zero_valued_cache_fields_are_omitted(self):
        with _clean_env():
            data = AgentUsage(role="r", model="deepseek-chat").as_dict()
        self.assertNotIn("cached_prompt_tokens", data)
        self.assertNotIn("reasoning_tokens", data)

    def test_unpriced_models_are_named_in_the_payload(self):
        with _clean_env():
            data = collect_usage(_Crew([
                _Agent("Academic", _LLM("model-from-the-future", _Metrics(prompt=1)))
            ])).as_dict()
        self.assertFalse(data["cost_complete"])
        self.assertIn("model-from-the-future", data["unpriced_models"])

    def test_empty_run_usage_serialises(self):
        self.assertEqual(RunUsage().as_dict()["total_tokens"], 0)


class KimiK3PricingTests(TestCase):

    def test_kimi_k3_uses_the_provider_rates_and_own_basis_date(self):
        with _clean_env():
            price = price_for("kimi-k3")
        self.assertEqual(
            (price.input, price.cached, price.output),
            (3.00, 0.30, 15.00),
        )
        self.assertIn("Kimi K3", price.basis)
        self.assertIn("2026-08-30", price.basis)
        self.assertNotIn(PRICES_AS_OF, price.basis)

    def test_kimi_cache_is_a_subset_of_prompt_input(self):
        """Kimi reports cached_tokens at usage top level, but billing follows
        the OpenAI-shaped subset convention after llm_config translates it."""

        with _clean_env():
            cost = cost_for(
                "kimi-k3",
                _Metrics(
                    prompt=1_000_000,
                    cached=250_000,
                    completion=100_000,
                ),
            )
        self.assertAlmostEqual(cost, 3.825, places=6)
