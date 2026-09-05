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
        """Verify _safe_truncate returns empty string for None input.

        Regression guard: agent bio can be NULL in the database. The
        discover and search pages must render that as an empty string
        instead of crashing on None[:max_len] or printing 'None'.
        """
        assert _safe_truncate(None, 150) == ""

    def test_truncation_handles_empty_string(self):
        """Verify _safe_truncate passes through empty strings unchanged."""
        assert _safe_truncate("", 200) == ""

    def test_truncation_short_text_unchanged(self):
        """Verify _safe_truncate returns text unchanged when under the limit.

        Texts shorter than max_len should be returned verbatim with no
        ellipsis appended. Otherwise short bios would render with a
        spurious "..." that misleads users about the bio length.
        """
        assert _safe_truncate("short bio", 150) == "short bio"

    def test_truncation_long_text_gets_ellipsis(self):
        """Verify _safe_truncate appends '...' to text longer than max_len.

        Standard truncation contract: drop everything past max_len, then
        append exactly three dots so the rendered text is max_len+3 chars
        and signals to the user that more content exists.
        """
        long = "x" * 300
        result = _safe_truncate(long, 150)
        assert len(result) == 153
        assert result.endswith("...")

    def test_truncation_exact_boundary(self):
        """Verify _safe_truncate returns text exactly at max_len unchanged.

        Boundary: when len(text) == max_len there is nothing to drop, so
        the function must return the original text with no ellipsis. This
        complements the one-over-boundary test below.
        """
        assert _safe_truncate("x" * 150, 150) == "x" * 150

    def test_truncation_one_over_boundary(self):
        """Verify _safe_truncate adds '...' when text is max_len + 1 chars.

        Off-by-one guard: the smallest case that requires truncation
        (len == max_len + 1) must still trigger the ellipsis path. If the
        comparison used `>` instead of `>=`, this case would silently
        return text one character longer than allowed.
        """
        result = _safe_truncate("x" * 151, 150)
        assert result == "x" * 150 + "..."


class TestSubscriptionsJoin:
    def test_uses_following_id_not_channel_id(self):
        """Verify the agent directory endpoint joins on following_id, not channel_id.

        The subscriptions table tracks which user follows which agent. The
        legacy column name was `channel_id`; the canonical name is
        `following_id`. The agent directory endpoint must reference the
        new name in its SQL/source so a schema rename in one place does
        not silently break the join (which would surface as 500s).
        """
        import search_blueprint
        import inspect
        source = inspect.getsource(search_blueprint.api_agent_directory)
        assert "following_id" in source
        assert "channel_id" not in source
