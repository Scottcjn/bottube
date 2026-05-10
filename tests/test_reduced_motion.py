from pathlib import Path


def test_base_template_respects_reduced_motion_preference():
    template = Path("bottube_templates/base.html").read_text(encoding="utf-8")

    assert "@media (prefers-reduced-motion: reduce)" in template
    assert "animation-duration: 0.01ms !important;" in template
    assert "animation-iteration-count: 1 !important;" in template
    assert "transition-duration: 0.01ms !important;" in template
    assert "scroll-behavior: auto !important;" in template
