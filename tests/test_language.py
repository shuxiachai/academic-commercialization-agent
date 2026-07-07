"""Tests for language detection, translation fallback, and registry lookups."""
from unittest.mock import patch

import pytest

from academic_agent.language import (
    LANGUAGE_REGISTRY,
    detect_language,
    get_lang_info,
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
