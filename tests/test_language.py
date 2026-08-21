"""Tests for language detection, translation fallback, and registry lookups."""
import json
import os
import warnings
from unittest.mock import patch

import pytest


from academic_agent.language import (
    LANGUAGE_REGISTRY,
    TopicSearchPlan,
    detect_language,
    get_lang_info,
    plan_topic_search,
    translate_headings,
    translate_to_english,
)


# ---------------------------------------------------------------------------
# detect_language
# ---------------------------------------------------------------------------

def test_detect_simplified_chinese():
    assert detect_language("柔性压电纳米发电机的可穿戴能量收集") == "zh-cn"


def test_detect_cjk_mixed_with_latin():
    # langdetect misdetects short CJK+Latin strings; Unicode block check must win
    assert detect_language("PEM电解槽") == "zh-cn"


def test_detect_japanese():
    assert detect_language("ペロブスカイト太陽電池の商業化") == "ja"


def test_detect_korean():
    assert detect_language("고체 리튬 배터리의 상업화") == "ko"


def test_detect_english():
    result = detect_language("perovskite solar cells for building-integrated photovoltaics")
    assert result == "en"


def test_detect_does_not_raise_on_empty_string():
    result = detect_language("")
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# get_lang_info
# ---------------------------------------------------------------------------

def test_get_lang_info_japanese():
    info = get_lang_info("ja")
    assert info["name"] == "Japanese"
    assert info["patent_cc"] == "JP"


def test_get_lang_info_zh_cn():
    assert get_lang_info("zh-cn")["name"] == "Simplified Chinese"


def test_get_lang_info_bare_zh_prefix():
    # "zh" without variant should resolve to Simplified Chinese
    assert get_lang_info("zh")["name"] == "Simplified Chinese"


def test_get_lang_info_unknown_falls_back_to_english():
    info = get_lang_info("xx-unknown")
    assert info["name"] == "English"


def test_registry_all_entries_have_required_keys():
    required = {"gl", "hl", "name", "patent_cc"}
    for code, entry in LANGUAGE_REGISTRY.items():
        missing = required - entry.keys()
        assert not missing, f"Registry entry '{code}' is missing keys: {missing}"


# ---------------------------------------------------------------------------
# translate_to_english — LLM failure graceful degradation
# ---------------------------------------------------------------------------

def test_translate_to_english_returns_original_on_llm_failure():
    original = "固态锂电池的干法电极制造工艺"
    with patch("academic_agent.language._llm_call", return_value=""):
        result = translate_to_english(original)
    assert result == original


def test_translate_to_english_returns_translation_on_success():
    expected = "Dry electrode manufacturing for solid-state lithium batteries"
    with patch("academic_agent.language._llm_call", return_value=expected):
        result = translate_to_english("固态锂电池的干法电极制造工艺")
    assert result == expected


# ---------------------------------------------------------------------------
# plan_topic_search — free-form input becomes a search-safe topic
# ---------------------------------------------------------------------------

def test_conversational_chinese_input_becomes_one_canonical_search_plan():
    """The production defect this covers.

    Literal translation preserved both "we are building" and "help me assess
    its value" in the academic query. Relevant papers existed, but the same
    request-shaped sentence was then used as the title-relevance filter and
    rejected the synonym results that retrieval had found.
    """
    raw = "我们在做剧本创作相关的大模型，帮我看看价值如何"
    response = (
        "SEARCH_TOPIC: large language models for screenplay creation\n"
        "ALIAS: LLM-assisted screenwriting\n"
        "ALIAS: generative AI for scriptwriting"
    )

    with patch("academic_agent.language._llm_call", return_value=response) as call:
        plan = plan_topic_search(raw)

    assert plan == TopicSearchPlan(
        search_topic="large language models for screenplay creation",
        aliases=("LLM-assisted screenwriting", "generative AI for scriptwriting"),
    )
    assert call.call_count == 1
    assert raw in call.call_args.args[0]

def test_compound_topic_keeps_independently_searchable_components():
    response = (
        "SEARCH_TOPIC: mycelium composites with embedded sensors and edge AI\n"
        "ALIAS: fungal biomaterials for intelligent structural monitoring\n"
        "COMPONENT: mycelium composite materials\n"
        "COMPONENT: embedded environmental sensors\n"
        "COMPONENT: edge AI anomaly detection"
    )
    with patch("academic_agent.language._llm_call", return_value=response):
        plan = plan_topic_search(
            "mycelium packaging with sensors and edge AI for cold-chain monitoring"
        )

    assert plan.components == (
        "mycelium composite materials",
        "embedded environmental sensors",
        "edge AI anomaly detection",
    )


def test_a_single_component_line_is_ignored_as_an_eager_alias():
    response = (
        "SEARCH_TOPIC: direct air capture sorbents\n"
        "ALIAS: carbon dioxide adsorption materials\n"
        "COMPONENT: porous sorbent materials"
    )
    with patch("academic_agent.language._llm_call", return_value=response):
        plan = plan_topic_search("direct air capture sorbents")

    assert plan.components == ()



