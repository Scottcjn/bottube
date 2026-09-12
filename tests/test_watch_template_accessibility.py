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


def test_watch_template_embed_snippet_names_its_iframe():
    """The copyable embed snippet must carry an accessible name (#2251).

    The generator's output lands on other people's sites, so its iframe needs
    a name of its own: a screen reader announces frames by name, and an
    unnamed one gives the reader nothing to decide on before entering it. The
    name carries the video title because a page embedding several BoTTube
    videos would otherwise present frames that all announce identically, and
    it is escaped because a title is free text that would otherwise close the
    attribute.
    """
    template = Path(__file__).resolve().parents[1] / "bottube_templates" / "watch.html"
    html = template.read_text(encoding="utf-8")

    assert 'var videoTitle = {{ (video.title or "") | tojson }};' in html, (
        "the embed generator has no title to work from; `tojson` is what keeps "
        "a quote or a backslash in the title from breaking the script"
    )
    assert "function escapeEmbedAttribute(value)" in html
    for replacement in ("&amp;", "&lt;", "&gt;", "&quot;", "&#39;"):
        assert replacement in html, f"escapeEmbedAttribute does not encode {replacement}"
    assert 'return title ? "BoTTube video: " + title : "BoTTube video";' in html, (
        "a video with no title must still produce a named frame"
    )
    assert (
        '\'<iframe src="https://bottube.ai/embed/\' + videoId + \'" title="\' + title + \'"'
        in html
    ), "the generated snippet does not name the frame"
