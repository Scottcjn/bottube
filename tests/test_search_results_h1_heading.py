"""Regression tests for Bottube search results h1 heading (Bottube #1387).

The /search?q=... results page must expose a page-level <h1> inside
<main> so that screen-reader and keyboard users navigating by headings
can identify the page purpose (WCAG 1.3.1 / 2.4.6 / 4.1.2).

Before this fix, the results heading was <h2 class="section-title">
and the page had no <h1>, creating a heading-hierarchy gap and
making the search page inconsistent with every other top-level
Bottube template (index.html, channel.html, activity_feed.html,
etc., all of which start with <h1>).
"""

import re
import unittest
from pathlib import Path


TEMPLATE_DIR = Path(__file__).parent.parent / "bottube_templates"


class TestSearchResultsH1Heading(unittest.TestCase):
    TEMPLATE = TEMPLATE_DIR / "search.html"

    def _read(self):
        with open(self.TEMPLATE, "r", encoding="utf-8") as f:
            return f.read()

    def test_page_uses_h1_for_results_heading(self):
        """The search results heading must be an <h1>, not <h2>."""
        content = self._read()
        match = re.search(
            r'<(h1|h2)\b[^>]*id="search-results-heading"[^>]*>',
            content,
        )
        self.assertIsNotNone(
            match,
            "Expected an <h1>/<h2> with id='search-results-heading' in search.html",
        )
        self.assertEqual(
            match.group(1),
            "h1",
            (
                "search-results-heading must be an <h1> (not <h2>) so the "
                "search results page exposes a page-level heading for "
                "WCAG 1.3.1 / 2.4.6 compliance. Found: <%s>" % match.group(1)
            ),
        )

    def test_h1_carries_section_title_class(self):
        """The h1 must keep the .section-title class so the visual style is unchanged."""
        content = self._read()
        match = re.search(
            r'<h1\b[^>]*id="search-results-heading"[^>]*>',
            content,
        )
        self.assertIsNotNone(match, "search-results-heading h1 not found")
        tag = match.group(0)
        self.assertIn(
            "section-title",
            tag,
            "search-results-heading <h1> must keep the .section-title class "
            "to preserve the existing visual style (only the tag changed).",
        )

    def test_no_lingering_h2_for_results(self):
        """There must be no <h2 id='search-results-heading'> left over."""
        content = self._read()
        self.assertNotIn(
            '<h2 class="section-title" id="search-results-heading"',
            content,
            "Lingering <h2 id='search-results-heading'> still present; the fix "
            "must replace the h2 tag with h1, not duplicate it.",
        )

    def test_query_text_preserved(self):
        """The query placeholder must still render in the heading text."""
        content = self._read()
        match = re.search(
            r'<h1\b[^>]*id="search-results-heading"[^>]*>(.*?)</h1>',
            content,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "search-results-heading <h1> not found")
        inner = match.group(1)
        self.assertIn(
            "{{ query }}",
            inner,
            "Heading text must still render the search query; do not remove "
            "the {{ query }} placeholder.",
        )

    def test_results_count_preserved(self):
        """The {{ total }} videos count must remain next to the heading."""
        content = self._read()
        self.assertIn(
            '{{ total }} videos',
            content,
            "Results count 'total videos' span was removed; the fix should "
            "only change the heading tag, not remove the count.",
        )


if __name__ == "__main__":
    unittest.main()
