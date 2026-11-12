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


class Qwen35PlusPricingTests(TestCase):

    def test_qwen_uses_conservative_peak_rates_and_its_own_basis_date(self):
        with _clean_env():
            price = price_for("qwen3.5-plus")
        self.assertEqual(
            (price.input, price.cached, price.output),
            (0.573, 0.115, 3.44),
        )
        self.assertIn("Qwen3.5 Plus", price.basis)
        self.assertIn("2026-08-30", price.basis)
        self.assertNotIn(PRICES_AS_OF, price.basis)

    def test_newer_qwen_models_are_priced_as_upper_bounds_with_their_own_date(self):
        """Production moved to these models; unpriced, every run reported
        "at least $X; unpriced: qwen3.x" and the soft stop could not apply."""
        with _clean_env():
            plus, max_ = price_for("qwen3.7-plus"), price_for("qwen3.8-max")
            dated = price_for("qwen3.8-max-0902")
        self.assertEqual((plus.input, plus.cached, plus.output), (0.85, 0.85, 3.40))
        self.assertEqual((max_.input, max_.cached, max_.output), (2.00, 2.00, 6.00))
        self.assertEqual((dated.input, dated.output), (2.00, 6.00))
        for price in (plus, max_):
            self.assertIn("upper bound", price.basis)
            self.assertIn("2026-10-18", price.basis)
            self.assertNotIn(PRICES_AS_OF, price.basis)
            # Unknown cache pricing is charged at the full input rate.
            self.assertEqual(price.cached, price.input)

    def test_qwen38_27b_is_priced_at_the_higher_official_or_listed_rate(self):
        """Production moved to qwen3.8-27b on 2026-10-19; unpriced, every run
        would read "at least $X; unpriced" and the soft stop could not apply."""
        with _clean_env():
            small = price_for("qwen3.8-27b")
        self.assertEqual((small.input, small.cached, small.output), (0.52, 0.52, 3.20))
        self.assertIn("upper bound", small.basis)
        self.assertIn("2026-10-19", small.basis)
        self.assertNotIn(PRICES_AS_OF, small.basis)

    def test_free_quota_catalogue_rows_price_the_rotating_deployment(self):
        """The public deployment switched to qwen3.7-max-preview on 2026-10-23
        with no row to match; the run page would have read "unpriced" and the
        soft stop could not apply. The preview and dated snapshots must find
        the base row by prefix, and the flash tiers must carry their own date."""
        with _clean_env():
            preview = price_for("qwen3.7-max-preview")
            snapshot = price_for("qwen3.7-max-2026-06-08")
            flash37, flash38 = price_for("qwen3.7-flash"), price_for("qwen3.8-flash")
        self.assertEqual((preview.input, preview.cached, preview.output), (2.64, 0.53, 7.92))
        self.assertEqual((snapshot.input, snapshot.output), (2.64, 7.92))
        self.assertEqual((flash37.input, flash37.cached, flash37.output), (0.17, 0.17, 0.68))
        self.assertEqual((flash38.input, flash38.cached, flash38.output), (0.12, 0.12, 0.38))
        for price in (preview, flash37, flash38):
            self.assertIn("upper bound", price.basis)
            self.assertIn("2026-10-23", price.basis)
            self.assertNotIn(PRICES_AS_OF, price.basis)
        # The Max row names a region so a reader can re-check it; the preview
        # is listed only in Beijing, so an overstated basis is the honest one.
        self.assertIn("Singapore", preview.basis)

    def test_qwen_cached_tokens_are_a_subset_of_prompt_input(self):
        """DashScope follows the OpenAI nested cached-token convention.

        Full-rate input therefore excludes the cached subset rather than
        double-billing it. The table uses the peak published context tier so
        a budget stop remains conservative for shorter requests too.
        """

        with _clean_env():
            cost = cost_for(
                "qwen3.5-plus",
                _Metrics(
                    prompt=1_000_000,
                    cached=250_000,
                    completion=100_000,
                ),
            )
        self.assertAlmostEqual(cost, 0.8025, places=6)


class _AnthropicLLM(_LLM):
    """An LLM whose class lives where CrewAI's Anthropic provider does."""


