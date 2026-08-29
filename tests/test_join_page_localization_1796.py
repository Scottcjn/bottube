# SPDX-License-Identifier: MIT
from pathlib import Path


def test_join_template_uses_translation_keys_for_user_facing_copy():
    template = Path("bottube_templates/join.html").read_text(encoding="utf-8")

    required_keys = [
        "join.title",
        "join.hero_title",
        "join.hero_subtitle",
        "join.humans_title",
        "join.tools_title",
        "join.ai_agents_title",
        "join.api_reference_title",
        "join.video_tools_title",
        "join.ffmpeg_title",
        "join.claude_skill_title",
    ]
    for key in required_keys:
        assert key in template, f"missing translation key in template: {key}"

    stale_english = [
        "Join BoTTube",
        "For Humans",
        "Install Our Tools",
        "For AI Agents",
        "API Reference",
        "Video Generation Tools",
        "FFmpeg Cookbook",
        "Claude Code Skill",
    ]
    for text in stale_english:
        assert text not in template, f"stale hard-coded English still present: {text}"


def test_all_supported_locales_have_join_strings():
    required_keys = [
        "join.title",
        "join.hero_title",
        "join.hero_subtitle",
        "join.humans_title",
        "join.humans_intro",
        "join.ai_agents_title",
        "join.api_reference_title",
        "join.video_tools_title",
        "join.ffmpeg_title",
        "join.claude_skill_title",
    ]

    for locale in ["en", "es", "fr", "ja", "pt"]:
        data = __import__("json").loads(Path(f"translations/{locale}.json").read_text(encoding="utf-8"))
        strings = data["strings"]
        missing = [key for key in required_keys if key not in strings]
        assert not missing, f"{locale} missing join translation keys: {missing}"
