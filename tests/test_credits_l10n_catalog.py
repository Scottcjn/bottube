# SPDX-License-Identifier: MIT
"""
Regression tests for the Credits & Pricing page localization catalog (issue #1796).

The /credits page body ("Credits & Pricing", "Video generation", "Buy RTC
credits", "Card top-ups", ...) was never wired into the translations catalog,
so ?lang=es localized only the nav while the page body stayed English.
These tests pin the credits.* key coverage across every shipped locale file.
"""

import json
from pathlib import Path

TRANSLATIONS_DIR = Path(__file__).resolve().parent.parent / "translations"

# Every locale file shipped in the repo (zh-CN ships even though
# SUPPORTED_LOCALES currently covers en/es/fr/ja/pt).
LOCALE_FILES = sorted(p.name for p in TRANSLATIONS_DIR.glob("*.json"))

REQUIRED_CREDITS_KEYS = {
    "credits.title",
    "credits.intro",
    "credits.reference_rate",
    "credits.login_hint",
    "credits.video_generation",
    "credits.image_generation",
    "credits.video_billed_note",
    "credits.image_note",
    "credits.buy_rtc",
    "credits.buy_pay_how",
    "credits.buy_crypto_rails",
    "credits.no_kyc",
    "credits.card_topup",
    "credits.crypto_topup_label",
    "credits.ergo_bridge",
    "credits.topup_from_studio",
    "credits.card_topups",
    "credits.crypto_topups",
    "credits.loading_packages",
    "credits.table_model",
    "credits.table_type",
    "credits.table_per_second",
    "credits.table_max_clip",
    "credits.table_five_sec",
    "credits.table_per_image",
}


def _load(locale_file: str) -> dict:
    data = json.loads((TRANSLATIONS_DIR / locale_file).read_text(encoding="utf-8"))
    assert isinstance(data.get("strings"), dict), f"{locale_file} missing strings object"
    return data


def test_credits_keys_present_in_every_locale():
    assert LOCALE_FILES, "no translation catalogs found"
    for locale_file in LOCALE_FILES:
        strings = _load(locale_file)["strings"]
        missing = REQUIRED_CREDITS_KEYS - strings.keys()
        assert not missing, f"{locale_file} missing credits keys: {sorted(missing)}"


def test_credits_keys_are_nonempty_strings():
    for locale_file in LOCALE_FILES:
        strings = _load(locale_file)["strings"]
        for key in REQUIRED_CREDITS_KEYS:
            value = strings.get(key)
            assert isinstance(value, str) and value.strip(), (
                f"{locale_file}:{key} is not a non-empty string"
            )


def test_credits_keys_localized_not_english_echo():
    """Non-English catalogs must not fall back to the English copy.

    Keys that are language-neutral by construction (pure currency tickers,
    model names) are exempt because identical values are correct there.
    """
    # credits.crypto_topup_label is pure currency tickers (language-neutral).
    # credits.table_type is "Type" in French too — a correct, identical word.
    language_neutral = {"credits.crypto_topup_label", "credits.table_type"}
    english = _load("en.json")["strings"]
    for locale_file in LOCALE_FILES:
        if locale_file == "en.json":
            continue
        strings = _load(locale_file)["strings"]
        identical = [
            key
            for key in REQUIRED_CREDITS_KEYS - language_neutral
            if strings[key] == english[key]
        ]
        assert not identical, (
            f"{locale_file} echoes English copy for: {identical}"
        )


def test_catalog_json_remains_valid_and_lang_matches_filename():
    for locale_file in LOCALE_FILES:
        data = _load(locale_file)
        expected_lang = Path(locale_file).stem
        assert data.get("lang") == expected_lang, (
            f"{locale_file} lang={data.get('lang')!r} does not match filename"
        )