_AnthropicLLM.__module__ = "crewai.llms.providers.anthropic.completion"

# The six nodes of the first run through Anthropic (2026-11-12, claude-sonnet-5-5,
# held-out topic V01), as CrewAI reported them: (role, input, output, cache writes).
# CrewAI turns prompt caching on for Anthropic, so the prompt arrives as a cache
# write and "input" is the four tokens after the cache breakpoint.
_FIRST_ANTHROPIC_RUN = (
    ("Academic Literature Analyst", 4, 3_143, 6_069),
    ("Patent Landscape Analyst", 4, 2_814, 6_037),
    ("Market and Competitive Intelligence Analyst", 4, 5_598, 5_787),
    ("Technology Commercialization Report Writer", 4, 12_503, 28_692),
    ("Scientific Report Quality Reviewer", 4, 2_512, 41_301),
    ("Commercialization Readiness Scorer", 4, 4_107, 37_067),
)


class AnthropicTotalsTests(TestCase):
    """A run's token total counts every token the provider processed.

    The first run through Anthropic was recorded as 30,701 tokens. The
    provider processed 155,654: CrewAI's total_tokens is input plus output,
    and on Anthropic "input" leaves out what was written to or read from the
    prompt cache, which there was the whole prompt. The page showed a visitor
    paying with their own key a fifth of what they were billed for. The cost
    formula already knew the convention; the total did not."""

    def _run(self):
        return _Crew([
            _Agent(role, _LLM("claude-sonnet-5-5", _Metrics(prompt=prompt, completion=out, created=written)))
            for role, prompt, out, written in _FIRST_ANTHROPIC_RUN
        ])

    def test_the_first_anthropic_run_adds_up_to_what_was_processed(self):
        with _clean_env():
            usage = collect_usage(self._run())
        self.assertEqual(usage.total_tokens, 155_654)
        writer = usage.agents[3]
        self.assertEqual(writer.total_tokens, 4 + 12_503 + 28_692)
        # What the provider reported stays as reported, beside the total.
        self.assertEqual((writer.prompt_tokens, writer.completion_tokens, writer.cache_creation_tokens),
                         (4, 12_503, 28_692))
        self.assertEqual(usage.total_requests, 6)

    def test_cache_reads_count_too(self):
        """A second call of a node reads the prompt back from the cache."""
        with _clean_env():
            usage = collect_usage(_Crew([_Agent("Writer", _LLM(
                "claude-sonnet-5-5", _Metrics(prompt=40, cached=28_692, completion=9_000, created=600, requests=2)))]))
        self.assertEqual(usage.total_tokens, 40 + 28_692 + 9_000 + 600)

    def test_an_anthropic_model_behind_another_name_is_counted_the_same_way(self):
        with _clean_env():
            usage = collect_usage(_Crew([_Agent("Writer", _AnthropicLLM(
                "default", _Metrics(prompt=4, completion=100, created=5_000)))]))
        self.assertEqual(usage.total_tokens, 5_104)

    def test_the_other_providers_total_is_the_one_they_report(self):
        """There cached tokens are already inside prompt_tokens: adding them would count them twice."""
        with _clean_env():
            usage = collect_usage(_Crew([
                _Agent("Writer", _LLM("deepseek-chat", _Metrics(prompt=1_000, cached=400, completion=100))),
                _Agent("Scorer", _LLM("qwen3.8-max", _Metrics(prompt=2_000, cached=2_000, completion=50, total=2_060))),
            ]))
        self.assertEqual([a.total_tokens for a in usage.agents], [1_100, 2_060])
        self.assertEqual(usage.total_tokens, 3_160)

    def test_the_first_anthropic_run_is_priced_and_the_price_is_complete(self):
        """$2 input, 1.25x that for a cache write, $10 output per million (2026-11-12)."""
        with _clean_env():
            usage = collect_usage(self._run())
        expected = (24 * 2.00 + 124_953 * 2.00 * 1.25 + 30_677 * 10.00) / 1_000_000
        self.assertAlmostEqual(usage.cost_usd, expected, places=5)
        self.assertAlmostEqual(usage.cost_usd, 0.6192, places=3)
        self.assertTrue(usage.cost_complete)
        self.assertEqual(usage.unpriced_models, ())
        self.assertIn("2026-11-12", usage.price_basis)