def test_topic_plan_marks_an_input_without_an_identifiable_technology_unresolved():
    with patch(
        "academic_agent.language._llm_call",
        return_value="SEARCH_TOPIC: UNRESOLVED",
    ):
        plan = plan_topic_search("帮我看看这个值不值得做")

    assert not plan.resolved
    assert plan.search_topic == ""
    assert plan.aliases == ()


def test_topic_plan_falls_back_to_the_original_english_input_when_call_fails():
    raw = "solid-state batteries for electric vehicles"
    with patch("academic_agent.language._llm_call", return_value=""):
        plan = plan_topic_search(raw)

    assert plan == TopicSearchPlan(search_topic=raw, aliases=())


# ---------------------------------------------------------------------------
# translate_headings — LLM failure graceful degradation
# ---------------------------------------------------------------------------

def test_translate_headings_returns_originals_on_llm_failure():
    headings = ("## Executive Summary", "## Technology Readiness", "## Market Analysis")
    with patch("academic_agent.language._llm_call", return_value=""):
        result = translate_headings(headings, "Simplified Chinese")
    assert result == headings


def test_translate_headings_returns_originals_on_count_mismatch():
    # LLM returns fewer lines than expected — safety fallback must return originals
    headings = ("## Executive Summary", "## Market Analysis")
    with patch("academic_agent.language._llm_call", return_value="## 执行摘要"):
        result = translate_headings(headings, "Simplified Chinese")
    assert result == headings


def test_translate_headings_success():
    headings = ("## Executive Summary", "## Market Analysis")
    with patch("academic_agent.language._llm_call", return_value="## 执行摘要\n## 市场分析"):
        result = translate_headings(headings, "Simplified Chinese")
    assert result == ("## 执行摘要", "## 市场分析")


def test_translate_headings_preserves_tuple_type():
    headings = ("## Introduction",)
    with patch("academic_agent.language._llm_call", return_value="## 介绍"):
        result = translate_headings(headings, "Simplified Chinese")
    assert isinstance(result, tuple)


# ---------------------------------------------------------------------------
# Provider routing in _llm_call
# ---------------------------------------------------------------------------

# Only the provider variables are neutralised — clearing all of os.environ
# takes HOME with it, and the deferred llm_config import needs it.
_PROVIDER_ENV = dict.fromkeys((
    "LLM_PROVIDER",
    "DEEPSEEK_API_KEY", "DEEPSEEK_API_BASE", "DEEPSEEK_MODEL",
    "OPENAI_API_KEY", "OPENAI_API_BASE", "OPENAI_MODEL_NAME",
    "ANTHROPIC_API_KEY", "ANTHROPIC_API_BASE", "ANTHROPIC_MODEL",
), "")


def _only(**overrides):
    """Provider environment with exactly `overrides` set."""
    return {**_PROVIDER_ENV, **overrides}


class _Resp:
    """urlopen stub supporting 'with urlopen(...) as resp:'."""

    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


@pytest.mark.allow_llm
def test_anthropic_deployment_actually_translates():
    """The defect this covers.

    _llm_call read only DEEPSEEK_API_KEY / OPENAI_API_KEY and always spoke
    the OpenAI wire format, so an Anthropic-only deployment — a configuration
    llm_config explicitly supports — sent every request with an empty bearer
    token. The failure was swallowed by the fallback, so nothing broke
    visibly: non-English topics simply stopped being translated for search.
    """
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = {k.lower(): v for k, v in request.header_items()}
        captured["body"] = json.loads(request.data)
        return _Resp({"content": [{"type": "text", "text": "solid state batteries"}]})

    with patch.dict(os.environ, _only(ANTHROPIC_API_KEY="sk-ant-test")), \
         patch("academic_agent.language.urlopen", fake_urlopen):
        out = translate_to_english("固态电池")

    assert out == "solid state batteries"
    assert captured["url"].endswith("/v1/messages")
    assert captured["headers"]["x-api-key"] == "sk-ant-test"
    assert "anthropic-version" in captured["headers"]
    # system is a top-level field for Anthropic, not a message role
    assert "system" in captured["body"]
    assert [m["role"] for m in captured["body"]["messages"]] == ["user"]


@pytest.mark.allow_llm
def test_deepseek_deployment_keeps_the_openai_shape():
    """The path that already worked must not move."""
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = {k.lower(): v for k, v in request.header_items()}
        captured["body"] = json.loads(request.data)
        return _Resp({"choices": [{"message": {"content": "solid state batteries"}}]})

    with patch.dict(os.environ, _only(DEEPSEEK_API_KEY="sk-test")), \
         patch("academic_agent.language.urlopen", fake_urlopen):
        out = translate_to_english("固态电池")

    assert out == "solid state batteries"
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["authorization"] == "Bearer sk-test"
    assert [m["role"] for m in captured["body"]["messages"]] == ["system", "user"]


@pytest.mark.allow_llm
def test_an_unreachable_endpoint_still_degrades_to_the_original():
    """Callers rely on "" meaning "use the untranslated text"; adding a
    second provider must not turn a failed call into a crash mid-run."""
    with patch.dict(os.environ, _only(ANTHROPIC_API_KEY="k")), \
         patch("academic_agent.language.urlopen", side_effect=OSError("no network")), \
         warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert translate_to_english("固态电池") == "固态电池"
