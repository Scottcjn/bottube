from pathlib import Path
import re


TEMPLATES_DIR = Path(__file__).parent.parent / "bottube_templates"


def _history_limit_input(template_name):
    html = (TEMPLATES_DIR / template_name).read_text(encoding="utf-8")
    match = re.search(r'<input[^>]*id="historyLimitInput"[^>]*>', html)
    assert match, f"{template_name} is missing the history limit input"
    return match.group(0)


def test_bridge_history_limit_inputs_have_accessible_names():
    for template_name in ("bridge_wrtc.html", "bridge_base.html"):
        input_markup = _history_limit_input(template_name)
        assert 'aria-label="History entries to load"' in input_markup
