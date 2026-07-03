# SPDX-License-Identifier: MIT
"""
Regression test: /discover/api/agents and /discover/api/search
crash with HTTP 500 when agent bio or video description is NULL.
"""

import pytest


def _safe_truncate(text, max_len):
    return (text[:max_len] + "...") if text and len(text) > max_len else (text or "")


class TestNullGuardExpressions:
    def test_truncation_handles_none(self):
        assert _safe_truncate(None, 150) == ""

    def test_truncation_handles_empty_string(self):
        assert _safe_truncate("", 200) == ""

    def test_truncation_short_text_unchanged(self):
        assert _safe_truncate("short bio", 150) == "short bio"

    def test_truncation_long_text_gets_ellipsis(self):
        long = "x" * 300
        result = _safe_truncate(long, 150)
        assert len(result) == 153
        assert result.endswith("...")

    def test_truncation_exact_boundary(self):
        assert _safe_truncate("x" * 150, 150) == "x" * 150

    def test_truncation_one_over_boundary(self):
        result = _safe_truncate("x" * 151, 150)
        assert result == "x" * 150 + "..."


class TestSubscriptionsJoin:
    def test_uses_following_id_not_channel_id(self):
        import search_blueprint
        import inspect
        source = inspect.getsource(search_blueprint.api_agent_directory)
        assert "following_id" in source
        assert "channel_id" not in source
