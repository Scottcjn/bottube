from pathlib import Path


def test_watch_template_does_not_duplicate_main_landmark():
    template = Path(__file__).resolve().parents[1] / "bottube_templates" / "watch.html"
    html = template.read_text(encoding="utf-8")

    assert 'id="main-content"' not in html
    assert 'role="main"' not in html
    assert 'href="#main-content"' not in html
    assert 'id="watch-layout" role="region" aria-label="Video page"' in html
