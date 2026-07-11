"""Language detection, topic translation, and heading localisation.

Used by collect_source_collection() to support multilingual input:
  - detect the language of the user's topic string
  - translate non-English topics to English for academic/patent search
  - translate required report headings so the guardrail validates correctly
  - provide Serper gl/hl params for native-language market search
"""

import json
import os
from urllib.request import Request, urlopen

# Registry: langdetect code → Serper params + human-readable name + patent country code
LANGUAGE_REGISTRY: dict[str, dict] = {
    "en":    {"gl": "us", "hl": "en",    "name": "English",             "patent_cc": ""},
    "zh-cn": {"gl": "cn", "hl": "zh-cn", "name": "Simplified Chinese",  "patent_cc": "CN"},
    "zh-tw": {"gl": "tw", "hl": "zh-tw", "name": "Traditional Chinese", "patent_cc": "TW"},
    "ja":    {"gl": "jp", "hl": "ja",    "name": "Japanese",            "patent_cc": "JP"},
    "ko":    {"gl": "kr", "hl": "ko",    "name": "Korean",              "patent_cc": "KR"},
    "de":    {"gl": "de", "hl": "de",    "name": "German",              "patent_cc": "DE"},
    "fr":    {"gl": "fr", "hl": "fr",    "name": "French",              "patent_cc": "FR"},
    "es":    {"gl": "es", "hl": "es",    "name": "Spanish",             "patent_cc": "ES"},
    "it":    {"gl": "it", "hl": "it",    "name": "Italian",             "patent_cc": "IT"},
    "pt":    {"gl": "br", "hl": "pt",    "name": "Portuguese",          "patent_cc": ""},
    "ru":    {"gl": "ru", "hl": "ru",    "name": "Russian",             "patent_cc": "RU"},
    "ar":    {"gl": "sa", "hl": "ar",    "name": "Arabic",              "patent_cc": ""},
}


def _detect_cjk_script(text: str) -> str | None:
    """Detect East-Asian script from Unicode code-point ranges.

    langdetect confuses Chinese and Korean on short strings that contain Latin
    letters (e.g. "PEM电解槽" → mis-detected as 'ko').  Checking character
    blocks is unambiguous:
      • Hangul syllables / jamo  → Korean
      • Hiragana / Katakana      → Japanese  (may also contain CJK kanji)
      • CJK unified ideographs only → Simplified Chinese
    Returns a langdetect-compatible code or None when script is ambiguous.
    """
    has_hangul    = any('가' <= c <= '힯' or 'ᄀ' <= c <= 'ᇿ' for c in text)
    has_hiragana  = any('぀' <= c <= 'ゟ' for c in text)
    has_katakana  = any('゠' <= c <= 'ヿ' for c in text)
    has_cjk       = any('一' <= c <= '鿿' or '㐀' <= c <= '䶿' for c in text)

    if has_hangul:
        return "ko"
    if has_hiragana or has_katakana:
        return "ja"
    if has_cjk:
        return "zh-cn"
    return None


def detect_language(text: str) -> str:
    """Return a langdetect language code (e.g. 'zh-cn', 'ja', 'en').

    CJK scripts are identified by Unicode block first — langdetect is
    unreliable for short technical strings that mix CJK with Latin characters.
    For all non-CJK (Latin-script) text we always return 'en': langdetect
    regularly misidentifies English technical terms as Italian, Spanish, or
    French (e.g. "commercialization", "vaccine", "sodium") with high false
    confidence, making it unsafe for this use case.
    """
    script = _detect_cjk_script(text)
    if script is not None:
        return script
    return "en"


def get_lang_info(lang_code: str) -> dict:
    """Return the registry entry for a language code.

    Chinese variants ('zh-cn', 'zh-tw', 'zh') all map to 'zh-cn'.
    Unknown codes fall back to English.
    """
    if lang_code.startswith("zh"):
        return LANGUAGE_REGISTRY["zh-cn"]
    return LANGUAGE_REGISTRY.get(lang_code, LANGUAGE_REGISTRY["en"])


def _llm_call(prompt: str, *, system: str, max_tokens: int = 400) -> str:
    """Minimal one-shot LLM call using the same credentials as the main pipeline."""
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    base_url = (
        os.getenv("DEEPSEEK_API_BASE")
        or os.getenv("OPENAI_API_BASE")
        or "https://api.deepseek.com"
    ).rstrip("/")
    model = (
        os.getenv("DEEPSEEK_MODEL")
        or os.getenv("OPENAI_MODEL_NAME")
        or "deepseek-chat"
    )
    if model.startswith("deepseek/"):
        model = model.split("/", 1)[1]

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    req = Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        import warnings
        warnings.warn(f"language._llm_call failed ({type(exc).__name__}: {exc}); falling back to original text")
        return ""


def translate_to_english(text: str) -> str:
    """Translate an arbitrary-language string to English.

    Used to convert a native-language research topic into an English topic
    suitable for academic and patent search APIs.
    Falls back to the original text if the LLM call fails.
    """
    result = _llm_call(
        f"Translate the following text to English. "
        f"Return ONLY the translation, no explanation or extra text:\n\n{text}",
        system=(
            "You are a professional scientific translator. "
            "Output only the requested English translation."
        ),
        max_tokens=200,
    )
    return result if result else text


def translate_headings(
    headings: tuple[str, ...],
    target_language_name: str,
) -> tuple[str, ...]:
    """Translate a tuple of Markdown heading strings to the target language.

    Preserves the leading # / ## markers. Returns the originals unchanged
    if the translation result count does not match (safety fallback).
    """
    lines = "\n".join(headings)
    result = _llm_call(
        f"Translate these Markdown section headings to {target_language_name}. "
        f"Keep the leading # and ## markers exactly as they are. "
        f"Return ONLY the translated headings, one per line, in the same order. "
        f"No numbering, no explanation:\n\n{lines}",
        system=(
            "You are a professional translator specialising in technical documents. "
            "Output only the translated headings, preserving Markdown markers."
        ),
        max_tokens=400,
    )
    translated = [ln.strip() for ln in result.splitlines() if ln.strip()]
    if len(translated) != len(headings):
        return headings
    return tuple(translated)