class AnthropicPriceTableTests(TestCase):
    """Anthropic's published prices on 2026-11-12, USD per million tokens.

    Before that date the table knew three Claude rows from 2026-05. None of the
    models the key form suggests was priced, a current Opus was priced at three
    times its rate through the "claude-opus-4" prefix, and Haiku 4.5 below its
    rate through "claude-haiku-4"."""

    # model id -> (input, cache read, output), from platform.claude.com/docs/en/about-claude/pricing
    PUBLISHED = {
        "claude-fable-5-2": (8.00, 0.20, 40.00), "claude-mythos-5-2": (8.00, 0.20, 40.00),
        "claude-fable-5-1": (10.00, 0.25, 50.00), "claude-mythos-5-1": (10.00, 0.25, 50.00),
        "claude-fable-5": (10.00, 1.00, 50.00), "claude-mythos-5": (10.00, 1.00, 50.00),
        "claude-opus-5-5": (4.00, 0.20, 20.00), "claude-opus-5": (5.00, 0.50, 25.00),
        "claude-opus-4-8": (5.00, 0.50, 25.00), "claude-opus-4-7": (5.00, 0.50, 25.00),
        "claude-opus-4-6": (5.00, 0.50, 25.00), "claude-opus-4-5": (5.00, 0.50, 25.00),
        "claude-opus-4-1": (15.00, 1.50, 75.00), "claude-opus-4": (15.00, 1.50, 75.00),
        "claude-sonnet-5-5": (2.00, 0.10, 10.00), "claude-sonnet-5": (2.00, 0.20, 10.00),
        "claude-sonnet-4-6": (3.00, 0.30, 15.00), "claude-sonnet-4-5": (3.00, 0.30, 15.00),
        "claude-sonnet-4": (3.00, 0.30, 15.00), "claude-haiku-4-5": (1.00, 0.10, 5.00),
    }

    def test_each_current_model_is_priced_as_published(self):
        with _clean_env():
            for model, rates in self.PUBLISHED.items():
                with self.subTest(model=model):
                    price = price_for(model)
                    self.assertEqual((price.input, price.cached, price.output), rates)
                    self.assertIn("2026-11-12", price.basis)
                    self.assertNotIn(PRICES_AS_OF, price.basis)

    def test_a_dated_snapshot_takes_its_own_models_row_not_a_shorter_names(self):
        with _clean_env():
            for model, rates in (
                ("claude-haiku-4-5-20251001", (1.00, 0.10, 5.00)),
                ("claude-opus-4-1-20250805", (15.00, 1.50, 75.00)),
                ("claude-opus-4-5-20251101", (5.00, 0.50, 25.00)),
                ("claude-sonnet-4-5-20250929", (3.00, 0.30, 15.00)),
                ("anthropic/claude-sonnet-5-5", (2.00, 0.10, 10.00)),
            ):
                with self.subTest(model=model):
                    price = price_for(model)
                    self.assertEqual((price.input, price.cached, price.output), rates)

    def test_haiku_5_5_is_priced_at_its_long_prompt_tier_and_says_so(self):
        """$0.10 / $0.50 up to 100,000 prompt tokens and $0.50 / $2.50 over. A
        node's usage is a sum over its requests and does not say how long each
        prompt was, so the row is the higher tier, as for the tiered Qwen rows:
        the figure can overstate and cannot understate."""
        with _clean_env():
            price = price_for("claude-haiku-5-5")
        self.assertEqual((price.input, price.cached, price.output), (0.50, 0.05, 2.50))
        self.assertIn("upper", price.basis)
        self.assertIn("2026-11-12", price.basis)

    def test_no_claude_model_falls_to_a_row_that_was_never_its_price(self):
        """A name the table does not know is unpriced, not priced as a namesake."""
        with _clean_env():
            for model in ("claude-haiku-4", "claude-haiku-3-5", "claude-sonnet-6", "claude-opus-6-1"):
                with self.subTest(model=model):
                    self.assertIsNone(price_for(model))
