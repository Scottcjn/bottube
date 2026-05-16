"""
Unit tests for translations.py — BoTTube video translation module.

Covers:
  - get_all_translations(): returns full data structure
  - get_video_translations(): lookup by URL, missing URL edge case
  - get_translations_by_language(): filter by language, unsupported language
  - get_supported_languages(): returns expected language list
  - Edge cases: empty string URL, None-like inputs, case sensitivity
"""

import pytest
from translations import (
    get_all_translations,
    get_video_translations,
    get_translations_by_language,
    get_supported_languages,
    TRANSLATION_DATA,
)


class TestGetAllTranslations:
    """Tests for get_all_translations()."""

    def test_returns_dict_with_videos_key(self):
        result = get_all_translations()
        assert isinstance(result, dict)
        assert "videos" in result
        assert "metadata" in result

    def test_videos_is_non_empty_list(self):
        result = get_all_translations()
        assert isinstance(result["videos"], list)
        assert len(result["videos"]) > 0

    def test_each_video_has_required_keys(self):
        result = get_all_translations()
        for video in result["videos"]:
            assert "video_url" in video, f"Missing video_url in {video}"
            assert "original_title" in video
            assert "original_description" in video
            assert "translations" in video
            assert isinstance(video["translations"], dict)

    def test_metadata_has_languages(self):
        result = get_all_translations()
        meta = result["metadata"]
        assert "languages" in meta
        assert isinstance(meta["languages"], list)
        assert len(meta["languages"]) >= 5


class TestGetVideoTranslations:
    """Tests for get_video_translations(url)."""

    def test_existing_url_returns_video(self):
        url = "https://bottube.ai/watch/tech-revolution-2024"
        result = get_video_translations(url)
        assert result is not None
        assert result["video_url"] == url
        assert "translations" in result

    def test_nonexistent_url_returns_none(self):
        result = get_video_translations("https://bottube.ai/watch/nonexistent-video")
        assert result is None

    def test_empty_string_url_returns_none(self):
        result = get_video_translations("")
        assert result is None

    def test_url_is_case_sensitive(self):
        """URLs should match exactly — uppercase should not match."""
        url = "https://bottube.ai/watch/tech-revolution-2024"
        result_exact = get_video_translations(url)
        result_upper = get_video_translations(url.upper())
        assert result_exact is not None
        assert result_upper is None

    def test_returned_video_has_translations_for_all_languages(self):
        url = "https://bottube.ai/watch/crypto-trading-guide"
        result = get_video_translations(url)
        assert result is not None
        supported = get_supported_languages()
        for lang in supported:
            assert lang in result["translations"], f"Missing translation for {lang}"
            assert "title" in result["translations"][lang]
            assert "description" in result["translations"][lang]


class TestGetTranslationsByLanguage:
    """Tests for get_translations_by_language(language)."""

    def test_chinese_returns_all_videos(self):
        result = get_translations_by_language("chinese")
        assert isinstance(result, list)
        assert len(result) == len(TRANSLATION_DATA["videos"])

    def test_spanish_returns_correct_structure(self):
        result = get_translations_by_language("spanish")
        for entry in result:
            assert "video_url" in entry
            assert "original_title" in entry
            assert "original_description" in entry
            assert "translation" in entry
            assert "title" in entry["translation"]
            assert "description" in entry["translation"]

    def test_unsupported_language_returns_empty_list(self):
        result = get_translations_by_language("klingon")
        assert result == []

    def test_empty_string_language_returns_empty_list(self):
        result = get_translations_by_language("")
        assert result == []

    def test_language_key_is_case_sensitive(self):
        """Language keys are lowercase; uppercase should return empty."""
        result_lower = get_translations_by_language("french")
        result_upper = get_translations_by_language("French")
        assert len(result_lower) > 0
        assert result_upper == []


class TestGetSupportedLanguages:
    """Tests for get_supported_languages()."""

    def test_returns_list(self):
        result = get_supported_languages()
        assert isinstance(result, list)

    def test_contains_expected_languages(self):
        result = get_supported_languages()
        expected = ["chinese", "spanish", "french", "portuguese", "german"]
        for lang in expected:
            assert lang in result, f"Missing language: {lang}"

    def test_no_empty_strings_in_languages(self):
        result = get_supported_languages()
        for lang in result:
            assert lang.strip() != "", "Empty string found in supported languages"

    def test_languages_are_lowercase(self):
        result = get_supported_languages()
        for lang in result:
            assert lang == lang.lower(), f"Language not lowercase: {lang}"
