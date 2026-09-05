# SPDX-License-Identifier: MIT
from pathlib import Path


def test_watch_template_does_not_duplicate_main_landmark():
    """Verify the watch template does not duplicate the page main landmark.

    The base template already exposes a #main-content landmark for keyboard
    and screen reader navigation. The watch page must reuse that landmark
    (or omit a competing one) so assistive tech does not see two conflicting
    'primary content' regions on the same route.
    """
    template = Path(__file__).resolve().parents[1] / "bottube_templates" / "watch.html"
    html = template.read_text(encoding="utf-8")

    assert 'id="main-content"' not in html
    assert 'role="main"' not in html
    assert 'href="#main-content"' not in html
    assert 'id="watch-layout" role="region" aria-label="Video page"' in html
