# SPDX-License-Identifier: MIT
import re
from pathlib import Path


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "bottube_templates"
    / "activity_feed.html"
)


def _load_feed_body() -> str:
    source = TEMPLATE.read_text(encoding="utf-8")
    match = re.search(
        r"async function loadFeed\([^)]*\)\s*\{(?P<body>.*?)\n    \}",
        source,
        re.DOTALL,
    )
    assert match, "activity feed must define loadFeed"
    return match.group("body")


def test_load_feed_does_not_depend_on_implicit_browser_event():
    body = _load_feed_body()

    assert not re.search(r"(?<![\w.])event\s*\.", body), (
        "loadFeed is invoked by DOMContentLoaded and setInterval without an "
        "event; reading the implicit browser event aborts before fetch"
    )


def test_feed_tabs_expose_filter_state_for_programmatic_activation():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert source.count('<button class="feed-tab') == 4
    for filter_name in ("all", "uploads", "comments", "tips"):
        assert f'data-filter="{filter_name}"' in source
    assert "setActiveFeedTab(filter)" in _load_feed_body()
