"""Tests for i18n translation table completeness.

Each test verifies that every language in a translation dict has all the same
keys as the English baseline.  A new UI string added without translating it
into every language would otherwise surface as a KeyError at runtime.
"""

from __future__ import annotations

from unittest import TestCase

from ui.i18n import _SCORECARD_I18N, _UI_I18N, _WARNING_I18N


class ScorecardI18nCompletenessTests(TestCase):
    """_SCORECARD_I18N: score card strings shown on the results panel."""

    _ENGLISH_KEYS = frozenset(_SCORECARD_I18N["English"].keys())

    def test_all_languages_have_all_english_keys(self):
        for lang, d in _SCORECARD_I18N.items():
            if lang == "English":
                continue
            missing = self._ENGLISH_KEYS - frozenset(d.keys())
            with self.subTest(lang=lang):
                self.assertFalse(
                    missing,
                    f"_SCORECARD_I18N[{lang!r}] is missing keys: {sorted(missing)}",
                )

    def test_no_language_has_extra_keys_not_in_english(self):
        for lang, d in _SCORECARD_I18N.items():
            if lang == "English":
                continue
            extra = frozenset(d.keys()) - self._ENGLISH_KEYS
            with self.subTest(lang=lang):
                self.assertFalse(
                    extra,
                    f"_SCORECARD_I18N[{lang!r}] has unexpected extra keys: {sorted(extra)}",
                )


class UiI18nCompletenessTests(TestCase):
    """_UI_I18N: button labels, headers, progress text shown in the Gradio shell."""

    _ENGLISH_KEYS = frozenset(_UI_I18N["English"].keys())

    def test_all_languages_have_all_english_keys(self):
        for lang, d in _UI_I18N.items():
            if lang == "English":
                continue
            missing = self._ENGLISH_KEYS - frozenset(d.keys())
            with self.subTest(lang=lang):
                self.assertFalse(
                    missing,
                    f"_UI_I18N[{lang!r}] is missing keys: {sorted(missing)}",
                )

    def test_no_language_has_extra_keys_not_in_english(self):
        for lang, d in _UI_I18N.items():
            if lang == "English":
                continue
            extra = frozenset(d.keys()) - self._ENGLISH_KEYS
            with self.subTest(lang=lang):
                self.assertFalse(
                    extra,
                    f"_UI_I18N[{lang!r}] has unexpected extra keys: {sorted(extra)}",
                )


class WarningI18nCompletenessTests(TestCase):
    """_WARNING_I18N: source coverage warning messages."""

    _ENGLISH_KEYS = frozenset(_WARNING_I18N["English"].keys())

    def test_all_languages_have_all_english_keys(self):
        for lang, d in _WARNING_I18N.items():
            if lang == "English":
                continue
            missing = self._ENGLISH_KEYS - frozenset(d.keys())
            with self.subTest(lang=lang):
                self.assertFalse(
                    missing,
                    f"_WARNING_I18N[{lang!r}] is missing keys: {sorted(missing)}",
                )
