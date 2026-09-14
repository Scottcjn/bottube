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


def _load_set_active_tab_body() -> str:
    source = TEMPLATE.read_text(encoding="utf-8")
    match = re.search(
        r"function setActiveFeedTab\([^)]*\)\s*\{(?P<body>.*?)\n    \}",
        source,
        re.DOTALL,
    )
    assert match, "activity feed must define setActiveFeedTab"
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


def test_feed_tabs_expose_and_sync_accessible_selected_state():
    source = TEMPLATE.read_text(encoding="utf-8")
    set_active_body = _load_set_active_tab_body()

    assert '<div class="feed-tabs" role="tablist" aria-label="Activity filters">' in source
    assert source.count('role="tab"') == 4
    assert source.count('aria-controls="activityList"') == 4
    assert source.count('aria-selected="true"') == 1
    assert source.count('aria-selected="false"') == 3
    assert 'id="activityList" role="tabpanel" aria-labelledby="activity-tab-all"' in source
    assert "const isActive = tab.dataset.filter === filter;" in set_active_body
    assert "tab.setAttribute('aria-selected', isActive ? 'true' : 'false');" in set_active_body
    assert "panel.setAttribute('aria-labelledby', tab.id);" in set_active_body
